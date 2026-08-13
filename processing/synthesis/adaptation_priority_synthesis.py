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

from .._helpers import clamp, intervention_priority_class


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


from .._mixins import GROUP_SYNTHESIS, GroupMixin, HelpUrlMixin  # noqa: E402


class AdaptationPrioritySynthesisAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_SYNTHESIS
    ICON = "tool_climate_adaptation_priority_synthesis.png"
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

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Climate Adaptation Priority Synthesis</h3>
            <p>Linear weighted-sum multi-criteria composite - the simplest, most
            transparent form of MCDA, following the same additive aggregation logic as
            the ISO 14044 lifecycle-impact convention. Combines up to six 0-100
            hazard fields (heat, flood, social, air, access, drought) with defaults
            (0.20/0.20/0.20/0.15/0.15/0.10) chosen so no single hazard dominates by
            construction - the weights are the explicit, auditable policy choice.</p>
            <p>Linear weighted-sum means full compensability: a very low flood score
            can offset a very high heat score. Missing fields are excluded and their
            weight redistributed across present fields - a unit with only 2 of 6
            fields still gets a score, but check the missing field before treating it
            as equally reliable to a fully-populated unit. All six inputs must already
            be on a common 0-100 scale; this tool performs no normalisation.</p>
            <p>How to read the results
            - adapt_score: the composite ranking number, 0-100.
            - adapt_class: Immediate (&gt;=75) / High (55-74) / Medium (35-54) /
            Monitor (&lt;35).
            - drivers: which hazard(s) actually drove the score - "flood:92.1,
            heat:45.0" means a flood priority, not a heat one; use this to assign
            hazard-specific interventions rather than generic ones.
            - missing: fields absent or zero-weighted - a reliability check, not a
            score component.</p>
            <p>Using the results: this algorithm does not spatially join layers by
            itself - prepare one polygon layer via Join Hazard Scores to Planning
            Units first. Feed adapt_score into Equity-Adjusted Priority to re-rank by
            vulnerability, or into Risk-Recovery Priority Matrix with a recovery score
            to find high-hazard + low-recovery gaps. Where the breakdown of which
            hazard drives the score matters more than the single number, use
            Multi-Hazard Composite Index instead - it keeps the diagnostic breakdown
            visible rather than collapsing it away.</p>
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
                score = clamp(_numeric(feature, field_name))
                weighted += score * weight
                weight_sum += weight
                driver_scores.append((key, score))
            adapt_score = clamp(weighted / max(weight_sum, 0.0001))
            top_drivers = ", ".join([f"{name}:{round(score, 1)}" for name, score in sorted(driver_scores, key=lambda item: item[1], reverse=True)[:3]])
            out = QgsFeature(out_fields)
            out.setGeometry(feature.geometry())
            out.setAttributes(feature.attributes() + [adapt_score, intervention_priority_class(adapt_score), top_drivers, ", ".join(missing) or "ok"])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: sink_id}
