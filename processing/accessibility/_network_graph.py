# -*- coding: utf-8 -*-
"""Shared road-network graph helpers for PlanX emergency accessibility tools."""
from __future__ import annotations

import heapq
import math
from collections import defaultdict

from qgis.core import QgsPointXY, QgsWkbTypes


def iter_features(source):
    if source is None:
        return []
    return [feature for feature in source.getFeatures() if feature.hasGeometry()]


def iter_line_parts(geometry):
    if geometry.isMultipart():
        return geometry.asMultiPolyline()
    line = geometry.asPolyline()
    return [line] if line else []


def node_key(point, tolerance):
    return (
        round(point.x() / tolerance) * tolerance,
        round(point.y() / tolerance) * tolerance,
    )


def segment_length(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def travel_time_minutes(length_m: float, speed_kmh: float) -> float:
    meters_per_minute = max(speed_kmh * 1000.0 / 60.0, 0.0001)
    return length_m / meters_per_minute


ROAD_CLASS_CAPACITY_PH = {
    "arterial": 2400.0,
    "collector": 1200.0,
    "local": 600.0,
    "motorway": 3000.0,
    "primary": 2000.0,
    "secondary": 1200.0,
    "tertiary": 800.0,
    "residential": 400.0,
}


def numeric_attribute(feature, field_name):
    if not field_name:
        return None
    try:
        value = feature[field_name]
        if value in (None, ""):
            return None
        return float(value)
    except (KeyError, TypeError, ValueError):
        return None


def direction_mode(feature, direction_field):
    """Return 'both', 'ft' (forward along digitized line), or 'bt' (backward)."""
    if not direction_field:
        return "both"
    try:
        raw = str(feature[direction_field] or "").strip().lower()
    except KeyError:
        return "both"
    if raw in ("ft", "forward", "f", "one_way", "oneway", "1", "yes", "true"):
        return "ft"
    if raw in ("bt", "backward", "b", "reverse", "-1"):
        return "bt"
    return "both"


def capacity_from_feature(feature, capacity_field, class_field, default_capacity, class_capacity_map):
    if capacity_field:
        value = numeric_attribute(feature, capacity_field)
        if value is not None and value > 0:
            return value
    if class_field:
        try:
            raw = feature[class_field]
            cls = str(raw or "").strip().lower()
        except KeyError:
            cls = ""
        if cls:
            mapping = class_capacity_map or ROAD_CLASS_CAPACITY_PH
            return mapping.get(cls, default_capacity)
    return default_capacity


def build_road_graph(
    roads,
    tolerance,
    capacity_field=None,
    class_field=None,
    direction_field=None,
    default_capacity=1200.0,
    class_capacity_map=None,
):
    """Build road graph with edge IDs and per-edge capacity (persons/hour).

    When ``direction_field`` is set, values FT/BT (or aliases) restrict edge direction
    along the digitized line; empty/other values keep both directions.

    Returns:
        graph: node -> [(neighbor, length_m, edge_id), ...]
        nodes: node -> QgsPointXY
        edges: edge_id -> (n1, n2)
        edge_capacity: edge_id -> persons per hour
    """
    graph = defaultdict(list)
    nodes: dict = {}
    edges: dict = {}
    edge_capacity: dict[int, float] = {}
    edge_id = 0
    for feature in iter_features(roads):
        segment_cap = capacity_from_feature(
            feature, capacity_field, class_field, default_capacity, class_capacity_map,
        )
        travel_dir = direction_mode(feature, direction_field)
        for part in iter_line_parts(feature.geometry()):
            if len(part) < 2:
                continue
            for p1, p2 in zip(part[:-1], part[1:]):
                n1 = node_key(p1, tolerance)
                n2 = node_key(p2, tolerance)
                if n1 == n2:
                    continue
                length = segment_length(n1, n2)
                if length <= 0:
                    continue
                if travel_dir in ("both", "ft"):
                    graph[n1].append((n2, length, edge_id))
                if travel_dir in ("both", "bt"):
                    graph[n2].append((n1, length, edge_id))
                nodes[n1] = QgsPointXY(n1[0], n1[1])
                nodes[n2] = QgsPointXY(n2[0], n2[1])
                edges[edge_id] = (n1, n2)
                edge_capacity[edge_id] = segment_cap
                edge_id += 1
    return graph, nodes, edges, edge_capacity


def nearest_graph_node(point, nodes, tolerance):
    """Snap a QgsPointXY to the closest graph node (linear scan)."""
    px, py = point.x(), point.y()
    best, best_d = None, float("inf")
    for key in nodes:
        d = (key[0] - px) ** 2 + (key[1] - py) ** 2
        if d < best_d:
            best_d = d
            best = key
    if best is None or best_d ** 0.5 > tolerance * 50:
        return None
    return best


def feature_point(geometry):
    if geometry.type() == QgsWkbTypes.PointGeometry:
        return geometry.asPoint()
    return geometry.centroid().asPoint()


def dijkstra_predecessors(graph, start_node, target_nodes):
    """Multi-target Dijkstra on length weights.

    Returns (distances, predecessor) where predecessor[node] = (prev_node, edge_id).
    """
    distances = {start_node: 0.0}
    predecessor = {}
    queue = [(0.0, start_node)]
    remaining = set(target_nodes)
    while queue and remaining:
        dist, node = heapq.heappop(queue)
        if dist > distances.get(node, float("inf")):
            continue
        if node in remaining:
            remaining.discard(node)
        for neighbor, weight, eid in graph.get(node, []):
            new_dist = dist + weight
            if new_dist < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_dist
                predecessor[neighbor] = (node, eid)
                heapq.heappush(queue, (new_dist, neighbor))
    return distances, predecessor


def reconstruct_path_edges(predecessor, start_node, target_node):
    """Walk predecessor map from target back to start; return edge_ids used."""
    path_edges = []
    current = target_node
    while current in predecessor and current != start_node:
        prev, eid = predecessor[current]
        path_edges.append(eid)
        current = prev
    if current != start_node:
        return []
    return path_edges


def multi_source_dijkstra(graph, start_nodes):
    """Shortest-path distances from many sources (destinations) outward.

    Accepts adjacency with (neighbor, length) or (neighbor, length, edge_id).
    """
    distances = {}
    queue = []
    for node in start_nodes:
        distances[node] = 0.0
        heapq.heappush(queue, (0.0, node))
    while queue:
        current_dist, node = heapq.heappop(queue)
        if current_dist > distances.get(node, float("inf")):
            continue
        for item in graph.get(node, []):
            if len(item) == 3:
                neighbor, weight, _eid = item
            else:
                neighbor, weight = item
            new_dist = current_dist + weight
            if new_dist < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_dist
                heapq.heappush(queue, (new_dist, neighbor))
    return distances


def build_simple_road_graph(roads, tolerance, direction_field=None):
    """Graph without edge metadata; nodes as QgsGeometry points (network access)."""
    from qgis.core import QgsGeometry

    graph, nodes_xy, edges, _caps = build_road_graph(
        roads, tolerance, direction_field=direction_field,
    )
    simple = defaultdict(list)
    for node, adj in graph.items():
        for neighbor, length, _eid in adj:
            simple[node].append((neighbor, length))
    nodes_geom = {k: QgsGeometry.fromPointXY(v) for k, v in nodes_xy.items()}
    return simple, nodes_geom, len(edges)


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = (p / 100.0) * (len(sorted_values) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac
