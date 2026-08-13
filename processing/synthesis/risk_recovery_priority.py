# -*- coding: utf-8 -*-
"""Risk-Recovery Priority Matrix.

Surfaces planning units that are simultaneously high-hazard (or high
adaptation priority) and low recovery capacity — the combination that
warrants the most urgent intervention.

    priority_raw = hazard_score * (1 + w * deficit / 100)
    deficit = 100 - recovery_score

Outputs:
  - rr_hazard, rr_recovery, rr_deficit, rr_factor
  - rr_priority_score (0-100 normalized)
  - rr_priority_class (Immediate / High / Medium / Monitor)
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
)

from .._helpers import clamp, intervention_priority_class


def _score(feature, field_name):
    return clamp(feature.attribute(field_name)) if field_name else None


from .._mixins import GROUP_SYNTHESIS, GroupMixin, HelpUrlMixin  # noqa: E402


class RiskRecoveryPriorityAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_SYNTHESIS
    ICON = "tool_risk_recovery_priority_matrix.png"
    INPUT = "INPUT"
    HAZARD_FIELD = "HAZARD_FIELD"
    RECOVERY_FIELD = "RECOVERY_FIELD"
    RECOVERY_WEIGHT = "RECOVERY_WEIGHT"
    OUTPUT = "OUTPUT"

    OUT_HAZARD = "rr_hazard"
    OUT_RECOVERY = "rr_recovery"
    OUT_DEFICIT = "rr_deficit"
    OUT_FACTOR = "rr_factor"
    OUT_SCORE = "rr_priority_score"
    OUT_CLASS = "rr_priority_class"

    def tr(self, string):
        return string

    def createInstance(self):
        return RiskRecoveryPriorityAlgorithm()

    def name(self):
        return "risk_recovery_priority_matrix"

    def displayName(self):
        return self.tr("Risk-Recovery Priority Matrix")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Risk-Recovery Priority Matrix</h3>
            <p>Combines a hazard or adaptation priority score (0-100) with a
            recovery capacity score (0-100) into a bivariate risk matrix - the
            standard ISO 31000 decision-support pattern where a two-axis grid
            replaces a single number specifically so a decision-maker can see WHY a
            unit is high-priority, not just THAT it is. The multiplicative form
            follows the "risk = hazard x vulnerability / coping capacity" convention
            of the UNDRR risk-assessment framework - structurally the same
            amplifier pattern as Equity-Adjusted Priority, applied to recovery
            capacity instead of social vulnerability (the two tools can be chained
            in either order).</p>
            <p><code>priority = hazard * (1 + w * (100 - recovery) / 100)</code></p>
            <p>The two input scores are assumed independent - in reality
            well-resourced areas often also have lower physical exposure, which this
            multiplicative form does not detect or correct for. Recovery capacity is
            a single scalar (typically rc_score from Recovery Capacity Index), so any
            nuance about which recovery dimension is weakest is lost by the time it
            reaches this tool.</p>
            <p>Using the results: use the matrix to triage a long list of planning
            units into four quadrants - Act now (high hazard/low recovery), Prepare
            (high/high), Support recovery (low/low), Monitor (low hazard/high
            recovery). Check for correlation between your hazard and recovery fields
            first - a spuriously high priority can result from two correlated inputs
            moving together rather than genuinely compounding risk.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT,
            self.tr("Planning units"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.HAZARD_FIELD,
            self.tr("Hazard / adaptation score (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RECOVERY_FIELD,
            self.tr("Recovery capacity score (0-100, e.g. rc_score)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.RECOVERY_WEIGHT,
            self.tr("Recovery deficit weight (0=ignore, 1=double at recovery=0)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.5,
            minValue=0.0,
            maxValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Risk-recovery priority"),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Planning units layer is required.")

        hazard_field = self.parameterAsString(parameters, self.HAZARD_FIELD, context)
        recovery_field = self.parameterAsString(parameters, self.RECOVERY_FIELD, context)
        weight = self.parameterAsDouble(parameters, self.RECOVERY_WEIGHT, context)
        max_raw = 100.0 * (1.0 + weight)

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_HAZARD, QVariant.Double),
            (self.OUT_RECOVERY, QVariant.Double),
            (self.OUT_DEFICIT, QVariant.Double),
            (self.OUT_FACTOR, QVariant.Double),
            (self.OUT_SCORE, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        total = max(source.featureCount(), 1)
        for idx, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            hazard = _score(feature, hazard_field) or 0.0
            recovery = _score(feature, recovery_field) or 0.0
            deficit = 100.0 - recovery
            factor = 1.0 + weight * (deficit / 100.0)
            raw = hazard * factor
            score = clamp(100.0 * raw / max_raw) or 0.0

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feature.geometry())
            attrs = list(feature.attributes())
            while len(attrs) < out_fields.size() - 6:
                attrs.append(None)
            attrs.extend([hazard, recovery, deficit, factor, score, intervention_priority_class(score)])
            new_feat.setAttributes(attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: dest_id}
