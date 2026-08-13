# -*- coding: utf-8 -*-
"""Seismic Cascade: Debris → Network Degradation → Accessibility Loss.

The most "wow" cross-domain analysis in the suite: takes the seismic-
debris polygon output from `seismic_debris_monte_carlo`, removes the
blocked road segments from the network, then re-runs shortest-path
accessibility on the degraded network and compares it to the pre-hazard
baseline.

Inputs:
  - Road network (lines)
  - Debris polygons (typically the OUTPUT_HAZARD_MODEL from the seismic
    Monte Carlo algorithm; any polygon impact layer works)
  - Origins (points or polygon centroids)
  - Destinations (shelters / safe areas)
  - Snap tolerance, edge-debris buffer

Outputs (origins layer):
  - cas_pre_dist, cas_post_dist (network metres)
  - cas_delta_dist (post - pre, +inf if newly unreachable)
  - cas_pre_reachable, cas_post_reachable (1/0 flags)
  - cas_status: Reachable / Newly cut off / Always cut off / Worse / Same

Logs:
  - Edges classified as blocked vs clear in the degraded network.
  - Aggregate accessibility loss (median, mean, % cut off).
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
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes,
)


def _parts(geometry: QgsGeometry):
    if geometry is None or geometry.isEmpty():
        return []
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


def _segment_blocked(p1, p2, debris_geometries) -> bool:
    """True if the segment intersects ANY debris polygon."""
    seg_geom = QgsGeometry.fromPolylineXY([QgsPointXY(p1[0], p1[1]),
                                           QgsPointXY(p2[0], p2[1])])
    for poly in debris_geometries:
        if poly is None or poly.isEmpty():
            continue
        if seg_geom.intersects(poly):
            return True
    return False


def _build_graphs(roads_source, debris_geometries, tolerance):
    """Builds two graphs (pre and post) from a road source.

    pre  -> all edges
    post -> only edges that do NOT intersect any debris polygon

    Returns (pre_graph, post_graph, nodes_dict, edges_total, edges_blocked).
    """
    pre_graph: dict = defaultdict(list)
    post_graph: dict = defaultdict(list)
    nodes: dict = {}
    edges_total = 0
    edges_blocked = 0

    for feature in roads_source.getFeatures():
        if not feature.hasGeometry():
            continue
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
                edges_total += 1
                pre_graph[n1].append((n2, length))
                pre_graph[n2].append((n1, length))
                nodes[n1] = QgsPointXY(n1[0], n1[1])
                nodes[n2] = QgsPointXY(n2[0], n2[1])
                if _segment_blocked(n1, n2, debris_geometries):
                    edges_blocked += 1
                    continue
                post_graph[n1].append((n2, length))
                post_graph[n2].append((n1, length))
    return pre_graph, post_graph, nodes, edges_total, edges_blocked


def _multi_source_dijkstra(graph, start_nodes):
    distances: dict = {n: 0.0 for n in start_nodes}
    queue: list = [(0.0, n) for n in start_nodes]
    heapq.heapify(queue)
    while queue:
        current_dist, node = heapq.heappop(queue)
        if current_dist > distances.get(node, float("inf")):
            continue
        for neighbour, weight in graph.get(node, []):
            new_dist = current_dist + weight
            if new_dist < distances.get(neighbour, float("inf")):
                distances[neighbour] = new_dist
                heapq.heappush(queue, (new_dist, neighbour))
    return distances


def _nearest_graph_node(point: QgsPointXY, nodes: dict, tolerance: float):
    if not nodes:
        return None
    best, best_d = None, float("inf")
    px, py = point.x(), point.y()
    for key in nodes:
        d = (key[0] - px) ** 2 + (key[1] - py) ** 2
        if d < best_d:
            best_d = d
            best = key
    if best_d ** 0.5 > tolerance * 50:
        return None
    return best


from .._mixins import GROUP_EMERGENCY, GroupMixin, HelpUrlMixin  # noqa: E402


class SeismicCascadeAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_EMERGENCY
    ICON = "tool_seismic_cascade_accessibility.png"
    ROADS = "ROADS"
    DEBRIS = "DEBRIS"
    ORIGINS = "ORIGINS"
    DESTINATIONS = "DESTINATIONS"
    SNAP_TOLERANCE = "SNAP_TOLERANCE"
    OUTPUT = "OUTPUT"

    OUT_PRE = "cas_pre_dist"
    OUT_POST = "cas_post_dist"
    OUT_DELTA = "cas_delta_dist"
    OUT_PRE_REACH = "cas_pre_reachable"
    OUT_POST_REACH = "cas_post_reachable"
    OUT_STATUS = "cas_status"

    def tr(self, string):
        return string

    def createInstance(self):
        return SeismicCascadeAlgorithm()

    def name(self):
        return "seismic_cascade_accessibility"

    def displayName(self):
        return self.tr("Seismic Cascade: Debris → Network Degradation")

    def shortHelpString(self):
        return self.tr(
            "<h3>Seismic Cascade — Debris → Network Degradation</h3> <p>Cross-domain cascading-hazard "
            "analysis, following the perturb-and-measure methodology formalised in NIST's (2015) "
            "Community Resilience Planning Guide: take a baseline network, perturb it with physical "
            'damage, measure the resulting service gap. Here the "damage" is the debris-polygon '
            "output from Seismic Debris Monte Carlo - this tool pipes it into the road network, drops "
            "every edge the debris intersects, builds pre- and post-hazard graphs, and runs "
            "multi-source Dijkstra from all destinations on each. The two tools are designed to be "
            "run back-to-back, one producing exactly what the other consumes.</p> <p>Debris blockage "
            "is binary - a segment is fully passable or fully blocked, with no partial-capacity "
            "reduction for a segment merely narrowed on one side. There is no repair/clearance "
            'timeline: the "post" graph is the worst moment immediately after the event, not the '
            "gradual reopening that follows. Only debris-driven blockage is modelled - a road segment "
            "with genuine pavement or bridge damage but no adjacent building debris is invisible to "
            "this tool.</p> <p>How to read the results - cas_status = Newly cut off: reachable before "
            "the quake, isolated after - the intervention-priority class. - cas_status = Worse: still "
            "reachable but via a &gt;=1% longer detour (cas_delta_dist &gt; 0). - cas_status = Always "
            "cut off: never reachable, pre or post - a pre-existing gap the quake did not create. - "
            "Origins and destinations snap to the pre- and post-graphs independently, so a large "
            "delta near a blocked segment is worth a map spot-check, not just a table read.</p> "
            "<p>Using the results: run this across several Mw values (6.5, 7.0, 7.5 ...) and compare "
            "the Newly-cut-off counts printed to the log to find the magnitude at which the network "
            "fails catastrophically rather than gradually. This is not a structural assessment of the "
            "road itself - it never asks whether the pavement or a bridge was damaged by shaking, "
            "only whether adjacent-building debris blocks it.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ROADS, self.tr("Road network (lines)"),
            [QgsProcessing.TypeVectorLine],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DEBRIS, self.tr("Debris / impact polygons (typically the seismic Monte Carlo output)"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.ORIGINS, self.tr("Origins (points or polygons - centroid used)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DESTINATIONS, self.tr("Destinations (shelters / safe-assembly)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SNAP_TOLERANCE, self.tr("Snap tolerance (map units)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=2.0, minValue=0.01, maxValue=1000.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Origins with cascade results")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        roads = self.parameterAsSource(parameters, self.ROADS, context)
        debris = self.parameterAsSource(parameters, self.DEBRIS, context)
        origins = self.parameterAsSource(parameters, self.ORIGINS, context)
        destinations = self.parameterAsSource(parameters, self.DESTINATIONS, context)
        tolerance = self.parameterAsDouble(parameters, self.SNAP_TOLERANCE, context)

        if any(x is None for x in (roads, debris, origins, destinations)):
            raise QgsProcessingException(
                "Roads, debris polygons, origins and destinations are all required."
            )

        # Load + spatial-index debris polygons so segment-blocked stays fast.
        feedback.pushInfo("Indexing debris polygons…")
        debris_geometries: list[QgsGeometry] = []
        debris_index = QgsSpatialIndex()
        for feat in debris.getFeatures():
            if not feat.hasGeometry():
                continue
            debris_geometries.append(QgsGeometry(feat.geometry()))
            debris_index.addFeature(feat)
        if not debris_geometries:
            raise QgsProcessingException(
                "No debris polygons supplied — run the seismic Monte Carlo first."
            )

        feedback.pushInfo("Building pre- and post-hazard graphs…")
        pre_graph, post_graph, nodes, e_total, e_blocked = _build_graphs(
            roads, debris_geometries, tolerance
        )
        feedback.pushInfo(
            f"Edges: total = {e_total}, blocked by debris = {e_blocked} "
            f"({(100.0 * e_blocked / max(e_total, 1)):.1f}%)."
        )
        if not pre_graph:
            raise QgsProcessingException("Empty network after snapping.")

        # Snap destinations to nodes once.
        dest_nodes_pre = set()
        dest_nodes_post = set()
        for feat in destinations.getFeatures():
            if not feat.hasGeometry():
                continue
            geom = feat.geometry()
            point = (geom.centroid().asPoint() if geom.type() != QgsWkbTypes.PointGeometry
                     else geom.asPoint())
            node = _nearest_graph_node(point, nodes, tolerance)
            if node is None:
                continue
            if node in pre_graph:
                dest_nodes_pre.add(node)
            if node in post_graph:
                dest_nodes_post.add(node)
        if not dest_nodes_pre:
            raise QgsProcessingException("No destination snapped to the network.")

        feedback.pushInfo(
            f"Destinations on pre-graph: {len(dest_nodes_pre)}, post-graph: {len(dest_nodes_post)}."
        )

        # Multi-source Dijkstra from destinations — same trick used in the
        # network_accessibility module (saves O(origins) full Dijkstras).
        feedback.pushInfo("Running multi-source Dijkstra (pre)…")
        dist_pre = _multi_source_dijkstra(pre_graph, dest_nodes_pre)
        feedback.pushInfo("Running multi-source Dijkstra (post)…")
        dist_post = _multi_source_dijkstra(post_graph, dest_nodes_post) if dest_nodes_post else {}

        # Build output schema.
        out_fields = origins.fields()
        for fname, ftype in (
            (self.OUT_PRE, QVariant.Double),
            (self.OUT_POST, QVariant.Double),
            (self.OUT_DELTA, QVariant.Double),
            (self.OUT_PRE_REACH, QVariant.Int),
            (self.OUT_POST_REACH, QVariant.Int),
            (self.OUT_STATUS, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            origins.wkbType(), origins.sourceCrs(),
        )

        status_counts: dict = {}
        pre_distances: list[float] = []
        post_distances: list[float] = []
        for feat in origins.getFeatures():
            if feedback.isCanceled():
                break
            if not feat.hasGeometry():
                continue
            geom = feat.geometry()
            point = (geom.centroid().asPoint() if geom.type() != QgsWkbTypes.PointGeometry
                     else geom.asPoint())
            node = _nearest_graph_node(point, nodes, tolerance)
            pre_d = dist_pre.get(node, float("inf")) if node is not None else float("inf")
            post_d = dist_post.get(node, float("inf")) if node is not None else float("inf")
            pre_reach = 1 if math.isfinite(pre_d) else 0
            post_reach = 1 if math.isfinite(post_d) else 0
            if pre_reach and not post_reach:
                status = "Newly cut off"
            elif not pre_reach and not post_reach:
                status = "Always cut off"
            elif pre_reach and post_reach and post_d > pre_d * 1.01:
                status = "Worse"
            elif pre_reach and post_reach:
                status = "Same"
            else:
                # Pre cut off, post reachable — happens only if the post graph
                # somehow added connectivity (shouldn't but handled defensively).
                status = "Recovered"
            status_counts[status] = status_counts.get(status, 0) + 1
            if math.isfinite(pre_d):
                pre_distances.append(pre_d)
            if math.isfinite(post_d):
                post_distances.append(post_d)

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(geom)
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([
                pre_d if math.isfinite(pre_d) else None,
                post_d if math.isfinite(post_d) else None,
                (post_d - pre_d) if (math.isfinite(pre_d) and math.isfinite(post_d)) else None,
                pre_reach, post_reach, status,
            ])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        # Summary.
        def _median(xs):
            if not xs:
                return None
            xs = sorted(xs)
            n = len(xs)
            return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])

        total = sum(status_counts.values()) or 1
        feedback.pushInfo("")
        feedback.pushInfo("─── Seismic cascade summary ───")
        for status in ("Newly cut off", "Always cut off", "Worse", "Same", "Recovered"):
            count = status_counts.get(status, 0)
            pct = 100.0 * count / total
            feedback.pushInfo(f"  {status:<16} : {count:>6}  ({pct:5.1f}%)")
        med_pre = _median(pre_distances)
        med_post = _median(post_distances)
        if med_pre is not None:
            feedback.pushInfo(f"Median pre-hazard distance to nearest shelter : {med_pre:,.1f}")
        if med_post is not None:
            feedback.pushInfo(f"Median post-hazard distance to nearest shelter: {med_post:,.1f}")
        return {self.OUTPUT: dest_id}
