# -*- coding: utf-8 -*-
"""Cost-Benefit Analyzer.

Given a scored layer (e.g., adaptation priority 0-100) and a cost model,
this algorithm ranks units by cost-effectiveness so planners can answer
"if I have a fixed budget, where do I spend it first?".

Cost model (per unit):
    cost = unit_cost (€/m² or €/feature) × area (or 1.0 for point/line layers)

Benefit model (per unit):
    benefit = score × reduction_factor × population_weight

The default reduction_factor is 0.7 (treatment removes ~70% of risk at the
unit), but a per-unit field can override it. Population weighting is
optional — if a population field is provided, benefit is scaled linearly.

Outputs per feature:
    cb_cost, cb_benefit, cb_ratio (benefit/cost), cb_priority_rank.

Logs the cumulative-budget curve so the user can pick a breakpoint:
"to capture 80 % of the total benefit you need to fund 25 % of the units".
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
    QgsWkbTypes,
)


def _safe_float(value, default=None):
    try:
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


class CostBenefitAnalyzerAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    UNIT_COST = "UNIT_COST"
    UNIT_COST_FIELD = "UNIT_COST_FIELD"
    DEFAULT_REDUCTION = "DEFAULT_REDUCTION"
    REDUCTION_FIELD = "REDUCTION_FIELD"
    POP_FIELD = "POP_FIELD"
    OUTPUT = "OUTPUT"

    OUT_COST = "cb_cost"
    OUT_BENEFIT = "cb_benefit"
    OUT_RATIO = "cb_ratio"
    OUT_RANK = "cb_priority_rank"

    def tr(self, string):
        return string

    def createInstance(self):
        return CostBenefitAnalyzerAlgorithm()

    def name(self):
        return "cost_benefit_analyzer"

    def displayName(self):
        return self.tr("Cost-Benefit Analyzer (planning prioritisation)")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Cost-Benefit Analyzer</h3>
            <p>Ranks planning units by cost-effectiveness using a transparent
            two-input model:</p>
            <pre>
cost    = unit_cost × area
benefit = score × reduction_factor × population_weight
ratio   = benefit / cost
            </pre>
            <p>Either a single default unit cost / reduction factor or
            per-feature fields can be supplied. Population weighting is
            optional. The output layer also includes a 1-N priority rank so
            you can drive a print layout straight from it.</p>
            <p>The processing log prints the cumulative-budget curve — useful
            for finding the "to capture 80 % of benefit you need to fund
            25 % of units" breakpoint.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored polygon/point layer"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SCORE_FIELD, self.tr("Score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.UNIT_COST, self.tr("Default unit cost (currency / m² for polygons; / feature for points)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=100.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.UNIT_COST_FIELD, self.tr("Per-feature unit-cost field (optional override)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DEFAULT_REDUCTION, self.tr("Default reduction factor (0..1)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.7, minValue=0.0, maxValue=1.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.REDUCTION_FIELD, self.tr("Per-feature reduction-factor field (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD, self.tr("Population weight field (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Cost-benefit ranked layer")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        unit_cost = self.parameterAsDouble(parameters, self.UNIT_COST, context)
        unit_cost_field = self.parameterAsString(parameters, self.UNIT_COST_FIELD, context)
        default_reduction = self.parameterAsDouble(parameters, self.DEFAULT_REDUCTION, context)
        reduction_field = self.parameterAsString(parameters, self.REDUCTION_FIELD, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)

        is_point = source.wkbType() in (
            QgsWkbTypes.Point, QgsWkbTypes.MultiPoint,
            QgsWkbTypes.PointZ, QgsWkbTypes.MultiPointZ,
        )

        records: list = []
        for feat in source.getFeatures():
            if feedback.isCanceled():
                break
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            score = _safe_float(feat.attribute(score_field), 0.0) or 0.0
            uc = _safe_float(feat.attribute(unit_cost_field), unit_cost) if unit_cost_field else unit_cost
            rf = _safe_float(feat.attribute(reduction_field), default_reduction) if reduction_field else default_reduction
            pop = _safe_float(feat.attribute(pop_field), 1.0) if pop_field else 1.0
            rf = max(0.0, min(1.0, rf))

            area = 1.0 if is_point else max(geom.area(), 0.0)
            cost = max(0.0, uc) * area
            benefit = score * rf * pop
            ratio = (benefit / cost) if cost > 0 else None
            records.append((feat, cost, benefit, ratio))

        # Rank descending by B/C ratio; features with cost == 0 (and finite benefit)
        # go first because they are "free wins". Features with both 0 go last.
        def _rank_key(rec):
            _f, cost, benefit, ratio = rec
            if cost == 0 and benefit > 0:
                return (-float("inf"),)  # free wins first
            if ratio is None:
                return (float("inf"),)
            return (-ratio,)

        records.sort(key=_rank_key)

        # Build output fields.
        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_COST, QVariant.Double),
            (self.OUT_BENEFIT, QVariant.Double),
            (self.OUT_RATIO, QVariant.Double),
            (self.OUT_RANK, QVariant.Int),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        # Write features in priority order so QGIS attribute table is already sorted.
        total_benefit = sum(r[2] for r in records) or 1.0
        total_cost = sum(r[1] for r in records)
        cum_benefit = 0.0
        cum_cost = 0.0
        log_breaks = [10, 25, 50, 75, 90]
        next_break = 0
        n = len(records) or 1

        for rank, (feat, cost, benefit, ratio) in enumerate(records, start=1):
            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 4:
                new_attrs.append(None)
            new_attrs.extend([cost, benefit, ratio if ratio is not None else None, rank])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            cum_benefit += benefit
            cum_cost += cost
            pct_units = 100.0 * rank / n
            pct_benefit = 100.0 * cum_benefit / total_benefit
            if next_break < len(log_breaks) and pct_benefit >= log_breaks[next_break]:
                feedback.pushInfo(
                    f"  {log_breaks[next_break]:>3}% of benefit reached after "
                    f"{pct_units:.1f}% of units (cumulative cost = {cum_cost:,.0f})"
                )
                next_break += 1

        feedback.pushInfo("")
        feedback.pushInfo("─── Cost-Benefit summary ───")
        feedback.pushInfo(f"Units evaluated   : {len(records)}")
        feedback.pushInfo(f"Total benefit     : {total_benefit:,.2f}")
        feedback.pushInfo(f"Total cost        : {total_cost:,.2f}")
        if total_cost > 0:
            feedback.pushInfo(f"Aggregate B/C     : {total_benefit / total_cost:.4f}")
        return {self.OUTPUT: dest_id}
