# -*- coding: utf-8 -*-
"""Risk Trend Hot-Spot.

Fuses two perspectives the suite already covers separately:
  - TEMPORAL: the time-series tracker tells you each unit's score has
    gone up, stayed flat, or gone down between two snapshots.
  - SPATIAL: Hot-Spot Gi* / LISA tells you which units are cluster
    members of high-value neighbourhoods.

This algorithm runs Gi* on the LATER snapshot's score, then combines the
cluster significance with the per-unit DELTA from the earlier snapshot
to produce a single fused "trending hot spot" label. The classic planner
question — "which neighbourhoods are both rising AND clustered with high
risk?" — drops out of one column.

Inputs:
  - layer with `later_score` (current value) and `delta` (later − earlier)
    fields (typically the output of `resilience_time_series`).
  - distance band for the local-Gi* neighbourhood.
  - significance level (default 0.05).

Outputs added per feature:
  - trh_gi_z           — z-score from Getis-Ord Gi*.
  - trh_gi_significant — 1 if |gi_z| ≥ 1.96 (i.e. p < 0.05), else 0.
  - trh_delta          — the input delta (copied for convenience).
  - trh_label          — one of:
        "Rising hot spot"   — clustered high values, score rising
        "Stable hot spot"   — clustered high values, score steady
        "Cooling hot spot"  — clustered high values, score falling
        "Rising cold spot"  — clustered low values, score rising
        "Stable cold spot"  — clustered low values, score steady
        "Cooling cold spot" — clustered low values, score falling
        "Hot, no cluster"   — high value but not significantly clustered
        "Cold, no cluster"  — low value but not significantly clustered
        "Not significant"   — neither cluster nor strong trend.
"""
from __future__ import annotations

import math

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsRectangle,
    QgsSpatialIndex,
)


