# -*- coding: utf-8 -*-
from __future__ import annotations

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .._helpers import access_risk_class
from ._network_graph import build_simple_road_graph, iter_features, multi_source_dijkstra, travel_time_minutes


def _nearest_node(point_geom, node_features, node_index):
    if not node_features or node_index is None:
        return None, None
    nearest = node_index.nearestNeighbor(point_geom.asPoint(), 1)
    if not nearest:
        return None, None
    node = node_features.get(nearest[0])
    if node is None:
        return None, None
    distance = point_geom.distance(node["geometry"])
    return node["key"], distance


from .._mixins import HelpUrlMixin

class NetworkEmergencyAccessibilityAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    ROADS = "ROADS"
    ORIGINS = "ORIGINS"
    DESTINATIONS = "DESTINATIONS"
    SPEED_KMH = "SPEED_KMH"
    TARGET_MINUTES = "TARGET_MINUTES"
    CRITICAL_MINUTES = "CRITICAL_MINUTES"
    SNAP_TOLERANCE = "SNAP_TOLERANCE"
    OUTPUT_ORIGINS = "OUTPUT_ORIGINS"
    OUTPUT_UNDERSERVED = "OUTPUT_UNDERSERVED"

    def tr(self, string):
        return string

    def createInstance(self):
        return NetworkEmergencyAccessibilityAlgorithm()

    def name(self):
        return "network_emergency_accessibility"

    def displayName(self):
        return self.tr("Network Emergency Accessibility")

    def group(self):
        return self.tr("5 - Emergency: accessibility and coverage")

    def groupId(self):
        return "planx_urban_resilience_emergency"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Network Emergency Accessibility</h3>
            <p>Computes approximate network distance and travel time from population assets or buildings to the nearest shelter/safe area using a line road network.</p>
            <p>This is an offline topological screening model. It uses road segment vertices as graph nodes, so prepare a connected and reasonably noded road layer for better results.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.ROADS, self.tr("Road network (line)"), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ORIGINS, self.tr("Origins: buildings / facilities / population assets"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.DESTINATIONS, self.tr("Destinations: shelters / safe assembly areas"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterNumber(self.SPEED_KMH, self.tr("Assumed travel speed (km/h)"), QgsProcessingParameterNumber.Double, defaultValue=4.5, minValue=0.5, maxValue=120.0))
        self.addParameter(QgsProcessingParameterNumber(self.TARGET_MINUTES, self.tr("Target access time (minutes)"), QgsProcessingParameterNumber.Double, defaultValue=10.0, minValue=1.0, maxValue=240.0))
        self.addParameter(QgsProcessingParameterNumber(self.CRITICAL_MINUTES, self.tr("Critical access time (minutes)"), QgsProcessingParameterNumber.Double, defaultValue=25.0, minValue=1.0, maxValue=480.0))
        self.addParameter(QgsProcessingParameterNumber(self.SNAP_TOLERANCE, self.tr("Graph node snapping tolerance (map units)"), QgsProcessingParameterNumber.Double, defaultValue=1.0, minValue=0.01))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_ORIGINS, self.tr("Network accessibility origins")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_UNDERSERVED, self.tr("Network underserved origins")))

    def processAlgorithm(self, parameters, context, feedback):
        roads = self.parameterAsSource(parameters, self.ROADS, context)
        origins = self.parameterAsSource(parameters, self.ORIGINS, context)
        destinations = self.parameterAsSource(parameters, self.DESTINATIONS, context)
        speed_kmh = self.parameterAsDouble(parameters, self.SPEED_KMH, context)
        target_minutes = self.parameterAsDouble(parameters, self.TARGET_MINUTES, context)
        critical_minutes = max(self.parameterAsDouble(parameters, self.CRITICAL_MINUTES, context), target_minutes)
        tolerance = self.parameterAsDouble(parameters, self.SNAP_TOLERANCE, context)

        graph, nodes, edge_count = build_simple_road_graph(roads, tolerance)
        if not nodes or edge_count == 0:
            raise Exception("Road network did not produce graph nodes. Check line geometry and CRS.")

        node_fields = QgsFields()
        node_fields.append(QgsField("node_id", QVariant.Int))
        node_features = {}
        for idx, (key, geometry) in enumerate(nodes.items()):
            node_features[idx] = {"key": key, "geometry": geometry}
        node_index = QgsSpatialIndex()
        for idx, data in node_features.items():
            feature = QgsFeature(node_fields)
            feature.setGeometry(data["geometry"])
            feature.setAttributes([idx])
            feature.setId(idx)
            node_index.addFeature(feature)

        destination_nodes = []
        for feature in iter_features(destinations):
            node, _snap = _nearest_node(feature.geometry().centroid(), node_features, node_index)
            if node is not None:
                destination_nodes.append(node)
        if not destination_nodes:
            raise Exception("No destination could be snapped to the road graph.")

        network_distances = multi_source_dijkstra(graph, destination_nodes)

        fields = QgsFields()
        for field in origins.fields():
            fields.append(field)
        fields.append(QgsField("net_dist_m", QVariant.Double))
        fields.append(QgsField("snap_dist", QVariant.Double))
        fields.append(QgsField("time_min", QVariant.Double))
        fields.append(QgsField("access_cls", QVariant.String))
        fields.append(QgsField("qa_flag", QVariant.String))
        (origin_sink, origin_id) = self.parameterAsSink(parameters, self.OUTPUT_ORIGINS, context, fields, QgsWkbTypes.Point, origins.sourceCrs())
        (underserved_sink, underserved_id) = self.parameterAsSink(parameters, self.OUTPUT_UNDERSERVED, context, fields, QgsWkbTypes.Point, origins.sourceCrs())

        origin_features = iter_features(origins)
        total = max(len(origin_features), 1)
        for idx, feature in enumerate(origin_features):
            if feedback.isCanceled():
                break
            point = feature.geometry().centroid()
            node, snap_dist = _nearest_node(point, node_features, node_index)
            if node is None or node not in network_distances:
                net_dist = -1.0
                time_min = -1.0
                access_cls = "Unreachable"
                qa_flag = "not_connected"
            else:
                net_dist = network_distances[node] + (snap_dist or 0.0)
                time_min = travel_time_minutes(net_dist, speed_kmh)
                access_cls = access_risk_class(time_min, target_minutes, critical_minutes)
                qa_flag = "ok" if (snap_dist or 0.0) <= tolerance * 5.0 else "large_snap_distance"
            out = QgsFeature(fields)
            out.setGeometry(point)
            out.setAttributes(feature.attributes() + [net_dist, snap_dist or -1.0, time_min, access_cls, qa_flag])
            origin_sink.addFeature(out, QgsFeatureSink.FastInsert)
            if access_cls in ("Underserved", "Critical", "Unreachable"):
                underserved_sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        feedback.pushInfo(f"Road graph nodes: {len(nodes)}, edges: {edge_count}, destination nodes: {len(destination_nodes)}")
        return {self.OUTPUT_ORIGINS: origin_id, self.OUTPUT_UNDERSERVED: underserved_id}
