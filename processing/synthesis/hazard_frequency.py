# -*- coding: utf-8 -*-
"""Multi-Period Hazard Frequency Aggregation.

Combines N temporal hazard snapshots (e.g., the same flood model run for
2020 / 2030 / 2050 climate scenarios, or seismic Monte Carlo runs across
multiple magnitudes) into one composite score per planning unit. The
result captures BOTH frequency (how many periods scored above the
threshold) AND intensity (mean / max score across periods).

Inputs:
  - planning unit polygon layer (target geometry)
  - up to 8 score layers (any polygons or points with a 0-100 field)
  - per-source score field name (same on every source for simplicity;
    layers without that field fall back to the default)
  - exposure threshold (default 50) — used for the frequency count
  - aggregation mode (mean, max, frequency-weighted mean)

Outputs:
  - per-unit fields: hf_frequency (how many of the N sources scored
    above the threshold at this unit), hf_mean, hf_max, hf_min,
    hf_composite (the chosen aggregation), hf_class.

Spatial join is done with `QgsSpatialIndex` bbox prefilter + per-pair
intersection check; for each source we take the maximum overlapping
score at each unit (matches the convention in
`join_scores_to_units.py`).
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
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsSpatialIndex,
)


AGG_MODES = ("Mean of all periods", "Maximum across periods", "Frequency-weighted mean")


def _safe_float(value, default=0.0):
    try:
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _risk_class(score: float) -> str:
    if score >= 75:
        return "Very High"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Moderate"
    return "Low"


from .._mixins import HelpUrlMixin  # noqa: E402




class HazardFrequencyAggregationAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    UNITS = "UNITS"
    SOURCES = "SOURCES"
    SCORE_FIELD = "SCORE_FIELD"
    THRESHOLD = "THRESHOLD"
    AGG_MODE = "AGG_MODE"
    OUTPUT = "OUTPUT"

    OUT_FREQ = "hf_frequency"
    OUT_MEAN = "hf_mean"
    OUT_MAX = "hf_max"
    OUT_MIN = "hf_min"
    OUT_COMPOSITE = "hf_composite"
    OUT_CLASS = "hf_class"

    def tr(self, string):
        return string

    def createInstance(self):
        return HazardFrequencyAggregationAlgorithm()

    def name(self):
        return "hazard_frequency_aggregation"

    def displayName(self):
        return self.tr("Multi-Period Hazard Frequency Aggregation")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Multi-Period Hazard Frequency Aggregation</h3>
            <p>Collapse N temporal hazard snapshots (e.g., the same flood
            model run for 2020 / 2030 / 2050, or seismic Monte Carlo
            across magnitudes) into ONE composite per planning unit.</p>
            <p>Output fields:</p>
            <ul>
              <li><code>hf_frequency</code> — count of source layers whose intersecting score exceeds the threshold at this unit.</li>
              <li><code>hf_mean</code> / <code>hf_max</code> / <code>hf_min</code> — statistics of the scores across the source layers.</li>
              <li><code>hf_composite</code> — Mean, Max, or Frequency-weighted mean depending on the chosen mode. Frequency-weighted mean = mean × (freq / N) so units that score high in BOTH many periods AND high intensity rise to the top.</li>
              <li><code>hf_class</code> — Very High / High / Moderate / Low based on the composite.</li>
            </ul>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.UNITS, self.tr("Planning units (polygons)"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.SOURCES,
            self.tr("Source hazard layers (2-8 score layers)"),
            layerType=QgsProcessing.TypeVectorPolygon,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SCORE_FIELD, self.tr("Score field name (same on every source)"),
            defaultValue="score",
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, self.tr("Frequency threshold (0-100)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=50.0, minValue=0.0, maxValue=100.0,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.AGG_MODE, self.tr("Composite aggregation mode"),
            options=list(AGG_MODES), defaultValue=2,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Aggregated units")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        units = self.parameterAsSource(parameters, self.UNITS, context)
        if units is None:
            raise QgsProcessingException("Planning units layer is required.")
        sources = self.parameterAsLayerList(parameters, self.SOURCES, context) or []
        if len(sources) < 2:
            raise QgsProcessingException("Provide at least two source hazard layers.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        threshold = self.parameterAsDouble(parameters, self.THRESHOLD, context)
        agg_idx = self.parameterAsEnum(parameters, self.AGG_MODE, context)

        # Index each source layer once.
        feedback.pushInfo(f"Indexing {len(sources)} source layers…")
        source_records: list = []  # (label, list[(geom, score)], QgsSpatialIndex, fid->geom_score)
        for src in sources:
            label = src.name()
            records: dict = {}
            index = QgsSpatialIndex()
            for feat in src.getFeatures():
                if not feat.hasGeometry():
                    continue
                score = _safe_float(feat.attribute(score_field))
                records[feat.id()] = (QgsGeometry(feat.geometry()), score)
                index.addFeature(feat)
            source_records.append((label, records, index))
            feedback.pushInfo(f"  {label:<30} features = {len(records)}")

        # Output schema.
        out_fields = units.fields()
        for fname, ftype in (
            (self.OUT_FREQ, QVariant.Int),
            (self.OUT_MEAN, QVariant.Double),
            (self.OUT_MAX, QVariant.Double),
            (self.OUT_MIN, QVariant.Double),
            (self.OUT_COMPOSITE, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            units.wkbType(), units.sourceCrs(),
        )

        n_sources = len(source_records)
        total = max(units.featureCount(), 1)
        for idx, feat in enumerate(units.getFeatures()):
            if feedback.isCanceled():
                break
            if not feat.hasGeometry():
                continue
            unit_geom = feat.geometry()
            bbox = unit_geom.boundingBox()

            scores: list[float] = []
            for _label, records, index in source_records:
                best = 0.0
                for cand_fid in index.intersects(bbox):
                    cand_geom, cand_score = records.get(cand_fid, (None, 0.0))
                    if cand_geom is None:
                        continue
                    if cand_geom.intersects(unit_geom):
                        if cand_score > best:
                            best = cand_score
                scores.append(best)

            freq = sum(1 for s in scores if s >= threshold)
            mean = sum(scores) / n_sources
            mx = max(scores)
            mn = min(scores)
            if agg_idx == 0:
                composite = mean
            elif agg_idx == 1:
                composite = mx
            else:
                composite = mean * (freq / n_sources)
            composite = max(0.0, min(100.0, composite))

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(unit_geom)
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([freq, mean, mx, mn, composite, _risk_class(composite)])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            if idx % 25 == 0:
                feedback.setProgress(int(100 * (idx + 1) / total))

        return {self.OUTPUT: dest_id}
