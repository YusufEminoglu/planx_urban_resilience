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


def _numeric(feature, field_name):
    try:
        value = feature[field_name]
        if value in (None, ""):
            return 0.0
        return float(value)
    except (KeyError, TypeError, ValueError):
        return 0.0


def _change_class(delta, threshold):
    if delta <= -threshold:
        return "Improved"
    if delta >= threshold:
        return "Worsened"
    return "Stable"


class ScenarioComparisonAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    BASELINE_FIELD = "BASELINE_FIELD"
    SCENARIO_FIELD = "SCENARIO_FIELD"
    THRESHOLD = "THRESHOLD"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return ScenarioComparisonAlgorithm()

    def name(self):
        return "resilience_scenario_comparison"

    def displayName(self):
        return self.tr("Scenario Comparison / Delta Map")

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Scenario Comparison / Delta Map</h3>
            <p>Compares two 0-100 score fields in the same layer, usually baseline and proposed scenario scores. The output adds baseline, scenario, delta, absolute delta, percent change and an improved/stable/worsened class.</p>
            <p>Lower scores are assumed to be better. A negative delta therefore means improvement.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Planning units with baseline and scenario fields"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(self.BASELINE_FIELD, self.tr("Baseline score field"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterField(self.SCENARIO_FIELD, self.tr("Scenario score field"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterNumber(self.THRESHOLD, self.tr("Meaningful change threshold"), QgsProcessingParameterNumber.Double, defaultValue=5.0, minValue=0.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Scenario comparison layer")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        baseline_field = self.parameterAsString(parameters, self.BASELINE_FIELD, context)
        scenario_field = self.parameterAsString(parameters, self.SCENARIO_FIELD, context)
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context)

        fields = QgsFields()
        for field in source.fields():
            fields.append(field)
        fields.append(QgsField("base_score", QVariant.Double))
        fields.append(QgsField("scen_score", QVariant.Double))
        fields.append(QgsField("delta", QVariant.Double))
        fields.append(QgsField("abs_delta", QVariant.Double))
        fields.append(QgsField("pct_change", QVariant.Double))
        fields.append(QgsField("change_cls", QVariant.String))
        fields.append(QgsField("action_hint", QVariant.String))
        (sink, sink_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, source.wkbType(), source.sourceCrs())

        features = [feature for feature in source.getFeatures() if feature.hasGeometry()]
        total = max(len(features), 1)
        for idx, feature in enumerate(features):
            if feedback.isCanceled():
                break
            baseline = _clamp(_numeric(feature, baseline_field))
            scenario = _clamp(_numeric(feature, scenario_field))
            delta = scenario - baseline
            pct_change = 0.0 if baseline == 0 else (delta / baseline) * 100.0
            change_cls = _change_class(delta, threshold)
            if change_cls == "Improved":
                action_hint = "Document and replicate"
            elif change_cls == "Worsened":
                action_hint = "Review scenario drivers"
            else:
                action_hint = "Monitor"
            out = QgsFeature(fields)
            out.setGeometry(feature.geometry())
            out.setAttributes(feature.attributes() + [baseline, scenario, delta, abs(delta), pct_change, change_cls, action_hint])
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: sink_id}
