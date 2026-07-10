# -*- coding: utf-8 -*-
"""Optimal Shelter Siting (greedy maximal-coverage).

Classic facility-location problem: from a set of candidate shelter sites,
pick K so the population covered within a maximum walking distance is
maximised. Greedy MCLP (Maximal Covering Location Problem) — at each
step pick the candidate that adds the most uncovered demand. This is a
0.63-of-optimal approximation in the worst case (Cornuéjols et al. 1977)
but is the de-facto practical choice when budgets are tight.

Inputs:
  - candidate sites layer (points / polygon centroids)
  - demand units layer (points or polygons) + population field
  - max coverage distance (map units; Euclidean, fast — for network
    distance, pre-route the demand through Network Emergency
    Accessibility first)
  - K (number of sites to select)
  - optional: existing-shelter layer that pre-covers some demand

Outputs (candidate sites layer enriched):
  - oss_selected         — 1 if picked, else 0
  - oss_rank             — 1-K selection order (NULL if not picked)
  - oss_pop_added        — additional population covered at selection time
  - oss_pop_total_cum    — cumulative covered population after picking it

Log:
  - per-step coverage curve
  - final coverage % and uncovered demand units list (top 10)
"""
from __future__ import annotations

import math

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        if math.isnan(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _centroid_xy(geom: QgsGeometry):
    if geom is None or geom.isEmpty():
        return None
    if geom.type() == QgsWkbTypes.PointGeometry and not geom.isMultipart():
        p = geom.asPoint()
        return (p.x(), p.y())
    c = geom.centroid().asPoint()
    return (c.x(), c.y())


from .._mixins import HelpUrlMixin

class OptimalShelterSitingAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    CANDIDATES = "CANDIDATES"
    DEMAND = "DEMAND"
    POP_FIELD = "POP_FIELD"
    MAX_DISTANCE = "MAX_DISTANCE"
    NUM_SITES = "NUM_SITES"
    EXISTING = "EXISTING"
    OUTPUT = "OUTPUT"

    OUT_SELECTED = "oss_selected"
    OUT_RANK = "oss_rank"
    OUT_POP_ADDED = "oss_pop_added"
    OUT_POP_CUM = "oss_pop_total_cum"

    def tr(self, string):
        return string

    def createInstance(self):
        return OptimalShelterSitingAlgorithm()

    def name(self):
        return "optimal_shelter_siting"

    def displayName(self):
        return self.tr("Optimal Shelter Siting (greedy maximal coverage)")

    def group(self):
        return self.tr("5 - Emergency")

    def groupId(self):
        return "planx_urban_resilience_emergency"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Optimal Shelter Siting</h3>
            <p>Pick K shelter sites from a candidate set so the population
            covered within a maximum walking distance is maximised. Greedy
            MCLP — at each step pick the site that adds the most uncovered
            demand. 0.63-of-optimal worst case, but the de-facto choice
            when budgets are tight.</p>
            <p>An optional existing-shelter layer pre-covers some demand
            so the K new picks fill the gaps.</p>
            <p>Per-candidate outputs:</p>
            <ul>
              <li><code>oss_selected</code> — 1 if picked, else 0.</li>
              <li><code>oss_rank</code> — 1..K selection order.</li>
              <li><code>oss_pop_added</code> — additional population covered at selection.</li>
              <li><code>oss_pop_total_cum</code> — cumulative covered population after this pick.</li>
            </ul>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CANDIDATES, self.tr("Candidate shelter sites (points or polygons)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.DEMAND, self.tr("Demand units (points or polygons) with population field"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD, self.tr("Population field on demand units"),
            parentLayerParameterName=self.DEMAND,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_DISTANCE, self.tr("Maximum coverage distance (map units)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=500.0, minValue=0.001, maxValue=1e9,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.NUM_SITES, self.tr("Number of sites to select (K)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=5, minValue=1, maxValue=10000,
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.EXISTING, self.tr("Existing shelters (optional — their coverage is subtracted before greedy)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Candidate sites with selection results")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        candidates_src = self.parameterAsSource(parameters, self.CANDIDATES, context)
        demand_src = self.parameterAsSource(parameters, self.DEMAND, context)
        if candidates_src is None or demand_src is None:
            raise QgsProcessingException("Candidates and demand layers are required.")
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        max_dist = self.parameterAsDouble(parameters, self.MAX_DISTANCE, context)
        k = self.parameterAsInt(parameters, self.NUM_SITES, context)
        existing_src = self.parameterAsSource(parameters, self.EXISTING, context)

        # Demand setup.
        feedback.pushInfo("Loading demand units…")
        demand_xy: list[tuple[float, float]] = []
        demand_pop: list[float] = []
        demand_feats: list[QgsFeature] = []
        for feat in demand_src.getFeatures():
            xy = _centroid_xy(feat.geometry())
            if xy is None:
                continue
            demand_xy.append(xy)
            demand_pop.append(_safe_float(feat.attribute(pop_field), 0.0))
            demand_feats.append(feat)
        m = len(demand_xy)
        if m == 0:
            raise QgsProcessingException("No demand features with geometry.")
        total_pop = sum(demand_pop)
        feedback.pushInfo(f"  {m} demand units, total population {total_pop:,.0f}.")

        # Coverage status: True if demand i is already covered.
        covered = [False] * m

        # Apply existing-shelter pre-coverage.
        if existing_src is not None:
            feedback.pushInfo("Pre-covering with existing shelters…")
            for feat in existing_src.getFeatures():
                xy = _centroid_xy(feat.geometry())
                if xy is None:
                    continue
                for i in range(m):
                    if covered[i]:
                        continue
                    if math.hypot(demand_xy[i][0] - xy[0], demand_xy[i][1] - xy[1]) <= max_dist:
                        covered[i] = True
            pre = sum(demand_pop[i] for i in range(m) if covered[i])
            pct = 100.0 * pre / total_pop if total_pop > 0 else 0.0
            feedback.pushInfo(f"  Existing shelters cover {pre:,.0f} ({pct:.1f}%) of demand.")

        # Load candidates.
        feedback.pushInfo("Loading candidate sites…")
        cand_feats: list[QgsFeature] = []
        cand_xy: list[tuple[float, float]] = []
        for feat in candidates_src.getFeatures():
            xy = _centroid_xy(feat.geometry())
            if xy is None:
                continue
            cand_feats.append(feat)
            cand_xy.append(xy)
        if not cand_feats:
            raise QgsProcessingException("No candidate features with geometry.")
        feedback.pushInfo(f"  {len(cand_feats)} candidate sites.")

        # Greedy MCLP loop.
        selected_idx: list[int] = []
        per_step_added: dict[int, float] = {}
        for step in range(1, k + 1):
            if feedback.isCanceled():
                break
            best_gain = -1.0
            best_idx = -1
            best_covered_set: list[int] = []
            for cidx, (cx, cy) in enumerate(cand_xy):
                if cidx in selected_idx:
                    continue
                gain = 0.0
                hits: list[int] = []
                for i in range(m):
                    if covered[i]:
                        continue
                    if math.hypot(demand_xy[i][0] - cx, demand_xy[i][1] - cy) <= max_dist:
                        hits.append(i)
                        gain += demand_pop[i]
                if gain > best_gain:
                    best_gain = gain
                    best_idx = cidx
                    best_covered_set = hits
            if best_idx < 0 or best_gain <= 0:
                feedback.pushInfo(f"  Step {step}: no candidate adds new coverage. Stopping.")
                break
            selected_idx.append(best_idx)
            per_step_added[best_idx] = best_gain
            for i in best_covered_set:
                covered[i] = True
            total_cov = sum(demand_pop[i] for i in range(m) if covered[i])
            pct = 100.0 * total_cov / total_pop if total_pop > 0 else 0.0
            feedback.pushInfo(
                f"  Step {step}: candidate idx={best_idx} adds {best_gain:,.0f} "
                f"(cumulative coverage {total_cov:,.0f} / {pct:.1f}%)."
            )
            feedback.setProgress(int(100 * step / k))

        # Build output (all candidates, annotated).
        out_fields = candidates_src.fields()
        for fname, ftype in (
            (self.OUT_SELECTED, QVariant.Int),
            (self.OUT_RANK, QVariant.Int),
            (self.OUT_POP_ADDED, QVariant.Double),
            (self.OUT_POP_CUM, QVariant.Double),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            candidates_src.wkbType(), candidates_src.sourceCrs(),
        )

        # Recompute cumulative for the chosen subset in order.
        cum = 0.0
        cum_map: dict[int, float] = {}
        for cidx in selected_idx:
            cum += per_step_added.get(cidx, 0.0)
            cum_map[cidx] = cum

        for idx, feat in enumerate(cand_feats):
            selected = 1 if idx in selected_idx else 0
            rank = (selected_idx.index(idx) + 1) if selected else None
            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 4:
                new_attrs.append(None)
            new_attrs.extend([
                selected,
                rank,
                per_step_added.get(idx, 0.0) if selected else None,
                cum_map.get(idx) if selected else None,
            ])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        # Final summary.
        final_cov = sum(demand_pop[i] for i in range(m) if covered[i])
        pct = 100.0 * final_cov / total_pop if total_pop > 0 else 0.0
        feedback.pushInfo("")
        feedback.pushInfo("─── Optimal Shelter Siting summary ───")
        feedback.pushInfo(f"  Selected {len(selected_idx)} of K={k} candidate sites.")
        feedback.pushInfo(f"  Total covered population: {final_cov:,.0f} ({pct:.1f}%).")
        uncovered = sorted(
            ((demand_pop[i], i) for i in range(m) if not covered[i]),
            reverse=True,
        )[:10]
        if uncovered:
            feedback.pushInfo("  Top 10 uncovered demand units (by population):")
            for pop_value, i in uncovered:
                feedback.pushInfo(f"    demand idx={i:<6}  population={pop_value:,.0f}")
        return {self.OUTPUT: dest_id}
