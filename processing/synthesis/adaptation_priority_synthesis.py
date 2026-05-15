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
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _priority_class(score):
    if score >= 75:
        return "Immediate"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Medium"
    return "Monitor"


def _numeric(feature, field_name):
    if not field_name:
        return 0.0
    try:
        value = feature[field_name]
        if value in (None, ""):
            return 0.0
        return float(value)
    except (KeyError, TypeError, ValueError):
        return 0.0


class AdaptationPrioritySynthesisAlgorithm(QgsProcessingAlgorithm):
    UNITS = "UNITS"
    HEAT_FIELD = "HEAT_FIELD"
    FLOOD_FIELD = "FLOOD_FIELD"
    SOCIAL_FIELD = "SOCIAL_FIELD"
    AIR_FIELD = "AIR_FIELD"
    ACCESS_FIELD = "ACCESS_FIELD"
    DROUGHT_FIELD = "DROUGHT_FIELD"
    WEIGHT_HEAT = "WEIGHT_HEAT"
    WEIGHT_FLOOD = "WEIGHT_FLOOD"
    WEIGHT_SOCIAL = "WEIGHT_SOCIAL"
    WEIGHT_AIR = "WEIGHT_AIR"
    WEIGHT_ACCESS = "WEIGHT_ACCESS"
    WEIGHT_DROUGHT = "WEIGHT_DROUGHT"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return AdaptationPrioritySynthesisAlgorithm()

    def name(self):
        return "climate_adaptation_priority_synthesis"

    def displayName(self):
        return self.tr("Climate Adaptation Priority Synthesis")

    def group(self):
        return self.tr("8 - Synthesis: adaptation priorities")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Climate Adaptation Priority Synthesis</h3>
            <p>Combines existing 0-100 risk or deficit fields into one adaptation priority score. Use it on planning units, grid cells or neighborhood polygons after joining outputs from other PlanX Urban Resilience modules.</p>
            <p>The algorithm does not spatially join layers by itself; prepare one polygon layer that already contains the fields you want to synthesize.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.UNITS, self.tr("Planning units / joined risk layer (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        for key, label in (
            (self.HEAT_FIELD, "Heat score field (optional)"),
            (self.FLOOD_FIELD, "Flood score field (optional)"),
            (self.SOCIAL_FIELD, "Social vulnerability score field (optional)"),
            (self.AIR_FIELD, "Air exposure score field (optional)"),
            (self.ACCESS_FIELD, "Accessibility deficit score field (optional)"),
            (self.DROUGHT_FIELD, "Green infrastructure stress score field (optional)"),
        ):
            self.addParameter(QgsProcessingParameterField(key, self.tr(label), parentLayerParameterName=self.UNITS, optional=True, type=QgsProcessingParameterField.Numeric))
        for key, label, default in (
            (self.WEIGHT_HEAT, "Heat weight", 0.20),
            (self.WEIGHT_FLOOD, "Flood weight", 0.20),
            (self.WEIGHT_SOCIAL, "Social vulnerability weight", 0.20),
            (self.WEIGHT_AIR, "Air exposure weight", 0.15),
            (self.WEIGHT_ACCESS, "Accessibility deficit weight", 0.15),
            (self.WEIGHT_DROUGHT, "Green infrastructure stress weight", 0.10),
        ):
            self.addParameter(QgsProcessingParameterNumber(key, self.tr(label), QgsProcessingParameterNumber.Double, defaultValue=default, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Climate adaptation priority layer")))

    def processAlgorithm(self, parameters, context, feedback):
        units = self.parameterAsSource(parameters, self.UNITS, context)
        fields_by_key = {
            "heat": self.parameterAsString(parameters, self.HEAT_FIELD, context),
            "flood": self.parameterAsString(parameters, self.FLOOD_FIELD, context),
            "social": self.parameterAsString(parameters, self.SOCIAL_FIELD, context),
            "air": self.parameterAsString(parameters, self.AIR_FIELD, context),
            "access": self.parameterAsString(parameters, self.ACCESS_FIELD, context),
            "drought": self.parameterAsString(parameters, self.DROUGHT_FIELD, context),
        }
        weights = {
            "heat": self.parameterAsDouble(parameters, self.WEIGHT_HEAT, context),
            "flood": self.parameterAsDouble(parameters, self.WEIGHT_FLOOD, context),
            "social": self.parameterAsDouble(parameters, self.WEIGHT_SOCIAL, context),
            "air": self.parameterAsDouble(parameters, self.WEIGHT_AIR, context),
            "access": self.parameterAsDouble(parameters, self.WEIGHT_ACCESS, context),
            "drought": self.parameterAsDouble(parameters, self.WEIGHT_DROUGHT, context),
        }

        out_fields = QgsFields()
        for field in units.fields():
            out_fields.append(field)
        out_fields.append(QgsField("adapt_score", QVariant.Double))
        out_fields.append(QgsField("adapt_class", QVariant.String))
        out_fields.append(QgsField("drivers", QVariant.String))
        out_fields.append(QgsField("missing", QVariant.String))
        (sink, sink_id) = self.parameterAsSink(parameters, self.OUTPUT, context, out_fields, QgsWkbTypes.Polygon, units.sourceCrs())

        features = [feature for feature in units.getFeatures() if feature.hasGeometry()]
        total = max(len(features), 1)
        for idx, feature in enumerate(features):
            if feedback.isCanceled():
                break
            weighted = 0.0
            weight_sum = 0.0
            driver_scores = []
            missing = []
            for key, field_name in fields_by_key.items():
                weight = weights[key]
                if weight <= 0:
                    continue
                if not field_name:
                    missing.append(key)
                    continue
                score = _clamp(_numeric(feature, field_name))
                weighted += score * weight
                weight_sum += weight
                driver_scores.append((key, score))
            adapt_score = _clamp(weighted / max(weight_sum, 0.0001))
            top_drivers = ", ".join([f"{name}:{round(score, 1)}" for name, score in sorted(driver_scores, key=lambda item: item[1], reverse=True)[:3]])
            out = QgsFeature(out_fields)
            out.setGeometry(feature.geometry())
            out.setAttributes(feature.attributes() + [adapt_score, _priority_class(adapt_score), top_drivers, ", ".join(missing) or "ok"])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: sink_id}
