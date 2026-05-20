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

import heapq
import math
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
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)


def _features(source):
    if source is None:
        return []
    return [feature for feature in source.getFeatures() if feature.hasGeometry()]


def _parts(geometry):
    if geometry.isMultipart():
        return geometry.asMultiPolyline()
    line = geometry.asPolyline()
    return [line] if line else []


def _node_key(point, tolerance):
    return (
        round(point.x() / tolerance) * tolerance,
        round(point.y() / tolerance) * tolerance,
    )


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _build_graph(roads, tolerance):
    """graph[node] -> list[(neighbor, length, edge_id)]; edges[edge_id] = (n1, n2)"""
    graph = defaultdict(list)
    nodes: dict = {}
    edges: dict = {}
    edge_id = 0
    for feature in _features(roads):
        for part in _parts(feature.geometry()):
            if len(part) < 2:
                continue
            for p1, p2 in zip(part[:-1], part[1:]):
                n1 = _node_key(p1, tolerance)
                n2 = _node_key(p2, tolerance)
                if n1 == n2:
                    continue
                length = _dist(n1, n2)
                if length <= 0:
                    continue
                graph[n1].append((n2, length, edge_id))
                graph[n2].append((n1, length, edge_id))
                nodes[n1] = QgsPointXY(n1[0], n1[1])
                nodes[n2] = QgsPointXY(n2[0], n2[1])
                edges[edge_id] = (n1, n2)
                edge_id += 1
    return graph, nodes, edges


def _dijkstra_predecessors(graph, start_node, target_nodes):
    """Multi-target Dijkstra. Returns (distances, predecessor_edges) where
    predecessor_edges[node] = (prev_node, edge_id). Stops once all targets found."""
    distances = {start_node: 0.0}
    predecessor = {}
    queue = [(0.0, start_node)]
    remaining = set(target_nodes)
    while queue and remaining:
        d, node = heapq.heappop(queue)
        if d > distances.get(node, float("inf")):
            continue
        if node in remaining:
            remaining.discard(node)
        for neighbor, weight, eid in graph.get(node, []):
            new_d = d + weight
            if new_d < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_d
                predecessor[neighbor] = (node, eid)
                heapq.heappush(queue, (new_d, neighbor))
    return distances, predecessor


def _nearest_graph_node(point, nodes, tolerance):
    """Snap a QgsPointXY to the closest graph node (linear scan; OK for ≤ a few thousand nodes)."""
    px, py = point.x(), point.y()
    best, best_d = None, float("inf")
    for key in nodes:
        d = (key[0] - px) ** 2 + (key[1] - py) ** 2
        if d < best_d:
            best_d = d
            best = key
    if best_d ** 0.5 > tolerance * 50:
        return None
    return best


class NetworkCriticalityAlgorithm(QgsProcessingAlgorithm):
    ROADS = "ROADS"
    ORIGINS = "ORIGINS"
    DESTINATIONS = "DESTINATIONS"
    SNAP_TOLERANCE = "SNAP_TOLERANCE"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return NetworkCriticalityAlgorithm()

    def name(self):
        return "network_criticality"

    def displayName(self):
        return self.tr("Network Criticality (edge betweenness proxy)")

    def group(self):
        return self.tr("5 - Emergency")

    def groupId(self):
        return "planx_urban_resilience_emergency"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Network Criticality (edge betweenness proxy)</h3>
            <p>For every origin -> nearest-destination shortest path, count how
            many times each road edge is used. The resulting count is normalised
            to 0-100 as <b>criticality_score</b>. High-score edges are
            bottlenecks: a closure there forces the most reroutes.</p>
            <p>Use case: shelter access, evacuation corridors, lifeline routes
            for hospitals or schools. Pair with the Network Emergency
            Accessibility algorithm to find <i>where</i> demand concentrates.</p>
            <p>Output is a line layer matching the input road CRS with the new
            <code>usage_count</code> and <code>criticality_score</code> fields
            attached to each edge geometry segment.</p>
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

        feedback.pushInfo("Building graph...")
        graph, nodes, edges = _build_graph(roads, tolerance)
        if not edges:
            raise QgsProcessingException("Empty road network after snapping; check the input or lower the snap tolerance.")

        # Snap destinations once.
        dest_nodes: set = set()
        for feat in _features(dests):
            geom = feat.geometry()
            point = geom.centroid().asPoint() if geom.type() != QgsWkbTypes.PointGeometry else geom.asPoint()
            node = _nearest_graph_node(point, nodes, tolerance)
            if node is not None:
                dest_nodes.add(node)
        if not dest_nodes:
            raise QgsProcessingException("No destination snapped to the road network.")

        usage_count: dict = defaultdict(int)
        origin_list = _features(origins)
        total = max(len(origin_list), 1)
        feedback.pushInfo(f"Running {total} origin Dijkstras across {len(dest_nodes)} destinations...")

        for idx, feat in enumerate(origin_list):
            if feedback.isCanceled():
                break
            geom = feat.geometry()
            point = geom.centroid().asPoint() if geom.type() != QgsWkbTypes.PointGeometry else geom.asPoint()
            origin_node = _nearest_graph_node(point, nodes, tolerance)
            if origin_node is None:
                continue
            distances, predecessor = _dijkstra_predecessors(graph, origin_node, dest_nodes)
            reachable = [(distances[d], d) for d in dest_nodes if d in distances]
            if not reachable:
                continue
            reachable.sort()
            target = reachable[0][1]
            # Walk back to origin collecting edges used.
            current = target
            while current in predecessor and current != origin_node:
                prev, eid = predecessor[current]
                usage_count[eid] += 1
                current = prev
            feedback.setProgress(int((idx + 1) / total * 100))

        # Emit edge layer
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
            length = _dist(n1, n2)
            line_geom = QgsGeometry.fromPolylineXY(
                [QgsPointXY(n1[0], n1[1]), QgsPointXY(n2[0], n2[1])]
            )
            feat = QgsFeature(fields)
            feat.setGeometry(line_geom)
            feat.setAttributes([eid, length, count, score])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)

        feedback.pushInfo(f"Done. Max usage on a single edge: {max_usage}")
        return {self.OUTPUT: dest_id}
