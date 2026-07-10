# -*- coding: utf-8 -*-
"""Join Hazard Scores to Planning Units.

Spatially joins up to five hazard/score layers onto planning-unit polygons.
For each unit, takes the **maximum** valid score among intersecting features
(useful for joining grid cells, parcel scores, or neighborhood polygons).

Outputs the input attributes plus new numeric fields ready for Multi-Hazard
Composite, Adaptation Priority, or Risk-Recovery Matrix.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterString,
)

from .._helpers import clamp


def _max_intersect_score(unit_geom, source, field_name):
    if not field_name:
        return None
    best = None
    for feat in source.getFeatures():
        if not feat.hasGeometry():
            continue
        if not unit_geom.intersects(feat.geometry()):
            continue
        value = clamp(feat.attribute(field_name))
        if value is None:
            continue
        best = value if best is None else max(best, value)
    return best


from .._mixins import HelpUrlMixin  # noqa: E402


class JoinScoresToPlanningUnitsAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    UNITS = "UNITS"
    SOURCE1 = "SOURCE1"
    FIELD1 = "FIELD1"
    OUT1 = "OUT1"
    SOURCE2 = "SOURCE2"
    FIELD2 = "FIELD2"
    OUT2 = "OUT2"
    SOURCE3 = "SOURCE3"
    FIELD3 = "FIELD3"
    OUT3 = "OUT3"
    SOURCE4 = "SOURCE4"
    FIELD4 = "FIELD4"
    OUT4 = "OUT4"
    SOURCE5 = "SOURCE5"
    FIELD5 = "FIELD5"
    OUT5 = "OUT5"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return JoinScoresToPlanningUnitsAlgorithm()

    def name(self):
        return "join_scores_to_planning_units"

    def displayName(self):
        return self.tr("Join Hazard Scores to Planning Units")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Join Hazard Scores to Planning Units</h3>
            <p>Attach up to five 0-100 score fields from other layers onto
            planning-unit polygons. Uses the <b>maximum</b> score among
            intersecting features per unit.</p>
            <p>Typical workflow: run Heat / Flood / Social modules, then join
            their score fields here before Multi-Hazard Composite or Adaptation
            Priority Synthesis.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.UNITS,
            self.tr("Planning units (polygons)"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        for idx in range(1, 6):
            self.addParameter(QgsProcessingParameterFeatureSource(
                getattr(self, f"SOURCE{idx}"),
                self.tr(f"Score layer {idx} (optional)"),
                [
                    QgsProcessing.TypeVectorPoint,
                    QgsProcessing.TypeVectorPolygon,
                    QgsProcessing.TypeVectorLine,
                ],
                optional=True,
            ))
            self.addParameter(QgsProcessingParameterField(
                getattr(self, f"FIELD{idx}"),
                self.tr(f"Score field {idx}"),
                parentLayerParameterName=getattr(self, f"SOURCE{idx}"),
                type=QgsProcessingParameterField.Numeric,
                optional=True,
            ))
            self.addParameter(QgsProcessingParameterString(
                getattr(self, f"OUT{idx}"),
                self.tr(f"Output field name {idx} (e.g. heat_score)"),
                defaultValue="",
                optional=True,
            ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Planning units with joined scores"),
        ))

    def processAlgorithm(self, parameters, context, feedback):
        units = self.parameterAsSource(parameters, self.UNITS, context)
        if units is None:
            raise QgsProcessingException("Planning units layer is required.")

        joins: list[tuple] = []
        for idx in range(1, 6):
            source = self.parameterAsSource(parameters, getattr(self, f"SOURCE{idx}"), context)
            field = self.parameterAsString(parameters, getattr(self, f"FIELD{idx}"), context) or ""
            out_name = self.parameterAsString(parameters, getattr(self, f"OUT{idx}"), context) or ""
            if source is None or not field:
                continue
            if not out_name:
                out_name = f"score_{idx}"
            joins.append((source, field, out_name))

        if not joins:
            raise QgsProcessingException("Provide at least one score layer and field.")

        out_fields = QgsFields()
        for fld in units.fields():
            out_fields.append(fld)
        for _source, _field, out_name in joins:
            if out_fields.indexOf(out_name) < 0:
                out_fields.append(QgsField(out_name, QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            units.wkbType(), units.sourceCrs(),
        )

        total = max(units.featureCount(), 1)
        for row, unit in enumerate(units.getFeatures()):
            if feedback.isCanceled():
                break
            geom = unit.geometry()
            attrs = {fld.name(): unit[fld.name()] for fld in units.fields()}
            for source, field, out_name in joins:
                attrs[out_name] = _max_intersect_score(geom, source, field)
            feat = QgsFeature(out_fields)
            feat.setGeometry(geom)
            feat.setAttributes([attrs.get(fld.name()) for fld in out_fields])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int((row + 1) / total * 100))

        feedback.pushInfo(f"Joined {len(joins)} score field(s) onto planning units.")
        return {self.OUTPUT: dest_id}
