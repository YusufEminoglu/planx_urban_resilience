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


def _area_share(geom, target_union):
    if target_union is None or target_union.isEmpty() or geom.area() <= 0:
        return 0.0
    inter = geom.intersection(target_union)
    if inter.isEmpty():
        return 0.0
    return clamp(inter.area() / geom.area(), 0.0, 1.0)


def _distance_score(geom, target_union, max_distance, missing_score=75.0):
    if target_union is None or target_union.isEmpty():
        return missing_score
    distance = geom.centroid().distance(target_union)
    return clamp((distance / max(max_distance, 1.0)) * 100.0)


def _count_near(geom, features, index):
    if not features or index is None:
        return 0
    feature_by_id = {feature.id(): feature for feature in features}
    count = 0
    for fid in index.intersects(geom.boundingBox()):
        feature = feature_by_id.get(fid)
        if feature and feature.geometry().intersects(geom):
            count += 1
    return count


from .._mixins import HelpUrlMixin  # noqa: E402




class GreenInfrastructureStressAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    GREEN = "GREEN"
    STUDY_AREA = "STUDY_AREA"
    IMPERVIOUS = "IMPERVIOUS"
    WATER = "WATER"
    TREES = "TREES"
    MAX_WATER_DISTANCE = "MAX_WATER_DISTANCE"
    IMPERVIOUS_WEIGHT = "IMPERVIOUS_WEIGHT"
    WATER_WEIGHT = "WATER_WEIGHT"
    SIZE_WEIGHT = "SIZE_WEIGHT"
    TREE_WEIGHT = "TREE_WEIGHT"
    OUTPUT_STRESS = "OUTPUT_STRESS"
    OUTPUT_PRIORITY = "OUTPUT_PRIORITY"

    def tr(self, string):
        return string

    def createInstance(self):
        return GreenInfrastructureStressAlgorithm()

    def name(self):
        return "green_infrastructure_drought_stress"

    def displayName(self):
        return self.tr("Drought and Green Infrastructure Stress")

    def group(self):
        return self.tr("7 - Drought: green infrastructure stress")

    def groupId(self):
        return "planx_urban_resilience_drought"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Drought and Green Infrastructure Stress</h3>
            <p>Ranks parks, green patches or tree canopy polygons by drought/stress sensitivity using impervious context, distance to water, patch size and optional tree points.</p>
            <p>This is an ecological planning-support index, not a plant physiology or irrigation model.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.GREEN, self.tr("Green infrastructure / parks / canopy patches (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.STUDY_AREA, self.tr("Study area (optional polygon)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.IMPERVIOUS, self.tr("Impervious surfaces / roads / hardscape (optional polygon)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.WATER, self.tr("Water / blue infrastructure (optional line or polygon)"), [QgsProcessing.TypeVectorLine, QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.TREES, self.tr("Tree points (optional)"), [QgsProcessing.TypeVectorPoint], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.MAX_WATER_DISTANCE, self.tr("Maximum water access distance"), QgsProcessingParameterNumber.Double, defaultValue=500.0, minValue=10.0))
        self.addParameter(QgsProcessingParameterNumber(self.IMPERVIOUS_WEIGHT, self.tr("Impervious context weight"), QgsProcessingParameterNumber.Double, defaultValue=0.35, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.WATER_WEIGHT, self.tr("Water distance weight"), QgsProcessingParameterNumber.Double, defaultValue=0.25, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.SIZE_WEIGHT, self.tr("Small patch sensitivity weight"), QgsProcessingParameterNumber.Double, defaultValue=0.25, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.TREE_WEIGHT, self.tr("Low tree density weight"), QgsProcessingParameterNumber.Double, defaultValue=0.15, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_STRESS, self.tr("Green infrastructure stress index")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_PRIORITY, self.tr("High-priority green infrastructure patches")))

    def processAlgorithm(self, parameters, context, feedback):
        green = self.parameterAsSource(parameters, self.GREEN, context)
        study = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        impervious = self.parameterAsSource(parameters, self.IMPERVIOUS, context)
        water = self.parameterAsSource(parameters, self.WATER, context)
        trees = self.parameterAsSource(parameters, self.TREES, context)
        max_water_distance = self.parameterAsDouble(parameters, self.MAX_WATER_DISTANCE, context)
        w_imperv = self.parameterAsDouble(parameters, self.IMPERVIOUS_WEIGHT, context)
        w_water = self.parameterAsDouble(parameters, self.WATER_WEIGHT, context)
        w_size = self.parameterAsDouble(parameters, self.SIZE_WEIGHT, context)
        w_tree = self.parameterAsDouble(parameters, self.TREE_WEIGHT, context)
        weight_sum = max(w_imperv + w_water + w_size + w_tree, 0.0001)

        study_union = _union(study)
        impervious_union = _union(impervious)
        water_union = _union(water)
        tree_features = _features(trees)
        tree_index = QgsSpatialIndex()
        if tree_features:
            for f in tree_features:
                tree_index.addFeature(f)
        else:
            tree_index = None
        green_features = _features(green)
        areas = [max(feature.geometry().area(), 0.0) for feature in green_features]
        min_area = min(areas) if areas else 0.0
        max_area = max(areas) if areas else 1.0
        area_range = max(max_area - min_area, 1.0)

        fields = QgsFields()
        for field in green.fields():
            fields.append(field)
        for name in ("imperv_ctx", "water_dist", "size_score", "tree_count", "stress_score", "stress_class"):
            field_type = QVariant.String if name == "stress_class" else QVariant.Double
            if name == "tree_count":
                field_type = QVariant.Int
            fields.append(QgsField(name, field_type))
        (stress_sink, stress_id) = self.parameterAsSink(parameters, self.OUTPUT_STRESS, context, fields, QgsWkbTypes.Polygon, green.sourceCrs())
        (priority_sink, priority_id) = self.parameterAsSink(parameters, self.OUTPUT_PRIORITY, context, fields, QgsWkbTypes.Polygon, green.sourceCrs())

        total = max(len(green_features), 1)
        for idx, feature in enumerate(green_features):
            if feedback.isCanceled():
                break
            geom = feature.geometry().makeValid()
            if study_union and not study_union.isEmpty() and not geom.intersects(study_union):
                continue
            working = geom.intersection(study_union).makeValid() if study_union and not study_union.isEmpty() else geom
            if working.isEmpty():
                continue
            context_buffer = working.buffer(max_water_distance * 0.25, 8)
            imperv_ctx = _area_share(context_buffer, impervious_union) * 100.0
            water_dist = _distance_score(working, water_union, max_water_distance)
            area = max(working.area(), 0.0)
            size_score = clamp((1.0 - ((area - min_area) / area_range)) * 100.0)
            tree_count = _count_near(working, tree_features, tree_index)
            tree_density_score = clamp(100.0 - tree_count * 10.0)
            stress_score = clamp((imperv_ctx * w_imperv + water_dist * w_water + size_score * w_size + tree_density_score * w_tree) / weight_sum)
            stress_class = composite_risk_class(stress_score)
            out = QgsFeature(fields)
            out.setGeometry(working)
            out.setAttributes(feature.attributes() + [imperv_ctx, water_dist, size_score, tree_count, stress_score, stress_class])
            stress_sink.addFeature(out, QgsFeatureSink.FastInsert)
            if stress_score >= 55:
                priority_sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT_STRESS: stress_id, self.OUTPUT_PRIORITY: priority_id}
