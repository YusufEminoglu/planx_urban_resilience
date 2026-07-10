# -*- coding: utf-8 -*-
"""Pareto-Optimal Intervention Selector.

Given a scored layer with cost and benefit fields (typically the output
of the Cost-Benefit Analyzer), this algorithm identifies the Pareto
frontier: the set of interventions where no other intervention is BOTH
cheaper AND more beneficial. Everything off the frontier is dominated by
something on it.

For each feature:
    pareto_rank       — 1 for points on the (cheapest, highest-benefit)
                        frontier, 2 for the next "skin" of points after the
                        first frontier is removed, and so on.
    pareto_dominated  — count of other features that strictly dominate it.
    pareto_dominates  — count of other features it strictly dominates.

Use case: when budget can fund only N interventions, picking everything
with `pareto_rank == 1` guarantees no objectively better alternative
exists. Successive ranks give a sensible fallback ordering.

Algorithm: non-dominated sorting (NSGA-II style), O(N²) in features. For
typical 100-2 000 planning unit layers this finishes in a second.
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
)


def _safe_float(value, default=None):
    try:
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _dominates(a, b) -> bool:
    """Returns True iff `a` Pareto-dominates `b`.

    a = (cost, benefit) where lower cost is better, higher benefit is better.
    a dominates b if a is no worse on both AND strictly better on at least one.
    """
    ac, ab = a
    bc, bb = b
    return (ac <= bc and ab >= bb) and (ac < bc or ab > bb)


from .._mixins import HelpUrlMixin  # noqa: E402


class ParetoSelectorAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    COST_FIELD = "COST_FIELD"
    BENEFIT_FIELD = "BENEFIT_FIELD"
    OUTPUT = "OUTPUT"

    OUT_RANK = "pareto_rank"
    OUT_DOMINATED = "pareto_dominated"
    OUT_DOMINATES = "pareto_dominates"

    def tr(self, string):
        return string

    def createInstance(self):
        return ParetoSelectorAlgorithm()

    def name(self):
        return "pareto_optimal_selector"

    def displayName(self):
        return self.tr("Pareto-Optimal Intervention Selector")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Pareto-Optimal Intervention Selector</h3>
            <p>Identifies the Pareto frontier of a (cost, benefit) trade-off:
            the set of interventions where no other is BOTH cheaper AND more
            beneficial. Pair with the Cost-Benefit Analyzer (uses its
            <code>cb_cost</code> / <code>cb_benefit</code> outputs) or feed
            any two numeric trade-off fields.</p>
            <p>Per-feature outputs:</p>
            <ul>
              <li><code>pareto_rank</code> — 1 = first frontier (best), 2 = second skin after removing the first, etc.</li>
              <li><code>pareto_dominated</code> — count of other features that strictly dominate this one.</li>
              <li><code>pareto_dominates</code> — count of other features this one strictly dominates.</li>
            </ul>
            <p>Budget-bounded use: when funds cover only N interventions,
            picking everything with <code>pareto_rank == 1</code> guarantees
            no objectively better alternative exists.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Layer with cost and benefit fields"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.COST_FIELD, self.tr("Cost field (lower = better)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.BENEFIT_FIELD, self.tr("Benefit field (higher = better)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Pareto-ranked layer")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        cost_field = self.parameterAsString(parameters, self.COST_FIELD, context)
        benefit_field = self.parameterAsString(parameters, self.BENEFIT_FIELD, context)

        feats: list = []
        costs: list = []
        benefits: list = []
        for feat in source.getFeatures():
            if not feat.hasGeometry():
                continue
            c = _safe_float(feat.attribute(cost_field))
            b = _safe_float(feat.attribute(benefit_field))
            if c is None or b is None:
                continue
            feats.append(feat)
            costs.append(c)
            benefits.append(b)

        n = len(feats)
        if n == 0:
            raise QgsProcessingException("No features with valid cost/benefit values.")
        feedback.pushInfo(f"Computing dominance over {n} features…")

        # O(N²) dominance counting.
        dominated_count = [0] * n
        dominates_count = [0] * n
        for i in range(n):
            if feedback.isCanceled():
                break
            ai = (costs[i], benefits[i])
            for j in range(n):
                if i == j:
                    continue
                aj = (costs[j], benefits[j])
                if _dominates(aj, ai):
                    dominated_count[i] += 1
                if _dominates(ai, aj):
                    dominates_count[i] += 1
            if i % 50 == 0:
                feedback.setProgress(int(60 * (i + 1) / n))

        # Non-dominated sorting: peel frontiers one at a time.
        rank = [0] * n
        remaining = set(range(n))
        cur_rank = 1
        while remaining:
            # Identify all indices in `remaining` with no dominators inside `remaining`.
            front: list = []
            for i in remaining:
                if all(not _dominates((costs[j], benefits[j]), (costs[i], benefits[i]))
                       for j in remaining if j != i):
                    front.append(i)
            if not front:
                # Shouldn't happen, but be safe — assign the same rank and exit.
                for i in remaining:
                    rank[i] = cur_rank
                break
            for i in front:
                rank[i] = cur_rank
            remaining.difference_update(front)
            cur_rank += 1
            feedback.setProgress(60 + int(40 * (n - len(remaining)) / n))

        # Build output.
        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_RANK, QVariant.Int),
            (self.OUT_DOMINATED, QVariant.Int),
            (self.OUT_DOMINATES, QVariant.Int),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        rank_counts: dict = {}
        for i, feat in enumerate(feats):
            r = rank[i]
            rank_counts[r] = rank_counts.get(r, 0) + 1
            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 3:
                new_attrs.append(None)
            new_attrs.extend([r, dominated_count[i], dominates_count[i]])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        feedback.pushInfo("")
        feedback.pushInfo("─── Pareto rank distribution ───")
        for r in sorted(rank_counts.keys()):
            feedback.pushInfo(f"  rank {r:>3} : {rank_counts[r]} features")
        feedback.pushInfo(
            f"Top frontier (rank 1) has {rank_counts.get(1, 0)} features — "
            f"these are not Pareto-dominated by anything else in the layer."
        )
        return {self.OUTPUT: dest_id}