def _safe_float(v, default=None):
    try:
        f = float(v)
        if math.isnan(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _label(gi_z: float, sig: int, delta: float | None, delta_tol: float) -> str:
    if delta is None:
        rising = False
        falling = False
    else:
        rising = delta > delta_tol
        falling = delta < -delta_tol
    is_hot = gi_z > 0 and sig
    is_cold = gi_z < 0 and sig
    if is_hot:
        if rising:
            return "Rising hot spot"
        if falling:
            return "Cooling hot spot"
        return "Stable hot spot"
    if is_cold:
        if rising:
            return "Rising cold spot"
        if falling:
            return "Cooling cold spot"
        return "Stable cold spot"
    if gi_z > 0:
        return "Hot, no cluster"
    if gi_z < 0:
        return "Cold, no cluster"
    return "Not significant"


from .._mixins import GROUP_SYNTHESIS, GroupMixin, HelpUrlMixin  # noqa: E402


class RiskTrendHotspotAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_SYNTHESIS
    ICON = "tool_risk_trend_hotspot.png"
    INPUT = "INPUT"
    LATER_SCORE = "LATER_SCORE"
    DELTA_FIELD = "DELTA_FIELD"
    DISTANCE = "DISTANCE"
    DELTA_TOL = "DELTA_TOL"
    OUTPUT = "OUTPUT"

    OUT_Z = "trh_gi_z"
    OUT_SIG = "trh_gi_significant"
    OUT_DELTA = "trh_delta"
    OUT_LABEL = "trh_label"

    def tr(self, string):
        return string

    def createInstance(self):
        return RiskTrendHotspotAlgorithm()

    def name(self):
        return "risk_trend_hotspot"

    def displayName(self):
        return self.tr("Risk Trend Hot-Spot (Gi* × Δ score)")

    def shortHelpString(self):
        return self.tr(
            "<h3>Risk Trend Hot-Spot</h3> <p>Fuses temporal trend (Δ score between two snapshots) "
            "with spatial clustering (Getis-Ord Gi* on the later snapshot) into a single label per "
            "unit - the suite's early-warning tool, answering \"where is risk both clustered AND "
            'getting worse right now." A two-stage design: first compute hot-spot significance on the '
            "later snapshot, then annotate with the trend - simpler than a full space-time scan "
            "statistic (Kulldorff, 1997) while preserving the key operational insight.</p> <ul> "
            "<li><b>Rising / Stable / Cooling hot spot</b> — clustered high values, trajectory "
            "tag.</li> <li><b>Rising / Stable / Cooling cold spot</b> — clustered low values, "
            "trajectory tag.</li> <li><b>Hot / Cold, no cluster</b> — value extreme but not "
            "significantly clustered.</li> <li><b>Not significant</b>.</li> </ul> <p>The significance "
            "test is purely spatial and cross-sectional - it does not test whether the CHANGE is "
            "clustered, only the current level. Only two time points are used, so this cannot "
            "distinguish a genuinely accelerating trend from a single noisy jump; 3+ snapshots would "
            "be needed to fit an actual trend line.</p> <p>Pair with the <i>Resilience Time-Series "
            "Tracker</i> output: <code>ts_later_score</code> as the later score and "
            '<code>ts_delta</code> as the delta.</p> <p>Using the results: "Rising hot spot" is the '
            "strongest early-warning signal - a statistically significant high-value cluster with an "
            "increasing score, the immediate-intervention priority. Check the delta tolerance against "
            "the underlying score's known measurement noise before trusting a Rising/Cooling label at "
            "face value, especially across closely-spaced snapshots.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Layer with later-score and delta fields"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.LATER_SCORE, self.tr("Later-snapshot score field (numeric)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DELTA_FIELD, self.tr("Delta field (later − earlier; numeric)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, self.tr("Distance band (map units)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=500.0, minValue=0.001, maxValue=1e9,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DELTA_TOL, self.tr("Delta tolerance (units below which the trend is 'stable')"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.0, minValue=0.0, maxValue=100.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Risk-trend hot-spot result")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.LATER_SCORE, context)
        delta_field = self.parameterAsString(parameters, self.DELTA_FIELD, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        delta_tol = self.parameterAsDouble(parameters, self.DELTA_TOL, context)

        # Load into memory.
        fids: list[int] = []
        points: dict = {}
        values: dict = {}
        deltas: dict = {}
        geometries: dict = {}
        attributes: dict = {}
        for feat in source.getFeatures():
            if not feat.hasGeometry():
                continue
            v = _safe_float(feat.attribute(score_field))
            if v is None:
                continue
            d = _safe_float(feat.attribute(delta_field))
            centroid = feat.geometry().centroid().asPoint()
            fids.append(feat.id())
            points[feat.id()] = (centroid.x(), centroid.y())
            values[feat.id()] = v
            deltas[feat.id()] = d
            geometries[feat.id()] = QgsGeometry(feat.geometry())
            attributes[feat.id()] = list(feat.attributes())

        n = len(fids)
        if n < 4:
            raise QgsProcessingException(
                f"Need at least 4 valid features for Gi* (got {n})."
            )

        # Build centroid index.
        index = QgsSpatialIndex()
        for fid in fids:
            x, y = points[fid]
            tmp_feat = QgsFeature()
            tmp_feat.setId(fid)
            tmp_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            index.addFeature(tmp_feat)

        # Global stats for Gi*.
        mean = sum(values.values()) / n
        var = sum((v - mean) ** 2 for v in values.values()) / n
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            raise QgsProcessingException(
                "All later-score values are identical — Gi* is undefined."
            )

        # Output schema.
        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_Z, QVariant.Double),
            (self.OUT_SIG, QVariant.Int),
            (self.OUT_DELTA, QVariant.Double),
            (self.OUT_LABEL, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        label_counts: dict = {}
        for idx, fid in enumerate(fids):
            if feedback.isCanceled():
                break
            xi, yi = points[fid]
            rect = QgsRectangle(xi - distance, yi - distance,
                                xi + distance, yi + distance)
            neighbour_ids = index.intersects(rect)
            w_sum = 0.0
            wx_sum = 0.0
            w_sq_sum = 0.0
            for nid in neighbour_ids:
                nx, ny = points[nid]
                d = math.hypot(nx - xi, ny - yi)
                if d > distance:
                    continue
                # Inverse-distance (self gets w=1).
                w = 1.0 if nid == fid else (1.0 / (d if d > 1e-9 else 1e-9))
                w_sum += w
                w_sq_sum += w * w
                wx_sum += w * values[nid]
            try:
                numerator = wx_sum - mean * w_sum
                denom_sq = (n * w_sq_sum - w_sum * w_sum) / (n - 1)
                denom = std * math.sqrt(max(0.0, denom_sq))
                z = numerator / denom if denom > 0 else 0.0
            except (ZeroDivisionError, ValueError):
                z = 0.0
            sig = 1 if abs(z) >= 1.96 else 0
            d_val = deltas[fid]
            lbl = _label(z, sig, d_val, delta_tol)
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(geometries[fid])
            new_attrs = list(attributes[fid])
            while len(new_attrs) < out_fields.size() - 4:
                new_attrs.append(None)
            new_attrs.extend([z, sig, d_val, lbl])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)
            if idx % 50 == 0:
                feedback.setProgress(int(100 * (idx + 1) / n))

        feedback.pushInfo("")
        feedback.pushInfo("─── Risk-trend hot-spot summary ───")
        for lbl in (
            "Rising hot spot", "Stable hot spot", "Cooling hot spot",
            "Rising cold spot", "Stable cold spot", "Cooling cold spot",
            "Hot, no cluster", "Cold, no cluster", "Not significant",
        ):
            feedback.pushInfo(f"  {lbl:<22} : {label_counts.get(lbl, 0)}")
        return {self.OUTPUT: dest_id}
