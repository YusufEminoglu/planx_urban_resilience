# -*- coding: utf-8 -*-
"""Resilience Time-Series Tracker.

Two snapshots of the same scored layer (e.g. 2020 baseline, 2025 measured,
or 2030 target). Joins them on a stable unit ID and emits per-unit deltas
plus a target-gap label.

Inputs:
  - earlier layer + score field + id field
  - later layer + score field + id field (same id semantics)
  - optional target value or per-unit target field

Outputs:
  - layer (geometry from the later snapshot) with:
    - ts_earlier_score, ts_later_score, ts_delta, ts_delta_pct
    - ts_trend         : Improved / Stable / Worsened
    - ts_target_gap    : later - target (positive = below target if higher
                         is better; sign convention depends on user
                         interpretation - documented but not enforced)
"""
from __future__ import annotations

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
)

from .._helpers import clamp


def _trend(delta: float, tol: float = 1.0) -> str:
    if delta < -tol:
        return "Improved"
    if delta > tol:
        return "Worsened"
    return "Stable"


from .._mixins import HelpUrlMixin

class ResilienceTimeSeriesAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    EARLIER = "EARLIER"
    LATER = "LATER"
    EARLIER_ID = "EARLIER_ID"
    LATER_ID = "LATER_ID"
    EARLIER_SCORE = "EARLIER_SCORE"
    LATER_SCORE = "LATER_SCORE"
    TARGET_VALUE = "TARGET_VALUE"
    OUTPUT = "OUTPUT"

    OUT_EARLIER = "ts_earlier_score"
    OUT_LATER = "ts_later_score"
    OUT_DELTA = "ts_delta"
    OUT_DELTA_PCT = "ts_delta_pct"
    OUT_TREND = "ts_trend"
    OUT_TARGET_GAP = "ts_target_gap"

    def tr(self, string):
        return string

    def createInstance(self):
        return ResilienceTimeSeriesAlgorithm()

    def name(self):
        return "resilience_time_series"

    def displayName(self):
        return self.tr("Resilience Time-Series Tracker")

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Resilience Time-Series Tracker</h3>
            <p>Joins two snapshots of the same scored layer on a stable unit
            ID and emits per-unit deltas with a trend label.</p>
            <p>Use cases: monitor a strategy against a 5-year horizon, compare
            two scenario outputs (baseline vs proposed) without rebuilding a
            comparison layer, or chart a single neighbourhood across pre/post-
            intervention years.</p>
            <p>Geometry is taken from the <i>later</i> snapshot.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.EARLIER, self.tr("Earlier snapshot"),
            [QgsProcessing.TypeVectorAnyGeometry],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.EARLIER_ID, self.tr("Earlier ID field"),
            parentLayerParameterName=self.EARLIER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.EARLIER_SCORE, self.tr("Earlier score field (0-100)"),
            parentLayerParameterName=self.EARLIER,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LATER, self.tr("Later snapshot"),
            [QgsProcessing.TypeVectorAnyGeometry],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.LATER_ID, self.tr("Later ID field"),
            parentLayerParameterName=self.LATER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.LATER_SCORE, self.tr("Later score field (0-100)"),
            parentLayerParameterName=self.LATER,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.TARGET_VALUE, self.tr("Target value (optional, e.g. 30 = aim for risk <= 30)"),
            type=QgsProcessingParameterNumber.Double, defaultValue=0.0,
            minValue=-1e6, maxValue=1e6, optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Time-series comparison")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        earlier = self.parameterAsSource(parameters, self.EARLIER, context)
        later = self.parameterAsSource(parameters, self.LATER, context)
        if earlier is None or later is None:
            raise QgsProcessingException("Both earlier and later snapshots are required.")

        e_id = self.parameterAsString(parameters, self.EARLIER_ID, context)
        l_id = self.parameterAsString(parameters, self.LATER_ID, context)
        e_score = self.parameterAsString(parameters, self.EARLIER_SCORE, context)
        l_score = self.parameterAsString(parameters, self.LATER_SCORE, context)
        target = self.parameterAsDouble(parameters, self.TARGET_VALUE, context)

        # Index earlier by id (str-keyed for type tolerance)
        earlier_map: dict = {}
        for feat in earlier.getFeatures():
            key = feat.attribute(e_id)
            if key is None:
                continue
            score = clamp(feat.attribute(e_score), -1e9, 1e9)
            earlier_map[str(key)] = score

        # Build output fields
        out_fields = later.fields()
        for fname, ftype in (
            (self.OUT_EARLIER, QVariant.Double),
            (self.OUT_LATER, QVariant.Double),
            (self.OUT_DELTA, QVariant.Double),
            (self.OUT_DELTA_PCT, QVariant.Double),
            (self.OUT_TREND, QVariant.String),
            (self.OUT_TARGET_GAP, QVariant.Double),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            later.wkbType(), later.sourceCrs(),
        )

        total = max(later.featureCount(), 1)
        matched = 0
        for idx, feat in enumerate(later.getFeatures()):
            if feedback.isCanceled():
                break
            key = feat.attribute(l_id)
            later_score = clamp(feat.attribute(l_score), -1e9, 1e9)
            earlier_score = earlier_map.get(str(key)) if key is not None else None
            if earlier_score is not None and later_score is not None:
                delta = later_score - earlier_score
                pct = (100.0 * delta / earlier_score) if abs(earlier_score) > 1e-6 else None
                trend = _trend(delta)
                matched += 1
            else:
                delta = None
                pct = None
                trend = "No match" if earlier_score is None else "No later score"
            gap = (later_score - target) if later_score is not None else None

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([earlier_score, later_score, delta, pct, trend, gap])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int((idx + 1) / total * 100))

        feedback.pushInfo(f"Matched {matched} / {total} units on ID.")
        return {self.OUTPUT: dest_id}
