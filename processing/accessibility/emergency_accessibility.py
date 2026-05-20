# -*- coding: utf-8 -*-
from __future__ import annotations

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .._helpers import clamp, accessibility_deficit_class


def _features(source):
    if source is None:
        return []
    return [feature for feature in source.getFeatures() if feature.hasGeometry()]


def _union(source):
    geometries = [feature.geometry().makeValid() for feature in _features(source)]
    if not geometries:
        return None
    return QgsGeometry.unaryUnion(geometries).makeValid()


def _nearest_distance(point_geom, features, index):
    if not features or index is None:
        return None
    nearest_ids = index.nearestNeighbor(point_geom.asPoint(), 1)
    if not nearest_ids:
        return None
    feature_by_id = {feature.id(): feature for feature in features}
    nearest = feature_by_id.get(nearest_ids[0])
    if nearest is None:
        return None
    return point_geom.distance(nearest.geometry())


class EmergencyAccessibilityAlgorithm(QgsProcessingAlgorithm):
    STUDY_AREA = "STUDY_AREA"
    SHELTERS = "SHELTERS"
    POPULATION_ASSETS = "POPULATION_ASSETS"
    BARRIERS = "BARRIERS"
    CELL_SIZE = "CELL_SIZE"
    SERVICE_DISTANCE = "SERVICE_DISTANCE"
    CRITICAL_DISTANCE = "CRITICAL_DISTANCE"
    BARRIER_WEIGHT = "BARRIER_WEIGHT"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_UNDERSERVED = "OUTPUT_UNDERSERVED"

    def tr(self, string):
        return string

    def createInstance(self):
        return EmergencyAccessibilityAlgorithm()

    def name(self):
        return "emergency_accessibility_shelter_coverage"

    def displayName(self):
        return self.tr("Emergency Accessibility and Shelter Coverage")

    def group(self):
        return self.tr("5 - Emergency: accessibility and coverage")

    def groupId(self):
        return "planx_urban_resilience_emergency"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Emergency Accessibility and Shelter Coverage</h3>
            <p>Creates a grid-based access deficit map from shelters or safe assembly areas. Optional population/building assets are marked when they fall outside the selected service distance.</p>
            <p>This is an offline Euclidean screening model. It is useful for first-pass planning and classroom comparison before network-based analysis.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.STUDY_AREA, self.tr("Study area (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.SHELTERS, self.tr("Shelters / safe assembly areas (point or polygon)"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.POPULATION_ASSETS, self.tr("Population assets / buildings / facilities (optional)"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.BARRIERS, self.tr("Barriers / blocked areas (optional polygon)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE, self.tr("Grid cell size (map units)"), QgsProcessingParameterNumber.Double, defaultValue=100.0, minValue=5.0))
        self.addParameter(QgsProcessingParameterNumber(self.SERVICE_DISTANCE, self.tr("Target service distance"), QgsProcessingParameterNumber.Double, defaultValue=500.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(self.CRITICAL_DISTANCE, self.tr("Critical distance"), QgsProcessingParameterNumber.Double, defaultValue=1200.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(self.BARRIER_WEIGHT, self.tr("Barrier overlap penalty weight"), QgsProcessingParameterNumber.Double, defaultValue=25.0, minValue=0.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_GRID, self.tr("Emergency accessibility grid")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_UNDERSERVED, self.tr("Underserved assets")))

    def processAlgorithm(self, parameters, context, feedback):
        study = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        shelters = self.parameterAsSource(parameters, self.SHELTERS, context)
        assets = self.parameterAsSource(parameters, self.POPULATION_ASSETS, context)
        barriers = self.parameterAsSource(parameters, self.BARRIERS, context)
        cell_size = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        service_distance = self.parameterAsDouble(parameters, self.SERVICE_DISTANCE, context)
        critical_distance = self.parameterAsDouble(parameters, self.CRITICAL_DISTANCE, context)
        barrier_weight = self.parameterAsDouble(parameters, self.BARRIER_WEIGHT, context)

        study_union = _union(study)
        barrier_union = _union(barriers)
        shelter_features = _features(shelters)
        shelter_index = QgsSpatialIndex(shelter_features) if shelter_features else None

        fields = QgsFields()
        fields.append(QgsField("cell_id", QVariant.Int))
        fields.append(QgsField("dist_shelter", QVariant.Double))
        fields.append(QgsField("barrier_pct", QVariant.Double))
        fields.append(QgsField("access_score", QVariant.Double))
        fields.append(QgsField("access_class", QVariant.String))
        (grid_sink, grid_id) = self.parameterAsSink(parameters, self.OUTPUT_GRID, context, fields, QgsWkbTypes.Polygon, study.sourceCrs())

        asset_fields = QgsFields()
        asset_fields.append(QgsField("asset_type", QVariant.String))
        asset_fields.append(QgsField("dist_shelter", QVariant.Double))
        asset_fields.append(QgsField("access_score", QVariant.Double))
        asset_fields.append(QgsField("access_class", QVariant.String))
        (asset_sink, asset_id) = self.parameterAsSink(parameters, self.OUTPUT_UNDERSERVED, context, asset_fields, QgsWkbTypes.Point, study.sourceCrs())

        extent = study.sourceExtent()
        total_cols = max(1, int((extent.xMaximum() - extent.xMinimum()) / cell_size) + 1)
        total_rows = max(1, int((extent.yMaximum() - extent.yMinimum()) / cell_size) + 1)
        total = total_cols * total_rows
        cell_id = 0
        high_geoms = []
        x = extent.xMinimum()
        while x < extent.xMaximum():
            y = extent.yMinimum()
            while y < extent.yMaximum():
                if feedback.isCanceled():
                    break
                rect = QgsRectangle(x, y, min(x + cell_size, extent.xMaximum()), min(y + cell_size, extent.yMaximum()))
                cell_geom = QgsGeometry.fromRect(rect)
                if study_union is None or not cell_geom.intersects(study_union):
                    y += cell_size
                    cell_id += 1
                    continue
                clipped = cell_geom.intersection(study_union).makeValid()
                centroid = clipped.centroid()
                distance = _nearest_distance(centroid, shelter_features, shelter_index)
                dist_value = distance if distance is not None else critical_distance
                access_score = clamp(((dist_value - service_distance) / max(critical_distance - service_distance, 1.0)) * 100.0)
                barrier_pct = 0.0
                if barrier_union and not barrier_union.isEmpty():
                    inter = clipped.intersection(barrier_union)
                    if not inter.isEmpty() and clipped.area() > 0:
                        barrier_pct = clamp(inter.area() / clipped.area() * 100.0)
                        access_score = clamp(access_score + (barrier_pct / 100.0) * barrier_weight)
                access_class = accessibility_deficit_class(access_score)
                feat = QgsFeature(fields)
                feat.setGeometry(clipped)
                feat.setAttributes([cell_id, dist_value, barrier_pct, access_score, access_class])
                grid_sink.addFeature(feat, QgsFeatureSink.FastInsert)
                if access_score >= 55:
                    high_geoms.append(clipped)
                feedback.setProgress(int(min(100, cell_id / total * 100)))
                y += cell_size
                cell_id += 1
            x += cell_size

        underserved_union = QgsGeometry.unaryUnion(high_geoms).makeValid() if high_geoms else None
        for feature in _features(assets):
            point = feature.geometry().centroid()
            distance = _nearest_distance(point, shelter_features, shelter_index)
            dist_value = distance if distance is not None else critical_distance
            score = clamp(((dist_value - service_distance) / max(critical_distance - service_distance, 1.0)) * 100.0)
            if score < 55 and not (underserved_union and feature.geometry().intersects(underserved_union)):
                continue
            out = QgsFeature(asset_fields)
            out.setGeometry(point)
            out.setAttributes(["asset", dist_value, score, accessibility_deficit_class(score)])
            asset_sink.addFeature(out, QgsFeatureSink.FastInsert)

        return {
            self.OUTPUT_GRID: grid_id,
            self.OUTPUT_UNDERSERVED: asset_id,
        }
