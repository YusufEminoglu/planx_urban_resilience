# -*- coding: utf-8 -*-
"""Climate Projection Overlay.

Apply a literature-based amplification factor to a today's hazard/composite
score so planners can see the unit-level impact of a warming-scenario.
Offline-first: no CMIP/downscaled rasters required.

Default amplification factors (multipliers applied to the today-score; not
hazard-specific because this is a generic overlay - users can refine per
hazard by running the algorithm once per scenario per layer):

  Scenario          Amplification
  ---------------   -------------
  Stable (today)    1.00
  Mild  +1.5C 2050  1.15
  Moderate +2C 2070 1.30
  High  +3C 2100    1.60

Output fields added per feature:
  - cp_today        copy of source score, validated and clamped
  - cp_scenario     scenario label
  - cp_factor       amplification factor used
  - cp_projected    today * factor, clamped to 0-100
  - cp_delta        projected - today (positive = worse under climate change)
  - cp_delta_class  Improved / Stable / Slight / Major increase
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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
)

from .._helpers import clamp


SCENARIOS = [
    ("Stable (today)", 1.00),
    ("Mild (+1.5C, ~2050)", 1.15),
    ("Moderate (+2C, ~2070)", 1.30),
    ("High (+3C, ~2100)", 1.60),
    ("Custom (use override)", None),
]


def _delta_class(delta: float) -> str:
    if delta < -1.0:
        return "Improved"
    if delta <= 1.0:
        return "Stable"
    if delta <= 10.0:
        return "Slight increase"
    if delta <= 25.0:
        return "Notable increase"
    return "Major increase"


from .._mixins import HelpUrlMixin

class ClimateProjectionOverlayAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    SCENARIO = "SCENARIO"
    CUSTOM_FACTOR = "CUSTOM_FACTOR"
    OUTPUT = "OUTPUT"

    OUT_TODAY = "cp_today"
    OUT_SCENARIO = "cp_scenario"
    OUT_FACTOR = "cp_factor"
    OUT_PROJECTED = "cp_projected"
    OUT_DELTA = "cp_delta"
    OUT_CLASS = "cp_delta_class"

    def tr(self, string):
        return string

    def createInstance(self):
        return ClimateProjectionOverlayAlgorithm()

    def name(self):
        return "climate_projection_overlay"

    def displayName(self):
        return self.tr("Climate Projection Overlay")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Climate Projection Overlay</h3>
            <p>Apply a literature-based amplification factor to a today's
            hazard/composite score to estimate impact under a warming scenario.
            Offline-first: no CMIP/downscaled rasters required.</p>
            <p><b>Scenarios:</b></p>
            <ul>
              <li>Stable (today) - factor 1.00</li>
              <li>Mild (+1.5C, ~2050) - factor 1.15</li>
              <li>Moderate (+2C, ~2070) - factor 1.30</li>
              <li>High (+3C, ~2100) - factor 1.60</li>
              <li>Custom - use the explicit factor parameter</li>
            </ul>
            <p>For hazard-specific factors (heat 1.3, flood 1.5, etc.) run the
            algorithm once per hazard with a Custom factor.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored layer"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SCORE_FIELD, self.tr("Score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.SCENARIO, self.tr("Scenario"),
            options=[name for name, _f in SCENARIOS], defaultValue=2,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CUSTOM_FACTOR,
            self.tr("Custom amplification factor (used only if scenario = Custom)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.30, minValue=0.1, maxValue=5.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Projected scores")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        scenario_idx = self.parameterAsEnum(parameters, self.SCENARIO, context)
        custom_factor = self.parameterAsDouble(parameters, self.CUSTOM_FACTOR, context)

        scenario_name, builtin_factor = SCENARIOS[scenario_idx]
        factor = builtin_factor if builtin_factor is not None else custom_factor
        if builtin_factor is None:
            scenario_name = f"Custom (x{factor:.2f})"

        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_TODAY, QVariant.Double),
            (self.OUT_SCENARIO, QVariant.String),
            (self.OUT_FACTOR, QVariant.Double),
            (self.OUT_PROJECTED, QVariant.Double),
            (self.OUT_DELTA, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        total = max(source.featureCount(), 1)
        for idx, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            today = clamp(feature.attribute(score_field))
            if today is None:
                today_attr = None
                projected = None
                delta = None
                cls = "No data"
            else:
                today_attr = today
                projected = clamp(today * factor) or 0.0
                delta = projected - today
                cls = _delta_class(delta)

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feature.geometry())
            new_attrs = list(feature.attributes())
            while len(new_attrs) < out_fields.size() - 6:
                new_attrs.append(None)
            new_attrs.extend([today_attr, scenario_name, factor, projected, delta, cls])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int((idx + 1) / total * 100))

        feedback.pushInfo(f"Applied scenario '{scenario_name}' with factor {factor:.3f}.")
        return {self.OUTPUT: dest_id}
