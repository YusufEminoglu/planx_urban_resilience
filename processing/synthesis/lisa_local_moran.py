# -*- coding: utf-8 -*-
"""LISA — Local Indicators of Spatial Association (Local Moran's I).

The Hot-Spot Gi* module (v1.20.0) flags clusters; LISA goes one step further
and ALSO labels outliers — a high-value feature surrounded by low values
(HL) or a low-value feature surrounded by high values (LH). That second
class is exactly what planners hunt for when they ask "where are the
under-served pockets next to thriving neighbourhoods?".

For each feature i:
    z_i  = (x_i - mean) / std
    lag  = Σ_j w_ij * z_j     (row-standardised neighbours, j ≠ i)
    I_i  = z_i * lag

Significance: analytic moments under the randomization (conditional
permutation) null hypothesis — Anselin (1995), eq. 13-14 — give
E[I_i] and Var[I_i] per feature from the row-standardised weights and
the sample kurtosis; the z-score is referred to the standard normal.
A Benjamini-Hochberg FDR-adjusted p-value is also reported to control
the multiple-testing problem inherent in n simultaneous local tests.

Quadrant labels:
    HH = high-high cluster      (z_i > 0, lag > 0, I_i > 0, p < 0.05)
    LL = low-low cluster        (z_i < 0, lag < 0, I_i > 0, p < 0.05)
    HL = high-low outlier       (z_i > 0, lag < 0, I_i < 0, p < 0.05)
    LH = low-high outlier       (z_i < 0, lag > 0, I_i < 0, p < 0.05)
    Not significant otherwise.
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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsRectangle,
    QgsSpatialIndex,
)


WEIGHT_METHODS = ("Inverse distance (row-standardised)", "Fixed-distance band (binary)")


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _two_sided_p(z: float) -> float:
    return 2.0 * (1.0 - _norm_cdf(abs(z)))


def _bh_fdr(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values; NaN entries stay NaN."""
    indexed = [(p, i) for i, p in enumerate(pvalues) if not math.isnan(p)]
    adjusted = [float("nan")] * len(pvalues)
    m = len(indexed)
    if m == 0:
        return adjusted
    indexed.sort()
    running_min = 1.0
    for rank in range(m, 0, -1):
        p, orig_idx = indexed[rank - 1]
        running_min = min(running_min, p * m / rank)
        adjusted[orig_idx] = min(running_min, 1.0)
    return adjusted


def _quadrant(z_i: float, lag: float, p: float) -> str:
    if math.isnan(z_i) or math.isnan(lag) or math.isnan(p):
        return "Not significant"
    if p >= 0.05:
        return "Not significant"
    if z_i > 0 and lag > 0:
        return "HH"  # high-high cluster
    if z_i < 0 and lag < 0:
        return "LL"  # low-low cluster
    if z_i > 0 and lag < 0:
        return "HL"  # high-low outlier
    if z_i < 0 and lag > 0:
        return "LH"  # low-high outlier
    return "Not significant"


class LisaLocalMoranAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    DISTANCE = "DISTANCE"
    WEIGHT_METHOD = "WEIGHT_METHOD"
    OUTPUT = "OUTPUT"

    OUT_Z = "lisa_z"
    OUT_LAG = "lisa_lag"
    OUT_I = "lisa_I"
    OUT_P = "lisa_pvalue"
    OUT_P_FDR = "lisa_p_fdr"
    OUT_QUADRANT = "lisa_quadrant"
    OUT_QUADRANT_FDR = "lisa_quad_fdr"

    def tr(self, string):
        return string

    def createInstance(self):
        return LisaLocalMoranAlgorithm()

    def name(self):
        return "lisa_local_moran"

    def displayName(self):
        return self.tr("LISA Local Moran's I (cluster + outlier)")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>LISA Local Moran's I</h3>
            <p>Companion to the Hot-Spot Gi* module — adds outlier detection
            on top of cluster detection. For each feature labels:</p>
            <ul>
              <li><b>HH</b> — high value in a high-value neighbourhood (cluster).</li>
              <li><b>LL</b> — low value in a low-value neighbourhood (cluster).</li>
              <li><b>HL</b> — high value surrounded by low neighbours (outlier).</li>
              <li><b>LH</b> — low value surrounded by high neighbours (outlier).</li>
              <li><b>Not significant</b> at the 95 % level.</li>
            </ul>
            <p>Significance uses the analytic randomization moments of
            Anselin (1995) — per-feature E[I] and Var[I] from the
            row-standardised weights and sample kurtosis. Because n local
            tests run simultaneously, a Benjamini-Hochberg FDR-adjusted
            p-value (<code>lisa_p_fdr</code>) and the corresponding
            conservative quadrant label (<code>lisa_quad_fdr</code>) are
            also written — prefer those when reporting results.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored polygon/point layer"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.VALUE_FIELD, self.tr("Value field (numeric)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCE, self.tr("Distance band (map units)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=500.0, minValue=0.001, maxValue=1e9,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.WEIGHT_METHOD, self.tr("Spatial weight method"),
            options=list(WEIGHT_METHODS), defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("LISA result")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        method_idx = self.parameterAsEnum(parameters, self.WEIGHT_METHOD, context)

        # Load and z-standardise.
        feedback.pushInfo("Loading features…")
        fids: list[int] = []
        points: dict = {}
        values: dict = {}
        geometries: dict = {}
        attributes: dict = {}
        for feat in source.getFeatures():
            if not feat.hasGeometry():
                continue
            try:
                v = float(feat.attribute(value_field))
            except (TypeError, ValueError):
                continue
            if math.isnan(v):
                continue
            centroid = feat.geometry().centroid().asPoint()
            fids.append(feat.id())
            points[feat.id()] = (centroid.x(), centroid.y())
            values[feat.id()] = v
            geometries[feat.id()] = QgsGeometry(feat.geometry())
            attributes[feat.id()] = list(feat.attributes())

        n = len(fids)
        if n < 4:
            raise QgsProcessingException(
                f"Need at least 4 valid features for LISA (got {n})."
            )

        mean = sum(values.values()) / n
        var = sum((v - mean) ** 2 for v in values.values()) / n
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            raise QgsProcessingException(
                "All feature values are identical — local Moran's I is undefined."
            )
        z_values = {fid: (values[fid] - mean) / std for fid in fids}

        # Spatial index over centroids.
        feedback.pushInfo("Building spatial index…")
        index = QgsSpatialIndex()
        for fid in fids:
            x, y = points[fid]
            tmp_feat = QgsFeature()
            tmp_feat.setId(fid)
            tmp_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            index.addFeature(tmp_feat)

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_Z, QVariant.Double),
            (self.OUT_LAG, QVariant.Double),
            (self.OUT_I, QVariant.Double),
            (self.OUT_P, QVariant.Double),
            (self.OUT_P_FDR, QVariant.Double),
            (self.OUT_QUADRANT, QVariant.String),
            (self.OUT_QUADRANT_FDR, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        feedback.pushInfo(f"Computing local Moran's I over {n} features…")

        # Sample kurtosis of the standardised variable (m2 == 1 by
        # construction, so b2 reduces to the fourth moment of z).
        b2 = sum(zv ** 4 for zv in z_values.values()) / n
        e_i = -1.0 / (n - 1)  # E[I_i] for row-standardised weights

        # Pass 1 — statistics per feature (Anselin 1995 randomization moments).
        results: list[tuple[int, float, float, float]] = []  # fid, lag, I, p
        for idx, fid in enumerate(fids):
            if feedback.isCanceled():
                break
            xi, yi = points[fid]
            rect = QgsRectangle(xi - distance, yi - distance,
                                xi + distance, yi + distance)
            cand_ids = index.intersects(rect)

            weights: list[tuple[int, float]] = []
            for nid in cand_ids:
                if nid == fid:
                    continue
                nx, ny = points[nid]
                d = math.hypot(nx - xi, ny - yi)
                if d > distance or d <= 0:
                    continue
                w = (1.0 / d) if method_idx == 0 else 1.0
                weights.append((nid, w))
            if not weights:
                lag = float("nan")
                moran_i = float("nan")
                p = float("nan")
            else:
                # Row-standardise.
                w_sum = sum(w for _nid, w in weights)
                std_weights = [(nid, w / w_sum) for nid, w in weights]
                lag = sum(w * z_values[nid] for nid, w in std_weights)
                z_i = z_values[fid]
                moran_i = z_i * lag
                # Var[I_i] under randomization (Anselin 1995):
                #   E[I²] = w2 (n − b2)/(n − 1)
                #         + (wi.² − w2)(2 b2 − n)/((n − 1)(n − 2))
                # with wi. = 1 (row-standardised) and w2 = Σ wij².
                w2 = sum(w * w for _nid, w in std_weights)
                e_i2 = (w2 * (n - b2) / (n - 1)
                        + (1.0 - w2) * (2.0 * b2 - n) / ((n - 1) * (n - 2)))
                var_i = max(e_i2 - e_i * e_i, 1e-12)
                z_stat = (moran_i - e_i) / math.sqrt(var_i)
                p = _two_sided_p(z_stat)
            results.append((fid, lag, moran_i, p))
            if idx % 100 == 0:
                feedback.setProgress(int(50 * (idx + 1) / n))

        # Pass 2 — FDR adjustment across all n simultaneous tests, then write.
        p_adjusted = _bh_fdr([r[3] for r in results])
        quadrant_counts: dict = {}
        fdr_counts: dict = {}
        for idx, ((fid, lag, moran_i, p), p_fdr) in enumerate(zip(results, p_adjusted)):
            lag_safe = lag if not math.isnan(lag) else 0.0
            cls = _quadrant(z_values[fid], lag_safe, p)
            cls_fdr = _quadrant(z_values[fid], lag_safe, p_fdr)
            quadrant_counts[cls] = quadrant_counts.get(cls, 0) + 1
            fdr_counts[cls_fdr] = fdr_counts.get(cls_fdr, 0) + 1

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(geometries[fid])
            new_attrs = list(attributes[fid])
            while len(new_attrs) < out_fields.size() - 7:
                new_attrs.append(None)
            new_attrs.extend([
                z_values[fid],
                lag if not math.isnan(lag) else None,
                moran_i if not math.isnan(moran_i) else None,
                p if not math.isnan(p) else None,
                p_fdr if not math.isnan(p_fdr) else None,
                cls,
                cls_fdr,
            ])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)
            if idx % 100 == 0:
                feedback.setProgress(50 + int(50 * (idx + 1) / n))

        feedback.pushInfo("")
        feedback.pushInfo("─── LISA summary (95 % significance / FDR-adjusted) ───")
        for q in ("HH", "LL", "HL", "LH", "Not significant"):
            feedback.pushInfo(
                f"  {q:<17} : {quadrant_counts.get(q, 0)} / {fdr_counts.get(q, 0)}"
            )
        return {self.OUTPUT: dest_id}
