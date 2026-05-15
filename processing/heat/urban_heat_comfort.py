# -*- coding: utf-8 -*-
from __future__ import annotations

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
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
)


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _risk_class(score):
    if score >= 75:
        return "Very High"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Moderate"
    return "Low"


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
    if target_union is None or target_union.isEmpty():
        return 0.0
    inter = cell_geom.intersection(target_union)
    if inter.isEmpty():
        return 0.0
    area = cell_geom.area()
    return 0.0 if area <= 0 else _clamp(inter.area() / area, 0.0, 1.0)


def _distance_score(point_geom, target_union, max_distance):
    if target_union is None or target_union.isEmpty():
        return 100.0
    distance = point_geom.distance(target_union)
    return _clamp((distance / max(max_distance, 1.0)) * 100.0)


def _source_fields(source):
    return source.fields() if source is not None else QgsFields()


class UrbanHeatComfortRiskAlgorithm(QgsProcessingAlgorithm):
    STUDY_AREA = "STUDY_AREA"
    BUILDINGS = "BUILDINGS"
    IMPERVIOUS = "IMPERVIOUS"
    GREEN = "GREEN"
    WATER = "WATER"
    VULNERABLE = "VULNERABLE"
    CELL_SIZE = "CELL_SIZE"
    COOLING_DISTANCE = "COOLING_DISTANCE"
    IMPERVIOUS_WEIGHT = "IMPERVIOUS_WEIGHT"
    GREEN_DEFICIT_WEIGHT = "GREEN_DEFICIT_WEIGHT"
    BUILDING_WEIGHT = "BUILDING_WEIGHT"
    VULNERABILITY_WEIGHT = "VULNERABILITY_WEIGHT"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_PRIORITY = "OUTPUT_PRIORITY"
    OUTPUT_EXPOSED = "OUTPUT_EXPOSED"

    def tr(self, string):
        return string

    def createInstance(self):
        return UrbanHeatComfortRiskAlgorithm()

    def name(self):
        return "urban_heat_comfort_risk"

    def displayName(self):
        return self.tr("Urban Heat Comfort Risk (screening)")

    def group(self):
        return self.tr("2 - Heat: comfort and exposure")

    def groupId(self):
        return "planx_urban_resilience_heat"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Urban Heat Comfort Risk</h3>
            <p>Offline-first screening model for urban heat exposure and cooling priority mapping. It combines impervious surface share, building density, green/cooling deficit, and optional vulnerable assets into a 0-100 heat risk score.</p>
            <p>This is a planning-support index, not a microclimate simulation.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.STUDY_AREA, self.tr("Study area (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.BUILDINGS, self.tr("Buildings (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.IMPERVIOUS, self.tr("Roads / hardscape / impervious surfaces (optional)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.GREEN, self.tr("Green areas / tree canopies (optional)"), [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.WATER, self.tr("Water / cooling areas (optional)"), [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.VULNERABLE, self.tr("Vulnerable facilities or population points (optional)"), [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE, self.tr("Grid cell size (map units)"), QgsProcessingParameterNumber.Double, defaultValue=100.0, minValue=5.0))
        self.addParameter(QgsProcessingParameterNumber(self.COOLING_DISTANCE, self.tr("Maximum walking distance to cooling/green area"), QgsProcessingParameterNumber.Double, defaultValue=400.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(self.IMPERVIOUS_WEIGHT, self.tr("Impervious surface weight"), QgsProcessingParameterNumber.Double, defaultValue=0.30, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.GREEN_DEFICIT_WEIGHT, self.tr("Green deficit / cooling distance weight"), QgsProcessingParameterNumber.Double, defaultValue=0.30, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.BUILDING_WEIGHT, self.tr("Building density weight"), QgsProcessingParameterNumber.Double, defaultValue=0.25, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.VULNERABILITY_WEIGHT, self.tr("Vulnerable asset exposure weight"), QgsProcessingParameterNumber.Double, defaultValue=0.15, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_GRID, self.tr("Heat risk grid")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_PRIORITY, self.tr("Priority cooling zones")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_EXPOSED, self.tr("Exposed buildings / vulnerable assets")))

    def processAlgorithm(self, parameters, context, feedback):
        study = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        buildings = self.parameterAsSource(parameters, self.BUILDINGS, context)
        impervious = self.parameterAsSource(parameters, self.IMPERVIOUS, context)
        green = self.parameterAsSource(parameters, self.GREEN, context)
        water = self.parameterAsSource(parameters, self.WATER, context)
        vulnerable = self.parameterAsSource(parameters, self.VULNERABLE, context)
        cell_size = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        cooling_distance = self.parameterAsDouble(parameters, self.COOLING_DISTANCE, context)
        w_imperv = self.parameterAsDouble(parameters, self.IMPERVIOUS_WEIGHT, context)
        w_green = self.parameterAsDouble(parameters, self.GREEN_DEFICIT_WEIGHT, context)
        w_build = self.parameterAsDouble(parameters, self.BUILDING_WEIGHT, context)
        w_vuln = self.parameterAsDouble(parameters, self.VULNERABILITY_WEIGHT, context)
        weight_sum = max(w_imperv + w_green + w_build + w_vuln, 0.0001)

        study_union = _union(study)
        building_union = _union(buildings)
        impervious_union = _union(impervious)
        green_union = _union(green)
        water_union = _union(water)
        cooling_union = None
        if green_union and water_union:
            cooling_union = QgsGeometry.unaryUnion([green_union, water_union]).makeValid()
        else:
            cooling_union = green_union or water_union
        vulnerable_features = _features(vulnerable)
        vulnerable_index = QgsSpatialIndex(vulnerable_features) if vulnerable_features else None

        fields = QgsFields()
        for name in ("cell_id", "imperv", "build_dens", "green_share", "cool_dist", "vuln_count", "heat_score", "risk_class"):
            field_type = QVariant.String if name == "risk_class" else QVariant.Double
            if name in ("cell_id", "vuln_count"):
                field_type = QVariant.Int
            fields.append(QgsField(name, field_type))
        (grid_sink, grid_id) = self.parameterAsSink(parameters, self.OUTPUT_GRID, context, fields, QgsWkbTypes.Polygon, study.sourceCrs())
        (priority_sink, priority_id) = self.parameterAsSink(parameters, self.OUTPUT_PRIORITY, context, fields, QgsWkbTypes.Polygon, study.sourceCrs())

        exposed_fields = QgsFields()
        exposed_fields.append(QgsField("asset_type", QVariant.String))
        exposed_fields.append(QgsField("heat_score", QVariant.Double))
        exposed_fields.append(QgsField("risk_class", QVariant.String))
        (exposed_sink, exposed_id) = self.parameterAsSink(parameters, self.OUTPUT_EXPOSED, context, exposed_fields, QgsWkbTypes.Point, study.sourceCrs())

        extent = study.sourceExtent()
        x = extent.xMinimum()
        cell_id = 0
        total_cols = max(1, int((extent.xMaximum() - extent.xMinimum()) / cell_size) + 1)
        total_rows = max(1, int((extent.yMaximum() - extent.yMinimum()) / cell_size) + 1)
        total = total_cols * total_rows

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
                if clipped.isEmpty():
                    y += cell_size
                    cell_id += 1
                    continue
                centroid = clipped.centroid()
                imperv_share = max(_area_share(clipped, impervious_union), _area_share(clipped, None))
                building_share = _area_share(clipped, building_union)
                green_share = _area_share(clipped, green_union)
                cooling_score = _distance_score(centroid, cooling_union, cooling_distance)
                green_deficit = _clamp((1.0 - green_share) * 100.0)
                vuln_count = 0
                if vulnerable_index:
                    for fid in vulnerable_index.intersects(clipped.boundingBox()):
                        feature = next((f for f in vulnerable_features if f.id() == fid), None)
                        if feature and feature.geometry().intersects(clipped):
                            vuln_count += 1
                vuln_score = _clamp(vuln_count * 20.0)
                heat_score = (
                    imperv_share * 100.0 * w_imperv
                    + building_share * 100.0 * w_build
                    + ((green_deficit + cooling_score) * 0.5) * w_green
                    + vuln_score * w_vuln
                ) / weight_sum
                heat_score = _clamp(heat_score)
                risk = _risk_class(heat_score)
                attrs = [cell_id, imperv_share, building_share, green_share, cooling_score, vuln_count, heat_score, risk]
                feat = QgsFeature(fields)
                feat.setGeometry(clipped)
                feat.setAttributes(attrs)
                grid_sink.addFeature(feat, QgsFeatureSink.FastInsert)
                if heat_score >= 55:
                    priority_sink.addFeature(feat, QgsFeatureSink.FastInsert)
                feedback.setProgress(int(min(100, cell_id / total * 100)))
                y += cell_size
                cell_id += 1
            x += cell_size

        for source, asset_type in ((buildings, "building"), (vulnerable, "vulnerable_asset")):
            for feature in _features(source):
                point = feature.geometry().centroid()
                score = _distance_score(point, cooling_union, cooling_distance)
                if score < 55:
                    continue
                out = QgsFeature(exposed_fields)
                out.setGeometry(point)
                out.setAttributes([asset_type, score, _risk_class(score)])
                exposed_sink.addFeature(out, QgsFeatureSink.FastInsert)

        return {
            self.OUTPUT_GRID: grid_id,
            self.OUTPUT_PRIORITY: priority_id,
            self.OUTPUT_EXPOSED: exposed_id,
        }
