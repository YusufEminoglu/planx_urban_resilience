# -*- coding: utf-8 -*-
"""Recovery Capacity Index.

Resilience = absorb + recover. Most modules in this suite measure stress
(exposure, hazard, vulnerability). This algorithm scores the OPPOSITE side:
how well a planning unit can BOUNCE BACK once a shock hits.

Composite of four offline-derivable proxies (each 0-100, missing fields are
ignored from the weighting):

  - Diversity (Hirschman-Herfindahl)        : land-use mix as a CSV of share
                                              fields (e.g. residential, commerce,
                                              industry, green). Higher diversity
                                              = more recovery resources.
  - Redundancy (multiple road accesses)     : `road_accesses` numeric field;
                                              normalized via min(100, count * scale).
  - Green coverage                          : `green_share` field 0-1 or 0-100.
  - Social cohesion proxy                   : `cohesion` numeric field 0-100,
                                              e.g. ownership rate, stable
                                              population fraction.

Output fields:
  - rc_diversity, rc_redundancy, rc_green, rc_cohesion : the four 0-100 sub-scores
  - rc_score        : weighted mean (0-100)
  - rc_class        : Very Low / Low / Moderate / High / Very High
  - rc_data_gap     : number of sub-scores that were missing
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
    QgsProcessingParameterString,
)

from .._helpers import clamp, recovery_capacity_class


def _shares_to_diversity(shares: list[float]) -> float:
    """Hirschman-Herfindahl based diversity score 0-100.

    HHI = sum(s_i^2). HHI=1 -> monoculture; HHI=1/n -> perfect mix.
    Score = 100 * (1 - HHI) / (1 - 1/n) bounded.
    """
    positive = [s for s in shares if s is not None and s > 0]
    n = len(positive)
    if n < 2:
        return 0.0
    total = sum(positive)
    if total <= 0:
        return 0.0
    normalized = [s / total for s in positive]
    hhi = sum(p * p for p in normalized)
    ideal = 1.0 / n
    if 1.0 - ideal <= 0:
        return 0.0
    diversity = 100.0 * (1.0 - hhi) / (1.0 - ideal)
    return max(0.0, min(100.0, diversity))


from .._mixins import GROUP_SYNTHESIS, GroupMixin, HelpUrlMixin  # noqa: E402


class RecoveryCapacityIndexAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_SYNTHESIS
    ICON = "tool_recovery_capacity_index.png"
    INPUT = "INPUT"
    DIVERSITY_FIELDS = "DIVERSITY_FIELDS"
    REDUNDANCY_FIELD = "REDUNDANCY_FIELD"
    REDUNDANCY_SCALE = "REDUNDANCY_SCALE"
    GREEN_FIELD = "GREEN_FIELD"
    COHESION_FIELD = "COHESION_FIELD"
    WEIGHTS = "WEIGHTS"
    OUTPUT = "OUTPUT"

    OUT_DIVERSITY = "rc_diversity"
    OUT_REDUNDANCY = "rc_redundancy"
    OUT_GREEN = "rc_green"
    OUT_COHESION = "rc_cohesion"
    OUT_SCORE = "rc_score"
    OUT_CLASS = "rc_class"
    OUT_GAPS = "rc_data_gap"

    def tr(self, string):
        return string

    def createInstance(self):
        return RecoveryCapacityIndexAlgorithm()

    def name(self):
        return "recovery_capacity_index"

    def displayName(self):
        return self.tr("Recovery Capacity Index")

    def shortHelpString(self):
        return self.tr(
            "<h3>Recovery Capacity Index</h3> <p>Measures the OPPOSITE side of resilience: how well a "
            'unit can bounce back after a shock, operationalising the "adaptive capacity" dimension '
            "of the IPCC AR5 vulnerability framework. Composite of four offline-derivable "
            "proxies:</p> <ol> <li><b>Diversity</b> - Hirschman-Herfindahl Index (borrowed from "
            "industrial-organisation economics, where it measures market concentration) applied to "
            "land-use shares following Cervero &amp; Kockelman's (1997) \"3Ds\" framework: many small, "
            "evenly-sized land uses signal a healthier local mix than one dominant use.</li> "
            '<li><b>Redundancy</b> - road-access count, scaled, following the "multiple paths" '
            "principle from network resilience theory: a location reachable by several routes "
            "recovers service faster after any one route is disrupted.</li> <li><b>Green coverage</b> "
            "(0-1 or 0-100).</li> <li><b>Social cohesion proxy</b> (0-100, e.g. ownership rate or "
            "stable-population fraction) - both drawn from Cutter, Ash &amp; Emrich's (2014) "
            "validated recovery-capacity indicators.</li> </ol> <p>All four sub-scores are optional "
            "and independently excludable - check rc_data_gap before treating a partially-scored unit "
            "as comparable to a fully-scored one. REDUNDANCY_SCALE (default 25.0) is a saturation "
            "constant, not a fitted parameter: a location with 25+ road-access points scores the "
            "maximum 100 regardless of whether it has 25 or 250 - tune it to your study area's actual "
            "access-count range. The four sub-scores are treated as independently additive; the model "
            "represents no interaction between them (e.g. diverse land uses matter less if nobody can "
            "reach them).</p> <p>Using the results: pair with Adaptation Priority Synthesis or "
            "Multi-Hazard Composite to find units that are <b>high-risk AND low-recovery</b> via "
            "Risk-Recovery Priority Matrix - the sharpest intervention targets. This uses "
            "offline-derivable proxies specifically because they need no survey data; it is not a "
            "substitute for a full community-resilience assessment (economic/institutional/social "
            "capital surveys) where the stakes justify collecting primary data.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Planning units"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIVERSITY_FIELDS, self.tr("Land-use share fields (optional, multiple)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            allowMultiple=True, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.REDUNDANCY_FIELD, self.tr("Redundancy count field (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.REDUNDANCY_SCALE, self.tr("Redundancy scale (saturates at 100/scale items)"),
            type=QgsProcessingParameterNumber.Double, defaultValue=25.0, minValue=1.0, maxValue=100.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.GREEN_FIELD, self.tr("Green coverage field (0-1 or 0-100) (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.COHESION_FIELD, self.tr("Social cohesion proxy 0-100 (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.WEIGHTS, self.tr("Sub-score weights CSV (diversity,redundancy,green,cohesion)"),
            defaultValue="1,1,1,1", optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Recovery capacity")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Planning units layer is required.")

        diversity_fields = self.parameterAsFields(parameters, self.DIVERSITY_FIELDS, context) or []
        redundancy_field = self.parameterAsString(parameters, self.REDUNDANCY_FIELD, context)
        red_scale = self.parameterAsDouble(parameters, self.REDUNDANCY_SCALE, context)
        green_field = self.parameterAsString(parameters, self.GREEN_FIELD, context)
        cohesion_field = self.parameterAsString(parameters, self.COHESION_FIELD, context)
        weight_text = self.parameterAsString(parameters, self.WEIGHTS, context) or "1,1,1,1"

        # Parse 4 weights
        weights = []
        for token in weight_text.replace(";", ",").split(","):
            try:
                weights.append(max(0.0, float(token.strip())))
            except ValueError:
                weights.append(1.0)
        while len(weights) < 4:
            weights.append(1.0)
        weights = weights[:4]
        w_div, w_red, w_grn, w_coh = weights

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_DIVERSITY, QVariant.Double),
            (self.OUT_REDUNDANCY, QVariant.Double),
            (self.OUT_GREEN, QVariant.Double),
            (self.OUT_COHESION, QVariant.Double),
            (self.OUT_SCORE, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
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

            # 1) Diversity
            if diversity_fields:
                shares = []
                for fname in diversity_fields:
                    val = feature.attribute(fname)
                    if val is None:
                        continue
                    try:
                        shares.append(float(val))
                    except (TypeError, ValueError):
                        continue
                rc_div = _shares_to_diversity(shares) if shares else None
            else:
                rc_div = None

            # 2) Redundancy
            if redundancy_field:
                count = clamp(feature.attribute(redundancy_field), low=0, high=1e6)
                if count is None:
                    rc_red = None
                else:
                    rc_red = clamp(count * red_scale)
            else:
                rc_red = None

            # 3) Green coverage — accept 0-1 or 0-100
            if green_field:
                gv = feature.attribute(green_field)
                try:
                    gf = float(gv) if gv is not None else None
                except (TypeError, ValueError):
                    gf = None
                if gf is None:
                    rc_grn = None
                else:
                    if 0 <= gf <= 1:
                        rc_grn = clamp(gf * 100.0)
                    else:
                        rc_grn = clamp(gf)
            else:
                rc_grn = None

            # 4) Cohesion
            rc_coh = clamp(feature.attribute(cohesion_field)) if cohesion_field else None

            sub = [
                (rc_div, w_div),
                (rc_red, w_red),
                (rc_grn, w_grn),
                (rc_coh, w_coh),
            ]
            present = [(s, w) for s, w in sub if s is not None]
            gaps = len(sub) - len(present)
            if present:
                weight_sum = sum(w for _s, w in present) or 1.0
                score = sum(s * w for s, w in present) / weight_sum
                score = clamp(score) or 0.0
            else:
                score = 0.0

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feature.geometry())
            new_attrs = list(feature.attributes())
            while len(new_attrs) < out_fields.size() - 7:
                new_attrs.append(None)
            new_attrs.extend([rc_div, rc_red, rc_grn, rc_coh, score, recovery_capacity_class(score), gaps])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: dest_id}
