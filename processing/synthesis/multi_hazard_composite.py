# -*- coding: utf-8 -*-
"""Multi-Hazard Composite Index.

For each planning unit, combine up to N hazard score fields (0-100) into:
  - composite_score (weighted mean, clamped 0-100)
  - composite_class (Very High / High / Moderate / Low)
  - dominant_hazard  (field name with the largest weighted contribution)
  - diversity_index  (Shannon entropy of normalized weighted scores, 0-100)
  - top_drivers      (CSV of up to 3 highest-contributing field names)
  - data_gap_count   (number of missing/null hazard fields for the feature)

Use case: Adaptation Priority Synthesis collapses to one score and hides
which hazard is driving it. This algorithm keeps the breakdown so planners
can answer "is this unit heat-dominated or multi-stressed?".
"""
from __future__ import annotations

import math

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
    QgsProcessingParameterString,
)

from .._helpers import clamp, composite_risk_class, parse_weights_csv


def _shannon_index(weighted_scores: list[float]) -> float:
    """Normalize and return Shannon entropy scaled 0-100.

    Single-hazard concentration -> 0; perfectly equal across N hazards -> 100.
    """
    positive = [s for s in weighted_scores if s > 0]
    n = len(positive)
    if n <= 1:
        return 0.0
    total = sum(positive)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for s in positive:
        p = s / total
        entropy -= p * math.log(p)
    max_entropy = math.log(n)
    return clamp(100.0 * entropy / max_entropy) or 0.0


class MultiHazardCompositeAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    HAZARD_FIELDS = "HAZARD_FIELDS"
    WEIGHTS = "WEIGHTS"
    OUTPUT = "OUTPUT"

    OUT_SCORE = "mh_score"
    OUT_CLASS = "mh_class"
    OUT_DOMINANT = "mh_dominant"
    OUT_DIVERSITY = "mh_diversity"
    OUT_DRIVERS = "mh_drivers"
    OUT_GAPS = "mh_data_gap"

    def tr(self, string):
        return string

    def createInstance(self):
        return MultiHazardCompositeAlgorithm()

    def name(self):
        return "multi_hazard_composite_index"

    def displayName(self):
        return self.tr("Multi-Hazard Composite Index")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Multi-Hazard Composite Index</h3>
            <p>Combines up to N hazard score fields (each on a 0-100 scale) per
            planning unit into a single composite score, plus diagnostic fields
            that reveal <b>which</b> hazard is driving the score.</p>
            <p><b>Outputs added to each feature:</b></p>
            <ul>
              <li><b>mh_score</b> - weighted mean of hazard scores (0-100).</li>
              <li><b>mh_class</b> - Very High / High / Moderate / Low.</li>
              <li><b>mh_dominant</b> - field name with the largest weighted contribution.</li>
              <li><b>mh_diversity</b> - 0 (single hazard dominant) to 100 (multi-stressed across all hazards).</li>
              <li><b>mh_drivers</b> - top 3 contributing field names (CSV).</li>
              <li><b>mh_data_gap</b> - number of hazard fields with null or non-numeric values.</li>
            </ul>
            <p><b>Weights:</b> optional CSV string matching the order of selected
            fields. Empty -> equal weights. Negative -> clamped to 0.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT,
            self.tr("Planning units"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.HAZARD_FIELDS,
            self.tr("Hazard score fields (numeric, 0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.WEIGHTS,
            self.tr("Weights (CSV, optional - empty = equal)"),
            defaultValue="",
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Multi-hazard composite")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Planning units layer is required.")

        hazard_fields = self.parameterAsFields(parameters, self.HAZARD_FIELDS, context) or []
        if len(hazard_fields) < 2:
            raise QgsProcessingException("Select at least two hazard score fields.")

        weight_text = self.parameterAsString(parameters, self.WEIGHTS, context)
        weights = parse_weights_csv(weight_text, len(hazard_fields))
        weight_sum = sum(weights) or 1.0

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_SCORE, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
            (self.OUT_DOMINANT, QVariant.String),
            (self.OUT_DIVERSITY, QVariant.Double),
            (self.OUT_DRIVERS, QVariant.String),
            (self.OUT_GAPS, QVariant.Int),
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
            scores: list[float | None] = []
            for fname in hazard_fields:
                scores.append(clamp(feature.attribute(fname)))
            gaps = sum(1 for s in scores if s is None)

            weighted = [
                (weights[i] * s if s is not None else 0.0) for i, s in enumerate(scores)
            ]
            present_weight = sum(weights[i] for i, s in enumerate(scores) if s is not None)
            composite = (sum(weighted) / present_weight) if present_weight > 0 else 0.0
            composite = clamp(composite) or 0.0

            # Dominant + drivers based on weighted contribution
            ranked = sorted(
                (
                    (weighted[i], hazard_fields[i])
                    for i, s in enumerate(scores) if s is not None
                ),
                reverse=True,
            )
            dominant = ranked[0][1] if ranked else ""
            drivers = ", ".join(name for _w, name in ranked[:3])

            diversity = _shannon_index([w for w in weighted if w > 0])

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feature.geometry())
            new_attrs = list(feature.attributes())
            # Pad to match field count if input layer has fewer attributes than out_fields
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([composite, composite_risk_class(composite), dominant, diversity, drivers, gaps])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: dest_id}
