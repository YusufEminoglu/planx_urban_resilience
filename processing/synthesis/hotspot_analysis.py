# -*- coding: utf-8 -*-
"""Hot-Spot Cluster Analysis (Getis-Ord Gi*).

For each feature i, Gi* measures the degree to which its neighborhood's
values are clustered relative to the global mean. High positive z-scores
mean a "hot spot" (cluster of high values); high negative z-scores mean a
"cold spot" (cluster of low values).

Implementation choices:
  - Spatial weights: row-standardised inverse-distance OR fixed-distance
    binary (user picks the method).
  - All math in pure Python — no numpy dependency. For 5 000-feature
    layers this finishes in a few seconds; for 50 000+ consider the
    QGIS native Hot Spot Analysis if it ships in your QGIS build.
  - Output columns: gi_zscore, gi_pvalue, gi_class (one of
    Cold-99 / Cold-95 / Cold-90 / Not significant / Hot-90 / Hot-95 /
    Hot-99). Includes self in the neighborhood (Gi* not Gi).

References:
  Getis & Ord (1992); Ord & Getis (1995).
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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
)


WEIGHT_METHODS = ("Inverse distance (1/d, row-standardised)", "Fixed distance band (binary)")


def _norm_cdf(z: float) -> float:
    """Standard normal CDF using erf; pure Python."""
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


def _gi_class(z: float, p: float) -> str:
    if math.isnan(z) or math.isnan(p):
        return "Not significant"
    if z > 0:
        if p < 0.01:
            return "Hot-99"
        if p < 0.05:
            return "Hot-95"
        if p < 0.10:
            return "Hot-90"
    else:
        if p < 0.01:
            return "Cold-99"
        if p < 0.05:
            return "Cold-95"
        if p < 0.10:
            return "Cold-90"
    return "Not significant"


from .._mixins import HelpUrlMixin  # noqa: E402




class HotSpotAnalysisAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    VALUE_FIELD = "VALUE_FIELD"
    DISTANCE = "DISTANCE"
    WEIGHT_METHOD = "WEIGHT_METHOD"
    OUTPUT = "OUTPUT"

    OUT_Z = "gi_zscore"
    OUT_P = "gi_pvalue"
    OUT_P_FDR = "gi_p_fdr"
    OUT_CLASS = "gi_class"
    OUT_CLASS_FDR = "gi_class_fdr"

    def tr(self, string):
        return string

    def createInstance(self):
        return HotSpotAnalysisAlgorithm()

    def name(self):
        return "hotspot_analysis_getis_ord"

    def displayName(self):
        return self.tr("Hot-Spot Cluster Analysis (Getis-Ord Gi*)")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Hot-Spot Cluster Analysis (Getis-Ord Gi*)</h3>
            <p>Tags each feature as a statistically significant <b>hot
            spot</b> (cluster of high values), <b>cold spot</b> (cluster of
            low values), or <b>not significant</b>, based on its neighbours'
            values. Use on any 0-100 resilience score: composite, social
            vulnerability, recovery capacity, etc.</p>
            <p><b>Outputs added to each feature:</b></p>
            <ul>
              <li><code>gi_zscore</code> — standardised statistic; |z| > 1.65 ≈ 90% confidence.</li>
              <li><code>gi_pvalue</code> — two-sided p-value derived from z.</li>
              <li><code>gi_p_fdr</code> — Benjamini-Hochberg FDR-adjusted p-value (controls false discoveries across the n simultaneous local tests).</li>
              <li><code>gi_class</code> — Hot-99 / Hot-95 / Hot-90 / Not significant / Cold-90 / Cold-95 / Cold-99.</li>
              <li><code>gi_class_fdr</code> — same labels from the FDR-adjusted p-value; prefer this when reporting.</li>
            </ul>
            <p>Spatial weights are either <b>inverse distance</b> (row-standardised) or a <b>fixed-distance band</b> (1 if within distance, else 0). Self is always included (Gi*, not Gi).</p>
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
            self.DISTANCE,
            self.tr("Distance band (map units)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=500.0, minValue=0.001, maxValue=1e9,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.WEIGHT_METHOD, self.tr("Spatial weight method"),
            options=list(WEIGHT_METHODS), defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Hot-spot result")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        value_field = self.parameterAsString(parameters, self.VALUE_FIELD, context)
        distance = self.parameterAsDouble(parameters, self.DISTANCE, context)
        method_idx = self.parameterAsEnum(parameters, self.WEIGHT_METHOD, context)

        # Load features into memory + their centroid coords + value.
        feedback.pushInfo("Loading features…")
        fids: list[int] = []
        points = {}   # fid -> (x, y)
        values = {}   # fid -> float
        geometries = {}  # fid -> QgsGeometry (for output)
        attributes = {}  # fid -> list
        for feat in source.getFeatures():
            if not feat.hasGeometry():
                continue
            geom = feat.geometry()
            try:
                v = float(feat.attribute(value_field))
            except (TypeError, ValueError):
                continue
            if math.isnan(v):
                continue
            centroid = geom.centroid().asPoint()
            fids.append(feat.id())
            points[feat.id()] = (centroid.x(), centroid.y())
            values[feat.id()] = v
            geometries[feat.id()] = QgsGeometry(geom)
            attributes[feat.id()] = list(feat.attributes())

        n = len(fids)
        if n < 4:
            raise QgsProcessingException(
                f"Need at least 4 valid features for a Gi* analysis (got {n})."
            )

        # Build a spatial index over centroid points for neighbour lookup.
        feedback.pushInfo("Building spatial index…")
        index = QgsSpatialIndex()
        for fid in fids:
            x, y = points[fid]
            tmp_feat = QgsFeature()
            tmp_feat.setId(fid)
            tmp_feat.setGeometry(QgsGeometry.fromPointXY(_xy_point(x, y)))
            index.addFeature(tmp_feat)

        # Global stats (Gi* assumes a fixed mean/variance for the population).
        total = sum(values.values())
        mean = total / n
        var = sum((v - mean) ** 2 for v in values.values()) / n
        s = math.sqrt(var) if var > 0 else 0.0

        # Output fields.
        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_Z, QVariant.Double),
            (self.OUT_P, QVariant.Double),
            (self.OUT_P_FDR, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
            (self.OUT_CLASS_FDR, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        feedback.pushInfo(f"Computing Gi* over {n} features…")
        from qgis.core import QgsRectangle

        # Pass 1 — z and p per feature.
        results: list[tuple[int, float, float]] = []  # fid, z, p
        for idx, fid in enumerate(fids):
            if feedback.isCanceled():
                break
            xi, yi = points[fid]
            rect = QgsRectangle(xi - distance, yi - distance,
                                xi + distance, yi + distance)
            neighbour_ids = index.intersects(rect)
            # Build weights (include self) over the candidate set.
            w_sum = 0.0
            wx_sum = 0.0
            w_sq_sum = 0.0
            for nid in neighbour_ids:
                nx, ny = points[nid]
                d = math.hypot(nx - xi, ny - yi)
                if d > distance:
                    continue
                if method_idx == 0:
                    # Inverse distance, self gets a small bonus to avoid /0
                    if nid == fid:
                        w = 1.0
                    else:
                        w = 1.0 / (d if d > 1e-9 else 1e-9)
                else:
                    w = 1.0  # fixed-distance binary
                w_sum += w
                w_sq_sum += w * w
                wx_sum += w * values[nid]

            # Gi* standardised statistic.
            try:
                numerator = wx_sum - mean * w_sum
                denom_sq = (n * w_sq_sum - w_sum * w_sum) / (n - 1)
                denom = s * math.sqrt(max(0.0, denom_sq))
                z = numerator / denom if denom > 0 else float("nan")
            except (ZeroDivisionError, ValueError):
                z = float("nan")
            p = _two_sided_p(z) if not math.isnan(z) else float("nan")
            results.append((fid, z, p))
            if idx % 100 == 0:
                feedback.setProgress(int(50 * (idx + 1) / n))

        # Pass 2 — Benjamini-Hochberg FDR across the n simultaneous tests.
        p_adjusted = _bh_fdr([r[2] for r in results])
        for idx, ((fid, z, p), p_fdr) in enumerate(zip(results, p_adjusted)):
            cls = _gi_class(z, p)
            cls_fdr = _gi_class(z, p_fdr)

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(geometries[fid])
            new_attrs = list(attributes[fid])
            while len(new_attrs) < out_fields.size() - 5:
                new_attrs.append(None)
            new_attrs.extend([z if not math.isnan(z) else None,
                              p if not math.isnan(p) else None,
                              p_fdr if not math.isnan(p_fdr) else None,
                              cls,
                              cls_fdr])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            if idx % 100 == 0:
                feedback.setProgress(50 + int(50 * (idx + 1) / n))

        return {self.OUTPUT: dest_id}


def _xy_point(x: float, y: float):
    """Late-import shim so the top of the file stays clean."""
    from qgis.core import QgsPointXY
    return QgsPointXY(x, y)
