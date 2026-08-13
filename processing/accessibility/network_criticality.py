# -*- coding: utf-8 -*-
"""Network Criticality (edge betweenness via OD shortest-path traffic).

For every origin → nearest-destination shortest path on the road network,
count how many times each edge is used. The resulting per-edge usage is
normalised 0-100 and exposed as `criticality_score`. Edges with the highest
score are bottlenecks: closing them would force the most reroutes.

This is an offline proxy for proper betweenness centrality. It scales O(O × V log V),
which is acceptable for a few thousand origins and edges.
"""
from __future__ import annotations

from collections import defaultdict

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)

from ._network_graph import (
    build_road_graph,
    dijkstra_predecessors,
    feature_point,
    iter_features,
    nearest_graph_node,
    reconstruct_path_edges,
    segment_length,
)


from .._mixins import GROUP_EMERGENCY, GroupMixin, HelpUrlMixin  # noqa: E402


class NetworkCriticalityAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_EMERGENCY
    ICON = "tool_network_criticality.png"
    ROADS = "ROADS"
    ORIGINS = "ORIGINS"
    DESTINATIONS = "DESTINATIONS"
    SNAP_TOLERANCE = "SNAP_TOLERANCE"
    ROAD_DIRECTION_FIELD = "ROAD_DIRECTION_FIELD"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return NetworkCriticalityAlgorithm()

    def name(self):
        return "network_criticality"

    def displayName(self):
        return self.tr("Network Criticality (edge betweenness proxy)")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Network Criticality (edge betweenness proxy)</h3>
            <p>Betweenness centrality (Freeman, 1977) measures how much shortest-path
            traffic flows through an edge, summed over every origin-destination pair -
            exact computation (Brandes, 2001) is O(VE), too slow for interactive QGIS use
            on a real road network. This tool narrows the scope instead: the shortest path
            from each real ORIGIN to its single nearest real DESTINATION only, an
            origin-destination usage-count proxy that trades betweenness's generality for
            realism (an actual emergency-access flow pattern) and speed
            (O(origins x edges log vertices)). Closer in spirit to traffic-assignment-based
            criticality than to graph-theoretic betweenness proper.</p>
            <p>usage_count is a raw frequency count, criticality_score = 100 x usage_count
            / max usage_count <i>within this run</i> - not comparable across runs with
            different origin/destination sets. Each origin routes to its single nearest
            destination only; if that shelter fills up, the "next nearest" reassignment
            this implies never actually happens here.</p>
            <p>How to read the results
            - criticality_score is a busy-ness measure, not a removal-impact measure. A
            busy edge with parallel alternatives costs little to lose; a quiet edge can
            still be the ONLY connector for a small demand pocket - usage_count alone
            cannot tell these two cases apart.
            - criticality_score &gt;= 90 marks the busiest few percent of edges under
            normal, all-shelters-available routing.</p>
            <p>Using the results: pair with Evacuation Time Simulation's per-edge load
            output to check whether the busiest corridors also carry the highest
            congestion, and with Seismic Cascade to see whether debris blockages coincide
            with high-criticality edges. Do not use this to identify single points of
            failure or redundancy gaps - that needs an extra-cost-on-removal analysis
            (remove a candidate edge, re-route, measure the detour), which this tool does
            not perform.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ROADS, self.tr("Road network (lines)"),
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ORIGINS, self.tr("Origins (points/polygons - use centroids)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DESTINATIONS, self.tr("Destinations (shelters/safe areas)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SNAP_TOLERANCE, self.tr("Snap tolerance (map units)"),
            type=QgsProcessingParameterNumber.Double, defaultValue=2.0, minValue=0.01,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.ROAD_DIRECTION_FIELD,
            self.tr("Road direction field (optional: both / ft / bt)"),
            parentLayerParameterName=self.ROADS,
            type=QgsProcessingParameterField.String,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Criticality (line)")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        roads = self.parameterAsSource(parameters, self.ROADS, context)
        origins = self.parameterAsSource(parameters, self.ORIGINS, context)
        dests = self.parameterAsSource(parameters, self.DESTINATIONS, context)
        if roads is None or origins is None or dests is None:
            raise QgsProcessingException("Roads, origins and destinations are all required.")
        tolerance = self.parameterAsDouble(parameters, self.SNAP_TOLERANCE, context)
        direction_field = self.parameterAsString(parameters, self.ROAD_DIRECTION_FIELD, context) or ""

        feedback.pushInfo("Building graph...")
        graph, nodes, edges, _edge_capacity = build_road_graph(
            roads, tolerance, direction_field=direction_field or None,
        )
        if not edges:
            raise QgsProcessingException(
                "Empty road network after snapping; check the input or lower the snap tolerance."
            )

        dest_nodes: set = set()
        for feat in iter_features(dests):
            node = nearest_graph_node(feature_point(feat.geometry()), nodes, tolerance)
            if node is not None:
                dest_nodes.add(node)
        if not dest_nodes:
            raise QgsProcessingException("No destination snapped to the road network.")

        usage_count: dict = defaultdict(int)
        origin_list = iter_features(origins)
        total = max(len(origin_list), 1)
        feedback.pushInfo(f"Running {total} origin Dijkstras across {len(dest_nodes)} destinations...")

        for idx, feat in enumerate(origin_list):
            if feedback.isCanceled():
                break
            origin_node = nearest_graph_node(feature_point(feat.geometry()), nodes, tolerance)
            if origin_node is None:
                continue
            distances, predecessor = dijkstra_predecessors(graph, origin_node, dest_nodes)
            reachable = [(distances[d], d) for d in dest_nodes if d in distances]
            if not reachable:
                continue
            reachable.sort()
            target = reachable[0][1]
            for eid in reconstruct_path_edges(predecessor, origin_node, target):
                usage_count[eid] += 1
            feedback.setProgress(int((idx + 1) / total * 100))

        fields = QgsFields()
        fields.append(QgsField("edge_id", QVariant.Int))
        fields.append(QgsField("length_m", QVariant.Double))
        fields.append(QgsField("usage_count", QVariant.Int))
        fields.append(QgsField("criticality_score", QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.LineString, roads.sourceCrs(),
        )

        max_usage = max(usage_count.values()) if usage_count else 1
        for eid, (n1, n2) in edges.items():
            count = usage_count.get(eid, 0)
            score = (100.0 * count / max_usage) if max_usage > 0 else 0.0
            length = segment_length(n1, n2)
            line_geom = QgsGeometry.fromPolylineXY(
                [QgsPointXY(n1[0], n1[1]), QgsPointXY(n2[0], n2[1])]
            )
            feat = QgsFeature(fields)
            feat.setGeometry(line_geom)
            feat.setAttributes([eid, length, count, score])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

        feedback.pushInfo(f"Done. Max usage on a single edge: {max_usage}")
        return {self.OUTPUT: dest_id}
