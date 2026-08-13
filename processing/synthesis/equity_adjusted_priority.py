# -*- coding: utf-8 -*-
"""Equity-Adjusted Adaptation Priority.

Pure adaptation priority highlights the highest hazard exposure — which can
correlate with wealthier, better-instrumented neighborhoods. This algorithm
multiplies the hazard score by an equity factor derived from the Social
Vulnerability Index, so units that are both high-risk **and** high-vulnerability
rise to the top.

Inputs:
  - planning units with a hazard/composite score field (0-100)
  - SVI field on the same layer (0-100)
  - equity weight (0..1): controls how much vulnerability amplifies priority

Equity factor:
    factor = 1 + equity_weight * (svi / 100)
    adjusted = clamp(hazard * factor, 0..100 * (1 + equity_weight))
    normalized = 100 * adjusted / max_possible

Output fields:
  - eq_hazard          (copy of source hazard score, validated)
  - eq_svi             (copy of source SVI, validated)
  - eq_factor          (1 + w*svi/100)
  - eq_adjusted_raw    (hazard * factor)
  - eq_adjusted_score  (0-100 after normalization)
  - eq_priority_class  (Very High / High / Moderate / Low based on adjusted)
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

from .._helpers import clamp, composite_risk_class


from .._mixins import GROUP_SYNTHESIS, GroupMixin, HelpUrlMixin  # noqa: E402


class EquityAdjustedPriorityAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_SYNTHESIS
    ICON = "tool_equity_adjusted_priority.png"
    INPUT = "INPUT"
    HAZARD_FIELD = "HAZARD_FIELD"
    SVI_FIELD = "SVI_FIELD"
    EQUITY_WEIGHT = "EQUITY_WEIGHT"
    OUTPUT = "OUTPUT"

    OUT_HAZARD = "eq_hazard"
    OUT_SVI = "eq_svi"
    OUT_FACTOR = "eq_factor"
    OUT_RAW = "eq_adjusted_raw"
    OUT_SCORE = "eq_adjusted_score"
    OUT_CLASS = "eq_priority_class"

    def tr(self, string):
        return string

    def createInstance(self):
        return EquityAdjustedPriorityAlgorithm()

    def name(self):
        return "equity_adjusted_priority"

    def displayName(self):
        return self.tr("Equity-Adjusted Adaptation Priority")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Equity-Adjusted Adaptation Priority</h3>
            <p>Re-ranks adaptation priority by multiplying a hazard/composite score
            (0-100) with an equity factor derived from the Social Vulnerability Index
            (0-100), following the distributive-justice framework for climate
            adaptation (Shi et al., 2016): resources should be allocated proportional
            to both physical exposure AND social vulnerability, since treating hazard
            score alone as the ranking criterion implicitly assumes every unit has
            equal capacity to respond.</p>
            <p><b>Equity factor:</b> <code>1 + w * (SVI / 100)</code></p>
            <ul>
              <li><b>w = 0</b> -> result equals the raw hazard score (no adjustment, the neutral default).</li>
              <li><b>w = 1</b> -> a fully vulnerable unit doubles in priority.</li>
              <li><b>w = 0.5</b> (default) -> SVI=100 gets a 50% boost.</li>
            </ul>
            <p>The adjustment is multiplicative, not additive: a unit with a very low
            hazard score gains little absolute priority even at high SVI, since
            there's little to amplify - this tool re-ranks AMONG already-hazardous
            units by vulnerability, it does not manufacture priority from
            vulnerability alone. SVI must already be joined onto the same layer;
            this tool computes no vulnerability score of its own.</p>
            <p>How to read the results: units where eq_adjusted_score exceeds
            eq_hazard by more than 10 points are the equity finding - physically
            moderate hazard but high social vulnerability pushed them up the list.</p>
            <p>Using the results: use w=0.5 for balanced prioritisation, w=1.0 for a
            strongly equity-first ranking - but treat the weight choice itself as a
            policy decision for affected communities to weigh in on, not a purely
            technical one. Adjusted score is normalized back to 0-100 so it remains
            comparable across runs and joinable with other resilience layers.</p>
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
            self.tr("Hazard / composite score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SVI_FIELD,
            self.tr("Social vulnerability score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.EQUITY_WEIGHT,
            self.tr("Equity weight (0=ignore SVI, 1=double at SVI=100)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.5, minValue=0.0, maxValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Equity-adjusted priority")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Planning units layer is required.")

        hazard_field = self.parameterAsString(parameters, self.HAZARD_FIELD, context)
        svi_field = self.parameterAsString(parameters, self.SVI_FIELD, context)
        equity_w = self.parameterAsDouble(parameters, self.EQUITY_WEIGHT, context)
        max_possible = 100.0 * (1.0 + equity_w)

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_HAZARD, QVariant.Double),
            (self.OUT_SVI, QVariant.Double),
            (self.OUT_FACTOR, QVariant.Double),
            (self.OUT_RAW, QVariant.Double),
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
            hazard = clamp(feature.attribute(hazard_field)) or 0.0
            svi = clamp(feature.attribute(svi_field)) or 0.0
            factor = 1.0 + equity_w * (svi / 100.0)
            raw = hazard * factor
            score = clamp(100.0 * raw / max_possible) or 0.0

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feature.geometry())
            new_attrs = list(feature.attributes())
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([hazard, svi, factor, raw, score, composite_risk_class(score)])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: dest_id}
