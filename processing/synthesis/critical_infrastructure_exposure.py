# -*- coding: utf-8 -*-
"""Critical Infrastructure Exposure.

Crosses a scored hazard layer with a critical-facility layer (schools,
hospitals, fire stations, water/power assets, etc.) and surfaces the
facilities that are both highly exposed AND highly critical — the right
shortlist for retrofit / hardening programmes.

Inputs:
  - hazard layer with a 0-100 score field
  - facility layer (points or polygons)
  - facility criticality field (numeric, any scale) OR a fixed default
  - facility name field (optional, used in the log)
  - optional facility-class field (used for grouping in the log)

Outputs:
  - Per-facility: hazard_score (sampled at the centroid), criticality,
    combined_score, exposure_class.
  - Log: top-N facilities and class-by-class breakdown.

Combined score:
    combined = (hazard / 100) × criticality_normalised × 100
where criticality_normalised maps the user's raw criticality field to a
0-100 range using min/max within the layer.
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
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsSpatialIndex,
    QgsWkbTypes,
)


def _exposure_class(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Moderate"
    return "Low"


def _safe_float(value, default=None):
    try:
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


class CriticalInfrastructureExposureAlgorithm(QgsProcessingAlgorithm):
    HAZARD = "HAZARD"
    HAZARD_FIELD = "HAZARD_FIELD"
    FACILITIES = "FACILITIES"
    CRITICALITY_FIELD = "CRITICALITY_FIELD"
    CRITICALITY_DEFAULT = "CRITICALITY_DEFAULT"
    NAME_FIELD = "NAME_FIELD"
    CLASS_FIELD = "CLASS_FIELD"
    OUTPUT = "OUTPUT"

    OUT_HAZARD = "ci_hazard"
    OUT_CRIT = "ci_criticality"
    OUT_COMBINED = "ci_combined"
    OUT_CLASS = "ci_exposure_class"

    def tr(self, string):
        return string

    def createInstance(self):
        return CriticalInfrastructureExposureAlgorithm()

    def name(self):
        return "critical_infrastructure_exposure"

    def displayName(self):
        return self.tr("Critical Infrastructure Exposure")

    def group(self):
        return self.tr("8 - Synthesis")

    def groupId(self):
        return "planx_urban_resilience_synthesis"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Critical Infrastructure Exposure</h3>
            <p>Crosses a hazard score layer with a critical-facility layer
            (schools, hospitals, fire stations, water/power assets, etc.)
            and produces an exposure score combining BOTH hazard intensity
            AND facility criticality. Useful when planners need a
            shortlist of facilities to harden first.</p>
            <p><code>combined = (hazard / 100) × (criticality_norm) × 100</code>
            where <code>criticality_norm</code> linearly maps the user's
            raw criticality field to 0-100 using its own min and max.</p>
            <p>If no criticality field is given, every facility uses the
            default criticality so the output is essentially the hazard
            score sampled at each facility.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.HAZARD, self.tr("Hazard score layer (polygons)"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.HAZARD_FIELD, self.tr("Hazard score field (0-100)"),
            parentLayerParameterName=self.HAZARD,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.FACILITIES, self.tr("Critical-facility layer (points or polygons)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CRITICALITY_FIELD, self.tr("Criticality field on facilities (optional)"),
            parentLayerParameterName=self.FACILITIES,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.CRITICALITY_DEFAULT, self.tr("Default criticality if no field given"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.0, minValue=0.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD, self.tr("Facility name/label field (optional, for log)"),
            parentLayerParameterName=self.FACILITIES,
            type=QgsProcessingParameterField.Any, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CLASS_FIELD, self.tr("Facility class field (optional, e.g. school/hospital)"),
            parentLayerParameterName=self.FACILITIES,
            type=QgsProcessingParameterField.String, optional=True,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("Exposed facilities")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        hazard = self.parameterAsSource(parameters, self.HAZARD, context)
        facilities = self.parameterAsSource(parameters, self.FACILITIES, context)
        if hazard is None or facilities is None:
            raise QgsProcessingException("Hazard and facility layers are required.")
        hazard_field = self.parameterAsString(parameters, self.HAZARD_FIELD, context)
        crit_field = self.parameterAsString(parameters, self.CRITICALITY_FIELD, context)
        crit_default = self.parameterAsDouble(parameters, self.CRITICALITY_DEFAULT, context)
        name_field = self.parameterAsString(parameters, self.NAME_FIELD, context)
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context)

        # Cache hazard polygons in memory + build spatial index.
        feedback.pushInfo("Indexing hazard polygons…")
        haz_records: list = []  # (fid, geometry, score)
        haz_index = QgsSpatialIndex()
        for feat in hazard.getFeatures():
            if not feat.hasGeometry():
                continue
            score = _safe_float(feat.attribute(hazard_field), 0.0) or 0.0
            haz_records.append((feat.id(), QgsGeometry(feat.geometry()), score))
            haz_index.addFeature(feat)
        if not haz_records:
            raise QgsProcessingException("No hazard features with geometry.")

        # First pass: collect raw criticalities to compute normalisation range.
        raw_crits: list[float] = []
        for feat in facilities.getFeatures():
            if not feat.hasGeometry():
                continue
            c = _safe_float(feat.attribute(crit_field), crit_default) if crit_field else crit_default
            raw_crits.append(c)
        if not raw_crits:
            raise QgsProcessingException("No facility features with geometry.")
        crit_min = min(raw_crits)
        crit_max = max(raw_crits)
        crit_range = crit_max - crit_min if crit_max > crit_min else 1.0
        feedback.pushInfo(f"Criticality range across facilities: {crit_min:g} – {crit_max:g}")

        # Build output.
        out_fields = facilities.fields()
        for fname, ftype in (
            (self.OUT_HAZARD, QVariant.Double),
            (self.OUT_CRIT, QVariant.Double),
            (self.OUT_COMBINED, QVariant.Double),
            (self.OUT_CLASS, QVariant.String),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        # Output keeps source geometry type — even for polygon facilities we
        # preserve the original geometry.
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            facilities.wkbType(), facilities.sourceCrs(),
        )

        haz_geom_lookup = {fid: (geom, score) for fid, geom, score in haz_records}
        ranked: list = []
        class_totals: dict = {}

        for feat in facilities.getFeatures():
            if feedback.isCanceled():
                break
            if not feat.hasGeometry():
                continue
            geom = feat.geometry()
            centroid = geom.centroid().asPoint() if geom.type() != QgsWkbTypes.PointGeometry else geom.asPoint()
            point_geom = QgsGeometry.fromPointXY(centroid)

            # Find hazard polygon containing the facility centroid.
            hazard_score = 0.0
            candidate_ids = haz_index.intersects(point_geom.boundingBox())
            for hid in candidate_ids:
                hg, hs = haz_geom_lookup.get(hid, (None, 0.0))
                if hg is not None and hg.contains(point_geom):
                    hazard_score = hs
                    break

            raw_c = _safe_float(feat.attribute(crit_field), crit_default) if crit_field else crit_default
            c_norm = 100.0 * (raw_c - crit_min) / crit_range
            combined = (hazard_score / 100.0) * c_norm
            combined = max(0.0, min(100.0, combined))
            exposure_class = _exposure_class(combined)

            name = feat.attribute(name_field) if name_field else f"fid={feat.id()}"
            cls = feat.attribute(class_field) if class_field else "—"
            ranked.append((combined, str(name), str(cls), hazard_score, raw_c))
            class_totals.setdefault(str(cls), []).append(combined)

            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(geom)
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 4:
                new_attrs.append(None)
            new_attrs.extend([hazard_score, raw_c, combined, exposure_class])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        ranked.sort(key=lambda r: -r[0])
        feedback.pushInfo("")
        feedback.pushInfo("─── Top 10 most exposed facilities ───")
        for combined, name, cls, hs, rc in ranked[:10]:
            feedback.pushInfo(
                f"  {name:<40} cls={cls:<14} combined={combined:6.2f} "
                f"hazard={hs:6.2f} criticality={rc:g}"
            )
        if class_field and len(class_totals) > 1:
            feedback.pushInfo("")
            feedback.pushInfo("─── Mean combined score by facility class ───")
            for cls, scores in sorted(class_totals.items(),
                                      key=lambda kv: -(sum(kv[1]) / max(len(kv[1]), 1))):
                mean = sum(scores) / max(len(scores), 1)
                feedback.pushInfo(f"  {cls:<20} n={len(scores):<5} mean={mean:6.2f}")
        return {self.OUTPUT: dest_id}
