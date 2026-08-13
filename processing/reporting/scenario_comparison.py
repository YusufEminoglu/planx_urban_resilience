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
)

from .._helpers import clamp


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


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class ScenarioComparisonAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_resilience_scenario_comparison.png"
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

    def shortHelpString(self):
        return self.tr(
            "<h3>Scenario Comparison / Delta Map</h3> <p>Compares two 0-100 score fields on the same "
            "layer - baseline vs. proposed intervention, or two alternative planning scenarios - a "
            "core methodology in sustainability assessment (Swart et al., 2004; Xiang &amp; Clarke, "
            '2003), following the "comparative statics" tradition of subtracting two spatial fields '
            "and mapping the residual. The default 5-point threshold avoids Openshaw &amp; Taylor's "
            '(1979) "small change problem": without a threshold every unit shows some delta, most of '
            "it noise.</p> <p>The output adds baseline, scenario, delta, absolute delta, percent "
            "change and an improved/stable/worsened class plus an action hint. Lower scores are "
            "assumed to be better (this suite's 0-100 scores are always \"higher = worse\" risk "
            "scores). A negative delta therefore means improvement.</p> <p>How to read the results - "
            "change_cls = Improved with a large negative delta: a success-story unit to document and "
            "replicate. - change_cls = Worsened: review the scenario parameters - this may be a "
            "realistic future-worsening (e.g. climate projection) or a modelling error. - Use percent "
            "change for ranking, absolute delta for mapping.</p> <p>Using the results: this is a "
            "same-moment (cross-sectional) comparison of two alternatives, not a longitudinal one - "
            "use Resilience Time-Series Tracker for comparing across real time instead. Feed the "
            "output into Bivariate Choropleth Symbology with baseline and delta as axes to show "
            '"where was it high AND got worse".</p>'
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
            baseline = clamp(_numeric(feature, baseline_field))
            scenario = clamp(_numeric(feature, scenario_field))
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
