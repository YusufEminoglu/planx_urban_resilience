# -*- coding: utf-8 -*-
"""Scenario Sensitivity Analysis.

Composite resilience scores depend on how component hazards are weighted.
This algorithm stress-tests those weights with Latin Hypercube Sampling:
for each planning unit it draws many weight vectors within a band around
nominal weights, recomputes the weighted composite, and reports how stable
the score is under that uncertainty.

Inputs:
  - planning units with two or more component score fields (0-100)
  - nominal weights (CSV, optional)
  - perturbation fraction (0..1): each weight may vary by ± this fraction
  - sample count (10..500)

Outputs per feature:
  - ss_baseline     : composite with nominal weights
  - ss_mean         : mean composite across samples
  - ss_std          : standard deviation
  - ss_p05, ss_p95  : 5th / 95th percentile across samples
  - ss_range        : p95 - p05
  - ss_stability    : 0-100 (high = low variance under weight uncertainty)
  - ss_samples      : number of LHS draws used
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
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)

from .._helpers import SeededRng, clamp, parse_weights_csv


def _latin_hypercube(n_samples: int, n_dims: int, rng: SeededRng) -> list[list[float]]:
    """Vectors in [0, 1]^n_dims via Latin Hypercube."""
    grid = [[0.0] * n_dims for _ in range(n_samples)]
    for dim in range(n_dims):
        cuts = [(i + rng.random()) / n_samples for i in range(n_samples)]
        rng.shuffle(cuts)
        for row in range(n_samples):
            grid[row][dim] = cuts[row]
    return grid


def _weighted_composite(scores: list[float | None], weights: list[float]) -> float:
    weighted = 0.0
    present = 0.0
    for value, weight in zip(scores, weights):
        if value is None:
            continue
        weighted += weight * value
        present += weight
    if present <= 0:
        return 0.0
    return clamp(weighted / present) or 0.0


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = (p / 100.0) * (len(sorted_values) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _stability(std: float) -> float:
    """Map std dev to 0-100 stability (std=0 -> 100, std>=25 -> 0)."""
    if std <= 0:
        return 100.0
    return clamp(100.0 * (1.0 - std / 25.0)) or 0.0


from .._mixins import HelpUrlMixin  # noqa: E402


class ScenarioSensitivityAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    COMPONENT_FIELDS = "COMPONENT_FIELDS"
    WEIGHTS = "WEIGHTS"
    PERTURB = "PERTURB"
    SAMPLES = "SAMPLES"
    SEED = "SEED"
    OUTPUT = "OUTPUT"

    OUT_BASELINE = "ss_baseline"
    OUT_MEAN = "ss_mean"
    OUT_STD = "ss_std"
    OUT_P05 = "ss_p05"
    OUT_P95 = "ss_p95"
    OUT_RANGE = "ss_range"
    OUT_STABILITY = "ss_stability"
    OUT_N = "ss_samples"

    def tr(self, string):
        return string

    def createInstance(self):
        return ScenarioSensitivityAlgorithm()

    def name(self):
        return "scenario_sensitivity"

    def displayName(self):
        return self.tr("Scenario Sensitivity Analysis")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Scenario Sensitivity Analysis</h3>
            <p>Stress-tests composite scores by varying component weights with
            Latin Hypercube Sampling. Units with <b>high stability</b> keep a
            similar rank regardless of reasonable weight choices; <b>low
            stability</b> units are sensitive to how hazards are prioritised.</p>
            <p><b>Outputs:</b> baseline composite (nominal weights), mean, std,
            p05/p95, range, and a 0-100 stability score.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT,
            self.tr("Planning units"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.COMPONENT_FIELDS,
            self.tr("Component score fields (numeric, 0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.WEIGHTS,
            self.tr("Nominal weights (CSV, optional — empty = equal)"),
            defaultValue="",
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.PERTURB,
            self.tr("Weight perturbation (0 = fixed, 1 = ±100% band)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.5,
            minValue=0.0,
            maxValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SAMPLES,
            self.tr("LHS sample count"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=100,
            minValue=10,
            maxValue=500,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.SEED,
            self.tr("Random seed (reproducible runs)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=42,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Sensitivity analysis")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Planning units layer is required.")

        component_fields = self.parameterAsFields(parameters, self.COMPONENT_FIELDS, context) or []
        if len(component_fields) < 2:
            raise QgsProcessingException("Select at least two component score fields.")

        weight_text = self.parameterAsString(parameters, self.WEIGHTS, context)
        base_weights = parse_weights_csv(weight_text, len(component_fields))
        perturb = self.parameterAsDouble(parameters, self.PERTURB, context)
        n_samples = int(self.parameterAsInt(parameters, self.SAMPLES, context))
        seed = self.parameterAsInt(parameters, self.SEED, context)
        rng = SeededRng(seed if seed is not None else 42)

        lhs = _latin_hypercube(n_samples, len(component_fields), rng)
        weight_vectors: list[list[float]] = []
        for sample in lhs:
            raw = []
            for dim, base in enumerate(base_weights):
                lo = base * (1.0 - perturb)
                hi = base * (1.0 + perturb)
                raw.append(lo + sample[dim] * (hi - lo))
            total = sum(raw) or 1.0
            weight_vectors.append([w / total for w in raw])

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_BASELINE, QVariant.Double),
            (self.OUT_MEAN, QVariant.Double),
            (self.OUT_STD, QVariant.Double),
            (self.OUT_P05, QVariant.Double),
            (self.OUT_P95, QVariant.Double),
            (self.OUT_RANGE, QVariant.Double),
            (self.OUT_STABILITY, QVariant.Double),
            (self.OUT_N, QVariant.Int),
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
            scores = [clamp(feature.attribute(fname)) for fname in component_fields]
            baseline = _weighted_composite(scores, base_weights)
            composites = [_weighted_composite(scores, wvec) for wvec in weight_vectors]
            composites.sort()
            mean = sum(composites) / len(composites) if composites else baseline
            variance = sum((c - mean) ** 2 for c in composites) / len(composites) if composites else 0.0
            std = math.sqrt(variance)
            p05 = _percentile(composites, 5)
            p95 = _percentile(composites, 95)
            score_range = p95 - p05
            stability = _stability(std)

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feature.geometry())
            new_attrs = list(feature.attributes())
            while len(new_attrs) < out_fields.size() - 8:
                new_attrs.append(None)
            new_attrs.extend([
                baseline, mean, std, p05, p95, score_range, stability, n_samples,
            ])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((idx + 1) / total * 100))

        return {self.OUTPUT: dest_id}
