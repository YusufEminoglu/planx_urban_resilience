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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)

from .._helpers import clamp


def _numeric(feature, field_name, fallback):
    if not field_name:
        return fallback
    try:
        value = feature[field_name]
        if value in (None, ""):
            return fallback
        return float(value)
    except (KeyError, TypeError, ValueError):
        return fallback


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class ScenarioTemplateAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_scenario_planning_template.png"
    INPUT = "INPUT"
    BASE_SCORE_FIELD = "BASE_SCORE_FIELD"
    DEFAULT_BASE_SCORE = "DEFAULT_BASE_SCORE"
    SCENARIO_NAME = "SCENARIO_NAME"
    INTERVENTION_TYPE = "INTERVENTION_TYPE"
    EXPECTED_REDUCTION = "EXPECTED_REDUCTION"
    OUTPUT = "OUTPUT"

    INTERVENTIONS = [
        "Green cooling / canopy increase",
        "Flood storage / drainage improvement",
        "Shelter and emergency access improvement",
        "Social support / vulnerable group service",
        "Air exposure mitigation",
        "Drought resilient landscape retrofit",
        "Custom intervention",
    ]

    def tr(self, string):
        return string

    def createInstance(self):
        return ScenarioTemplateAlgorithm()

    def name(self):
        return "scenario_planning_template"

    def displayName(self):
        return self.tr("Scenario Planning Template")

    def shortHelpString(self):
        return self.tr(
            "<h3>Scenario Planning Template</h3> <p>Creates an editable baseline/proposed worksheet "
            "from any planning unit or risk layer, following the participatory scenario-planning "
            "tradition in land-use and climate-adaptation studies (Patel et al., 2007; Kok et al., "
            "2006): rather than prescribing intervention magnitudes, it gives the planner a starting "
            "hypothesis to edit with local knowledge of cost, feasibility and context.</p> "
            "<p>scen_score = base_score x (1 - reduction/100) applies the expected reduction "
            "UNIFORMLY as a deliberately naive starting point - every unit is assumed to respond "
            "identically, which is almost never true. The tool performs no engineering or spatial "
            'validation of the values you enter; edit_status always starts as "draft" as a workflow '
            "marker, not a data-quality signal.</p> <p>Use the output as a clean worksheet before "
            "running Scenario Comparison / Delta Map. Lower scores are assumed to be better.</p> "
            "<p>Using the results: (1) filter by edit_status = 'draft' to find units needing review, "
            "(2) edit scen_score manually where the uniform reduction is unrealistic, (3) document "
            'the reasoning in notes, (4) mark edit_status "reviewed" when done. Ground '
            "EXPECTED_REDUCTION in the relevant hazard tool's own literature (e.g. Bowler et al., "
            "2010, for green-cooling magnitude) rather than guessing a number.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Planning units or scored layer"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(self.BASE_SCORE_FIELD, self.tr("Existing baseline score field (optional)"), parentLayerParameterName=self.INPUT, optional=True, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterNumber(self.DEFAULT_BASE_SCORE, self.tr("Default baseline score if field is empty"), QgsProcessingParameterNumber.Double, defaultValue=50.0, minValue=0.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterString(self.SCENARIO_NAME, self.tr("Scenario name"), defaultValue="Scenario A"))
        self.addParameter(QgsProcessingParameterEnum(self.INTERVENTION_TYPE, self.tr("Default intervention type"), options=self.INTERVENTIONS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(self.EXPECTED_REDUCTION, self.tr("Expected score reduction (%)"), QgsProcessingParameterNumber.Double, defaultValue=15.0, minValue=-100.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Scenario planning template layer")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        base_score_field = self.parameterAsString(parameters, self.BASE_SCORE_FIELD, context)
        default_base = self.parameterAsDouble(parameters, self.DEFAULT_BASE_SCORE, context)
        scenario_name = self.parameterAsString(parameters, self.SCENARIO_NAME, context)
        intervention_idx = self.parameterAsEnum(parameters, self.INTERVENTION_TYPE, context)
        expected_reduction = self.parameterAsDouble(parameters, self.EXPECTED_REDUCTION, context)
        intervention = self.INTERVENTIONS[intervention_idx]

        fields = QgsFields()
        for field in source.fields():
            fields.append(field)
        fields.append(QgsField("scenario", QVariant.String))
        fields.append(QgsField("interv_type", QVariant.String))
        fields.append(QgsField("base_score", QVariant.Double))
        fields.append(QgsField("scen_score", QVariant.Double))
        fields.append(QgsField("exp_reduce", QVariant.Double))
        fields.append(QgsField("edit_status", QVariant.String))
        fields.append(QgsField("notes", QVariant.String))

        (sink, sink_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, source.wkbType(), source.sourceCrs())
        features = [feature for feature in source.getFeatures() if feature.hasGeometry()]
        total = max(len(features), 1)
        for idx, feature in enumerate(features):
            if feedback.isCanceled():
                break
            base_score = clamp(_numeric(feature, base_score_field, default_base))
            scenario_score = clamp(base_score * (1.0 - expected_reduction / 100.0))
            out = QgsFeature(fields)
            out.setGeometry(feature.geometry())
            out.setAttributes(
                [
                    *feature.attributes(),
                    scenario_name,
                    intervention,
                    base_score,
                    scenario_score,
                    expected_reduction,
                    "draft",
                    "Review and edit scenario score before comparison.",
                ]
            )
            sink.addFeature(out, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: sink_id}
