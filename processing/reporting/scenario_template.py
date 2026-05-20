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


class ScenarioTemplateAlgorithm(QgsProcessingAlgorithm):
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

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Scenario Planning Template</h3>
            <p>Creates a scenario-editing layer from any planning unit or risk layer. It copies the input features and adds baseline/proposed score fields, scenario metadata, an intervention type, expected reduction and edit notes.</p>
            <p>Use the output as a clean worksheet before running Scenario Comparison / Delta Map. Lower scores are assumed to be better.</p>
            """
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
                feature.attributes()
                + [
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
