# -*- coding: utf-8 -*-
"""Bivariate Choropleth Symbology.

Applies a 3×3 bivariate colour matrix to a polygon layer based on two
score fields (e.g., risk × vulnerability). Each feature is classified into
Low / Mid / High on each axis (quantile bins), producing 9 categories with
the standard Stevens-style bivariate palette:

  vulnerability →
  Low      Mid      High
  #e8e8e8  #b5c0da  #6c83b5   ← risk: High
  #b8d6be  #90b2b3  #567994   ← risk: Mid
  #d3f2a3  #97c890  #5a9178   ← risk: Low

Also adds a `bv_class` field with the 9 labels (R-L_V-L, R-L_V-M, …) so the
symbology survives layer-style export.
"""
from __future__ import annotations

import contextlib
import math

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFillSymbol,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsRendererCategory,
)


# Risk (rows, low→high) × Vulnerability (cols, low→high).
BIVARIATE_PALETTE = [
    # vL,        vM,        vH
    ["#d3f2a3", "#97c890", "#5a9178"],  # rL
    ["#b8d6be", "#90b2b3", "#567994"],  # rM
    ["#e8e8e8", "#b5c0da", "#6c83b5"],  # rH
]
AXIS_LABELS = ("L", "M", "H")


def _bin(value: float, breaks: list[float]) -> int:
    """Return 0 / 1 / 2 based on tertile breakpoints [b1, b2]."""
    if math.isnan(value):
        return 0
    if value <= breaks[0]:
        return 0
    if value <= breaks[1]:
        return 1
    return 2


def _percentiles(values: list[float], pct: list[int]) -> list[float]:
    if not values:
        return [0.0] * len(pct)
    sv = sorted(values)
    out = []
    n = len(sv)
    for p in pct:
        if n == 1:
            out.append(sv[0])
            continue
        idx = (p / 100.0) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        out.append(sv[lo] + (sv[hi] - sv[lo]) * frac)
    return out


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class BivariateSymbologyAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_bivariate_choropleth_symbology.png"
    INPUT = "INPUT"
    RISK_FIELD = "RISK_FIELD"
    VULN_FIELD = "VULN_FIELD"
    OUTPUT = "OUTPUT"

    OUT_BV_CLASS = "bv_class"
    OUT_R_BIN = "bv_risk_bin"
    OUT_V_BIN = "bv_vuln_bin"

    def tr(self, string):
        return string

    def createInstance(self):
        return BivariateSymbologyAlgorithm()

    def name(self):
        return "bivariate_choropleth_symbology"

    def displayName(self):
        return self.tr("Bivariate Choropleth Symbology (risk × vulnerability)")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Bivariate Choropleth Symbology</h3>
            <p>Classifies every feature into Low / Mid / High on two scored
            axes (e.g., <b>risk</b> and <b>vulnerability</b>) using quantile
            breaks, then assigns the 9-category Stevens-style bivariate
            palette so the map shows BOTH variables at once.</p>
            <p>Output layer adds <code>bv_class</code> (e.g. <code>R-H_V-M</code>),
            <code>bv_risk_bin</code> and <code>bv_vuln_bin</code> fields and
            comes with a categorised renderer already applied.</p>
            <p>Reads beautifully alongside a 3×3 legend grid placed in the
            print layout (no built-in legend item is generated — place it
            manually as a cartographic element).</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Polygon layer with two score fields"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.RISK_FIELD, self.tr("Risk axis field (numeric)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.VULN_FIELD, self.tr("Vulnerability axis field (numeric)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Bivariate-classified layer")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        risk_field = self.parameterAsString(parameters, self.RISK_FIELD, context)
        vuln_field = self.parameterAsString(parameters, self.VULN_FIELD, context)

        # Collect values for tertile breaks.
        risk_vals: list[float] = []
        vuln_vals: list[float] = []
        for feat in source.getFeatures():
            try:
                r = float(feat.attribute(risk_field))
                v = float(feat.attribute(vuln_field))
                if not (math.isnan(r) or math.isnan(v)):
                    risk_vals.append(r)
                    vuln_vals.append(v)
            except (TypeError, ValueError):
                pass

        if not risk_vals or not vuln_vals:
            raise QgsProcessingException(
                "No numeric values found in the chosen fields."
            )

        risk_breaks = _percentiles(risk_vals, [33, 67])
        vuln_breaks = _percentiles(vuln_vals, [33, 67])
        feedback.pushInfo(f"Risk tertile breaks: {risk_breaks[0]:.2f} / {risk_breaks[1]:.2f}")
        feedback.pushInfo(f"Vuln tertile breaks: {vuln_breaks[0]:.2f} / {vuln_breaks[1]:.2f}")

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_BV_CLASS, QVariant.String),
            (self.OUT_R_BIN, QVariant.Int),
            (self.OUT_V_BIN, QVariant.Int),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        total = max(source.featureCount(), 1)
        for idx, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            try:
                r = float(feat.attribute(risk_field))
                v = float(feat.attribute(vuln_field))
            except (TypeError, ValueError):
                r, v = float("nan"), float("nan")
            r_bin = _bin(r, risk_breaks)
            v_bin = _bin(v, vuln_breaks)
            cls = f"R-{AXIS_LABELS[r_bin]}_V-{AXIS_LABELS[v_bin]}"

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 3:
                new_attrs.append(None)
            new_attrs.extend([cls, r_bin, v_bin])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            if idx % 25 == 0:
                feedback.setProgress(int(100 * (idx + 1) / total))

        # Apply renderer to the destination layer (when launched
        # interactively, layerToLoadOnCompletionDetails picks this up).
        self._apply_renderer(context, dest_id)
        feedback.pushInfo("Bivariate renderer applied. Place a 3×3 legend grid in your print layout.")
        return {self.OUTPUT: dest_id}

    @staticmethod
    def _apply_renderer(context: QgsProcessingContext, dest_id: str) -> None:
        # Symbology is a nice-to-have; never let it block output writing.
        with contextlib.suppress(Exception):
            layer = context.getMapLayer(dest_id)
            if layer is None or not hasattr(layer, "setRenderer"):
                return
            categories: list = []
            for r_bin in range(3):
                for v_bin in range(3):
                    label = f"R-{AXIS_LABELS[r_bin]}_V-{AXIS_LABELS[v_bin]}"
                    color = QColor(BIVARIATE_PALETTE[r_bin][v_bin])
                    symbol = QgsFillSymbol.createSimple({
                        "color": f"{color.red()},{color.green()},{color.blue()},230",
                        "outline_color": "60,60,60,200",
                        "outline_width": "0.2",
                    })
                    categories.append(QgsRendererCategory(label, symbol, label))
            renderer = QgsCategorizedSymbolRenderer("bv_class", categories)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
