# -*- coding: utf-8 -*-
"""Population-Weighted Exposure.

Bridges the gap between a 0-100 physical hazard / composite score and a
human-impact summary: how many people sit inside each risk class? where is
the highest expected exposure?

Inputs:
  - scored layer with a 0-100 score field per planning unit
  - either a population field on the SAME layer, OR a population layer
    (point/polygon) intersected with the scored units

Outputs:
  - per-unit: pop_total, pop_exposed (= score/100 × pop_total), exposure_class
  - study-area summary (printed to processing log): total population,
    population in each risk class, expected exposure intensity, top 10 units
    by exposed population.

Used to translate "this neighbourhood scores 80/100 on flood" into
"this neighbourhood has ~12 000 residents in the high-flood band".
"""
from __future__ import annotations

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
    QgsSpatialIndex,
)


def _risk_class(score: float) -> str:
    if score >= 75:
        return "Very High"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Moderate"
    return "Low"


from .._mixins import GROUP_SYNTHESIS, GroupMixin, HelpUrlMixin  # noqa: E402


class PopulationWeightedExposureAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_SYNTHESIS
    ICON = "tool_population_weighted_exposure.png"
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    POP_FIELD = "POP_FIELD"
    POP_LAYER = "POP_LAYER"
    POP_LAYER_FIELD = "POP_LAYER_FIELD"
    OUTPUT = "OUTPUT"

    OUT_TOTAL = "pop_total"
    OUT_EXPOSED = "pop_exposed"
    OUT_CLASS = "exposure_class"
    OUT_INTENSITY = "exposure_intensity"

    def tr(self, string):
        return string

    def createInstance(self):
        return PopulationWeightedExposureAlgorithm()

    def name(self):
        return "population_weighted_exposure"

    def displayName(self):
        return self.tr("Population-Weighted Exposure")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Population-Weighted Exposure</h3>
            <p>Translates a 0-100 hazard score into a human-impact estimate, the
            standard bridge from physical hazard to human impact in disaster-risk
            literature (UNDRR, 2019) - a hazard score alone says nothing about how
            many people are affected, which is usually the number that drives
            budgetary attention. Population is taken either from a field on the
            scored layer or from a separate point/polygon layer summed inside each
            unit.</p>
            <p>pop_exposed = score/100 x pop_total assumes risk scales linearly with
            score - a transparent, defensible screening approximation, not a
            validated dose-response curve for any specific hazard. Population is a
            snapshot with no diurnal/seasonal variation (daytime workplace vs.
            nighttime residential population can differ substantially).</p>
            <p>Per-unit outputs:</p>
            <ul>
              <li><code>pop_total</code> — population in this unit.</li>
              <li><code>pop_exposed</code> — score/100 × pop_total.</li>
              <li><code>exposure_intensity</code> — Very High / High / Moderate / Low based on the score.</li>
              <li><code>exposure_class</code> — same as intensity (kept for symbology naming compatibility).</li>
            </ul>
            <p>Study-area summary is printed to the processing log: total population,
            breakdown by risk class, top 10 units by exposed population.</p>
            <p>Using the results: compare pop_exposed rankings against raw score
            rankings - a moderate-hazard, high-population unit can outrank a
            high-hazard, low-population one on exposure, a finding this module exists
            to surface. Where the hazard-to-harm relationship is known to be strongly
            non-linear (e.g. flood depth-damage curves, typically convex), this
            linear model understates the difference - use a hazard-specific
            dose-response function instead.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored planning units"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SCORE_FIELD, self.tr("Score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD,
            self.tr("Population field on the scored layer (option A)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.POP_LAYER,
            self.tr("Population point/polygon layer (option B)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POP_LAYER_FIELD,
            self.tr("Population field on the population layer (used with option B)"),
            parentLayerParameterName=self.POP_LAYER,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Exposure layer")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)
        pop_layer = self.parameterAsSource(parameters, self.POP_LAYER, context)
        pop_layer_field = self.parameterAsString(parameters, self.POP_LAYER_FIELD, context)

        if not pop_field and pop_layer is None:
            raise QgsProcessingException(
                "Provide either a population field on the scored layer or a separate "
                "population layer."
            )

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_TOTAL, QVariant.Double),
            (self.OUT_EXPOSED, QVariant.Double),
            (self.OUT_INTENSITY, QVariant.String),
            (self.OUT_CLASS, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        # Pre-index population layer if option B was chosen.
        pop_records: list = []
        pop_index = None
        if pop_layer is not None:
            feedback.pushInfo("Indexing population layer…")
            pop_index = QgsSpatialIndex()
            for feat in pop_layer.getFeatures():
                if not feat.hasGeometry():
                    continue
                try:
                    pop = float(feat.attribute(pop_layer_field)) if pop_layer_field else 1.0
                except (TypeError, ValueError):
                    pop = 1.0
                pop_records.append((feat.id(), feat.geometry(), pop))
                pop_index.addFeature(feat)

        # Per-unit calculation.
        total_pop = 0.0
        class_totals = {"Very High": 0.0, "High": 0.0, "Moderate": 0.0, "Low": 0.0}
        ranked: list = []  # (exposed, unit_id, class)

        total = max(source.featureCount(), 1)
        for idx, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            try:
                score = max(0.0, min(100.0, float(feat.attribute(score_field))))
            except (TypeError, ValueError):
                score = 0.0

            if pop_field:
                try:
                    pop = float(feat.attribute(pop_field))
                except (TypeError, ValueError):
                    pop = 0.0
            else:
                # Sum population from records whose centroid falls inside this unit.
                pop = 0.0
                unit_geom = feat.geometry()
                if pop_index is not None:
                    for pid in pop_index.intersects(unit_geom.boundingBox()):
                        for rec_id, rec_geom, rec_pop in pop_records:
                            if rec_id != pid:
                                continue
                            point = (rec_geom.centroid().asPoint()
                                     if rec_geom.type() != 0 else rec_geom.asPoint())
                            if unit_geom.contains(QgsGeometry.fromPointXY(point)):
                                pop += rec_pop
                            break

            exposed = (score / 100.0) * pop
            cls = _risk_class(score)
            total_pop += pop
            class_totals[cls] = class_totals.get(cls, 0.0) + pop
            ranked.append((exposed, feat.id(), cls))

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 4:
                new_attrs.append(None)
            new_attrs.extend([pop, exposed, cls, cls])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            if idx % 25 == 0:
                feedback.setProgress(int(100 * (idx + 1) / total))

        # Study-area summary log.
        ranked.sort(key=lambda r: -r[0])
        feedback.pushInfo("")
        feedback.pushInfo("─── Population-Weighted Exposure summary ───")
        feedback.pushInfo(f"Total population in study area: {total_pop:,.0f}")
        for cls in ("Very High", "High", "Moderate", "Low"):
            v = class_totals.get(cls, 0.0)
            pct = (100.0 * v / total_pop) if total_pop > 0 else 0.0
            feedback.pushInfo(f"  {cls:<10} : {v:>12,.0f}  ({pct:5.1f}%)")
        feedback.pushInfo("")
        feedback.pushInfo("Top units by exposed population:")
        for exposed, fid, cls in ranked[:10]:
            feedback.pushInfo(f"  fid={fid:<8} {cls:<10} exposed≈{exposed:,.0f}")

        return {self.OUTPUT: dest_id}
