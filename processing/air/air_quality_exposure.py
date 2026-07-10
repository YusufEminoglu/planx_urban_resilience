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

from .._helpers import clamp, composite_risk_class


def _features(source):
    if source is None:
        return []
    return [feature for feature in source.getFeatures() if feature.hasGeometry()]


def _union(source):
    geometries = [feature.geometry().makeValid() for feature in _features(source)]
    if not geometries:
        return None
    return QgsGeometry.unaryUnion(geometries).makeValid()


def _area_share(cell_geom, target_union):
    if target_union is None or target_union.isEmpty() or cell_geom.area() <= 0:
        return 0.0
    inter = cell_geom.intersection(target_union)
    if inter.isEmpty():
        return 0.0
    return clamp(inter.area() / cell_geom.area(), 0.0, 1.0)


def _distance_risk(geom, target_union, max_distance, missing_score=0.0):
    if target_union is None or target_union.isEmpty():
        return missing_score
    distance = geom.distance(target_union)
    return clamp(100.0 - (distance / max(max_distance, 1.0)) * 100.0)


def _point_count(cell_geom, features, index):
    if not features or index is None:
        return 0
    feature_by_id = {feature.id(): feature for feature in features}
    count = 0
    for fid in index.intersects(cell_geom.boundingBox()):
        feature = feature_by_id.get(fid)
        if feature and feature.geometry().intersects(cell_geom):
            count += 1
    return count


from .._mixins import HelpUrlMixin  # noqa: E402




class AirQualityExposureAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    STUDY_AREA = "STUDY_AREA"
    ROADS = "ROADS"
    EMISSION_SOURCES = "EMISSION_SOURCES"
    SENSITIVE = "SENSITIVE"
    GREEN_BUFFERS = "GREEN_BUFFERS"
    CELL_SIZE = "CELL_SIZE"
    ROAD_DISTANCE = "ROAD_DISTANCE"
    SOURCE_DISTANCE = "SOURCE_DISTANCE"
    ROAD_WEIGHT = "ROAD_WEIGHT"
    SOURCE_WEIGHT = "SOURCE_WEIGHT"
    SENSITIVE_WEIGHT = "SENSITIVE_WEIGHT"
    BUFFER_WEIGHT = "BUFFER_WEIGHT"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_EXPOSED = "OUTPUT_EXPOSED"

    def tr(self, string):
        return string

    def createInstance(self):
        return AirQualityExposureAlgorithm()

    def name(self):
        return "air_quality_exposure_screening"

    def displayName(self):
        return self.tr("Air Quality / Urban Exposure (screening)")

    def group(self):
        return self.tr("6 - Air: exposure screening")

    def groupId(self):
        return "planx_urban_resilience_air"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Air Quality / Urban Exposure</h3>
            <p>Creates a planning-support exposure grid from road proximity, optional industrial/emission sources, sensitive receptors and green buffer coverage.</p>
            <p>This is not an atmospheric dispersion model. Use it for first-pass spatial screening and classroom comparison.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.STUDY_AREA, self.tr("Study area (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ROADS, self.tr("Major roads / traffic corridors (line)"), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.EMISSION_SOURCES, self.tr("Industrial / emission sources (optional point or polygon)"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.SENSITIVE, self.tr("Sensitive receptors: schools, hospitals, housing (optional)"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.GREEN_BUFFERS, self.tr("Green buffers / tree belts (optional polygon)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE, self.tr("Grid cell size (map units)"), QgsProcessingParameterNumber.Double, defaultValue=100.0, minValue=5.0))
        self.addParameter(QgsProcessingParameterNumber(self.ROAD_DISTANCE, self.tr("Road influence distance"), QgsProcessingParameterNumber.Double, defaultValue=300.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(self.SOURCE_DISTANCE, self.tr("Emission source influence distance"), QgsProcessingParameterNumber.Double, defaultValue=600.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(self.ROAD_WEIGHT, self.tr("Road proximity weight"), QgsProcessingParameterNumber.Double, defaultValue=0.35, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.SOURCE_WEIGHT, self.tr("Emission source proximity weight"), QgsProcessingParameterNumber.Double, defaultValue=0.25, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.SENSITIVE_WEIGHT, self.tr("Sensitive receptor weight"), QgsProcessingParameterNumber.Double, defaultValue=0.25, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.BUFFER_WEIGHT, self.tr("Green buffer mitigation weight"), QgsProcessingParameterNumber.Double, defaultValue=0.15, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_GRID, self.tr("Air exposure grid")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_EXPOSED, self.tr("Exposed sensitive receptors")))

    def processAlgorithm(self, parameters, context, feedback):
        study = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        roads = self.parameterAsSource(parameters, self.ROADS, context)
        sources = self.parameterAsSource(parameters, self.EMISSION_SOURCES, context)
        sensitive = self.parameterAsSource(parameters, self.SENSITIVE, context)
        green = self.parameterAsSource(parameters, self.GREEN_BUFFERS, context)
        cell_size = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        road_distance = self.parameterAsDouble(parameters, self.ROAD_DISTANCE, context)
        source_distance = self.parameterAsDouble(parameters, self.SOURCE_DISTANCE, context)
        w_road = self.parameterAsDouble(parameters, self.ROAD_WEIGHT, context)
        w_source = self.parameterAsDouble(parameters, self.SOURCE_WEIGHT, context)
        w_sensitive = self.parameterAsDouble(parameters, self.SENSITIVE_WEIGHT, context)
        w_buffer = self.parameterAsDouble(parameters, self.BUFFER_WEIGHT, context)
        weight_sum = max(w_road + w_source + w_sensitive, 0.0001)

        study_union = _union(study)
        road_union = _union(roads)
        source_union = _union(sources)
        green_union = _union(green)
        sensitive_features = _features(sensitive)
        sensitive_index = QgsSpatialIndex()
        if sensitive_features:
            for f in sensitive_features:
                sensitive_index.addFeature(f)
        else:
            sensitive_index = None

        fields = QgsFields()
        for name in ("cell_id", "road_score", "source_score", "sens_count", "green_share", "air_score", "risk_class"):
            field_type = QVariant.String if name == "risk_class" else QVariant.Double
            if name in ("cell_id", "sens_count"):
                field_type = QVariant.Int
            fields.append(QgsField(name, field_type))
        (grid_sink, grid_id) = self.parameterAsSink(parameters, self.OUTPUT_GRID, context, fields, QgsWkbTypes.Polygon, study.sourceCrs())

        exposed_fields = QgsFields()
        exposed_fields.append(QgsField("asset_type", QVariant.String))
        exposed_fields.append(QgsField("air_score", QVariant.Double))
        exposed_fields.append(QgsField("risk_class", QVariant.String))
        (exposed_sink, exposed_id) = self.parameterAsSink(parameters, self.OUTPUT_EXPOSED, context, exposed_fields, QgsWkbTypes.Point, study.sourceCrs())

        scored_cells = []
        extent = study.sourceExtent()
        total_cols = max(1, int((extent.xMaximum() - extent.xMinimum()) / cell_size) + 1)
        total_rows = max(1, int((extent.yMaximum() - extent.yMinimum()) / cell_size) + 1)
        total = total_cols * total_rows
        cell_id = 0
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
                road_score = _distance_risk(centroid, road_union, road_distance, missing_score=0.0)
                source_score = _distance_risk(centroid, source_union, source_distance, missing_score=0.0)
                sens_count = _point_count(clipped, sensitive_features, sensitive_index)
                sensitive_score = clamp(sens_count * 25.0)
                green_share = _area_share(clipped, green_union)
                raw = (road_score * w_road + source_score * w_source + sensitive_score * w_sensitive) / weight_sum
                air_score = clamp(raw - green_share * 100.0 * w_buffer)
                risk = composite_risk_class(air_score)
                feat = QgsFeature(fields)
                feat.setGeometry(clipped)
                feat.setAttributes([cell_id, road_score, source_score, sens_count, green_share, air_score, risk])
                grid_sink.addFeature(feat, QgsFeatureSink.FastInsert)
                scored_cells.append((clipped, air_score, risk))
                feedback.setProgress(int(min(100, cell_id / total * 100)))
                y += cell_size
                cell_id += 1
            x += cell_size

        high_union = QgsGeometry.unaryUnion([geom for geom, score, _risk in scored_cells if score >= 55]).makeValid() if scored_cells else None
        if high_union and not high_union.isEmpty():
            for feature in sensitive_features:
                if feature.geometry().intersects(high_union):
                    point = feature.geometry().centroid()
                    score = max(_distance_risk(point, road_union, road_distance), _distance_risk(point, source_union, source_distance))
                    out = QgsFeature(exposed_fields)
                    out.setGeometry(point)
                    out.setAttributes(["sensitive_receptor", score, composite_risk_class(score)])
                    exposed_sink.addFeature(out, QgsFeatureSink.FastInsert)

        return {self.OUTPUT_GRID: grid_id, self.OUTPUT_EXPOSED: exposed_id}
