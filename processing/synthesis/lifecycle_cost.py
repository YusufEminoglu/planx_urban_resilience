# -*- coding: utf-8 -*-
"""Lifecycle Cost Calculator.

Per planning unit, computes a 25-year (configurable) Net Present Value
of an intervention package: upfront capex + annual opex + maintenance
events + replacement at end-of-life. Useful for moving the suite from
"where is the risk" to "what does the response cost over time".

Inputs (all numeric fields on the input layer or scalar defaults):
  - capex_field        : upfront cost (currency / m² when area scaling
                          is enabled, otherwise currency / feature)
  - opex_per_year      : annual O&M cost (same scaling rule)
  - maintenance_every  : years between major maintenance events
  - maintenance_cost   : maintenance cost per event
  - replacement_years  : full replacement cycle (years; 0 = no replacement)
  - replacement_cost   : full replacement cost
  - horizon_years      : analysis horizon (default 25)
  - discount_rate_pct  : discount rate (% per year, default 4)
  - area_scale         : if on, multiply per-m² values by geometry area
                         (polygons only); if off, take each value
                         literally per feature.

Outputs per feature:
  - lc_capex_npv          (= upfront capex, already present-value)
  - lc_opex_npv           (sum of discounted annual opex)
  - lc_maintenance_npv    (sum of discounted maintenance events)
  - lc_replacement_npv    (sum of discounted replacements within horizon)
  - lc_total_npv          (sum of the above)
  - lc_annualised         (equivalent flat annual cost over the horizon)
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
    QgsProcessingParameterBoolean,
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


from .._mixins import HelpUrlMixin

class LifecycleCostAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    CAPEX_FIELD = "CAPEX_FIELD"
    OPEX_FIELD = "OPEX_FIELD"
    MAINT_INTERVAL = "MAINT_INTERVAL"
    MAINT_COST = "MAINT_COST"
    MAINT_COST_FIELD = "MAINT_COST_FIELD"
    REPL_YEARS = "REPL_YEARS"
    REPL_COST = "REPL_COST"
    REPL_COST_FIELD = "REPL_COST_FIELD"
    HORIZON = "HORIZON"
    DISCOUNT = "DISCOUNT"
    AREA_SCALE = "AREA_SCALE"
    OUTPUT = "OUTPUT"

    OUT_CAPEX = "lc_capex_npv"
    OUT_OPEX = "lc_opex_npv"
    OUT_MAINT = "lc_maintenance_npv"
    OUT_REPL = "lc_replacement_npv"
    OUT_TOTAL = "lc_total_npv"
    OUT_ANNUAL = "lc_annualised"

    def tr(self, string):
        return string

    def createInstance(self):
        return LifecycleCostAlgorithm()

    def name(self):
        return "lifecycle_cost_calculator"

    def displayName(self):
        return self.tr("Lifecycle Cost Calculator (25-year NPV)")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Lifecycle Cost Calculator</h3>
            <p>Per unit, computes the discounted Net Present Value of an
            intervention over a configurable horizon (default 25 years).
            Includes capex, annual opex, periodic maintenance and
            replacement events.</p>
            <p>Outputs <code>lc_capex_npv</code>, <code>lc_opex_npv</code>,
            <code>lc_maintenance_npv</code>, <code>lc_replacement_npv</code>,
            <code>lc_total_npv</code>, <code>lc_annualised</code>
            (equivalent flat annual cost over the horizon).</p>
            <p>If <i>Area scaling</i> is on and the input is polygon, all
            per-m² fields are multiplied by polygon area; otherwise they
            are used literally per feature.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Planning units / interventions"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CAPEX_FIELD, self.tr("Capex field (upfront)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.OPEX_FIELD, self.tr("Annual opex field"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAINT_INTERVAL, self.tr("Maintenance interval (years; 0 = no maintenance)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=5, minValue=0, maxValue=100,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAINT_COST, self.tr("Default maintenance event cost (used if no field)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MAINT_COST_FIELD, self.tr("Per-feature maintenance-cost field (optional override)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.REPL_YEARS, self.tr("Replacement cycle (years; 0 = no replacement)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=0, minValue=0, maxValue=200,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.REPL_COST, self.tr("Default replacement cost (used if no field)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.REPL_COST_FIELD, self.tr("Per-feature replacement-cost field (optional override)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.HORIZON, self.tr("Analysis horizon (years)"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=25, minValue=1, maxValue=200,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISCOUNT, self.tr("Discount rate (% per year)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=4.0, minValue=0.0, maxValue=50.0,
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.AREA_SCALE, self.tr("Scale per-unit-area values by polygon area"),
            defaultValue=False,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Lifecycle cost layer")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        capex_field = self.parameterAsString(parameters, self.CAPEX_FIELD, context)
        opex_field = self.parameterAsString(parameters, self.OPEX_FIELD, context)
        maint_interval = self.parameterAsInt(parameters, self.MAINT_INTERVAL, context)
        maint_default = self.parameterAsDouble(parameters, self.MAINT_COST, context)
        maint_field = self.parameterAsString(parameters, self.MAINT_COST_FIELD, context)
        repl_years = self.parameterAsInt(parameters, self.REPL_YEARS, context)
        repl_default = self.parameterAsDouble(parameters, self.REPL_COST, context)
        repl_field = self.parameterAsString(parameters, self.REPL_COST_FIELD, context)
        horizon = self.parameterAsInt(parameters, self.HORIZON, context)
        rate = self.parameterAsDouble(parameters, self.DISCOUNT, context) / 100.0
        area_scale = self.parameterAsBool(parameters, self.AREA_SCALE, context)

        # Annuity factor for "annualised" (a = NPV * r / (1 - (1+r)^-n)).
        if rate == 0:
            annuity_factor = 1.0 / horizon
        else:
            annuity_factor = rate / (1.0 - (1.0 + rate) ** (-horizon))

        # Output schema.
        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_CAPEX, QVariant.Double),
            (self.OUT_OPEX, QVariant.Double),
            (self.OUT_MAINT, QVariant.Double),
            (self.OUT_REPL, QVariant.Double),
            (self.OUT_TOTAL, QVariant.Double),
            (self.OUT_ANNUAL, QVariant.Double),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        is_polygon = source.wkbType() in (
            QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon,
            QgsWkbTypes.PolygonZ, QgsWkbTypes.MultiPolygonZ,
        )

        running_total = 0.0
        total_features = 0
        for feat in source.getFeatures():
            if feedback.isCanceled():
                break
            if not feat.hasGeometry():
                continue
            geom = feat.geometry()
            area = geom.area() if (is_polygon and area_scale) else 1.0

            capex = _safe_float(feat.attribute(capex_field)) * area
            opex = (_safe_float(feat.attribute(opex_field)) * area) if opex_field else 0.0
            maint_per_event = (_safe_float(feat.attribute(maint_field), maint_default) * area
                               if maint_field else maint_default * area)
            repl_per_event = (_safe_float(feat.attribute(repl_field), repl_default) * area
                              if repl_field else repl_default * area)

            # Opex NPV.
            opex_npv = 0.0
            if opex != 0:
                for t in range(1, horizon + 1):
                    opex_npv += opex / ((1.0 + rate) ** t)

            # Maintenance NPV.
            maint_npv = 0.0
            if maint_interval > 0 and maint_per_event != 0:
                t = maint_interval
                while t <= horizon:
                    maint_npv += maint_per_event / ((1.0 + rate) ** t)
                    t += maint_interval

            # Replacement NPV.
            repl_npv = 0.0
            if repl_years > 0 and repl_per_event != 0:
                t = repl_years
                while t <= horizon:
                    repl_npv += repl_per_event / ((1.0 + rate) ** t)
                    t += repl_years

            total_npv = capex + opex_npv + maint_npv + repl_npv
            annualised = total_npv * annuity_factor

            running_total += total_npv
            total_features += 1

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(geom)
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([capex, opex_npv, maint_npv, repl_npv, total_npv, annualised])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        feedback.pushInfo("")
        feedback.pushInfo("─── Lifecycle Cost summary ───")
        feedback.pushInfo(f"  Horizon       : {horizon} years")
        feedback.pushInfo(f"  Discount rate : {rate * 100:.2f}% per year")
        feedback.pushInfo(f"  Features      : {total_features}")
        feedback.pushInfo(f"  Sum of lc_total_npv across all features : {running_total:,.2f}")
        if total_features:
            feedback.pushInfo(
                f"  Equivalent flat annual cost (sum)        : {running_total * annuity_factor:,.2f}"
            )
        return {self.OUTPUT: dest_id}
