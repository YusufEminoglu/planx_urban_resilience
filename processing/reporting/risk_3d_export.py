# -*- coding: utf-8 -*-
"""3D Risk Volume Export.

Turns a 0-100 scored polygon layer into a GeoJSON file with an
`extrusion_height` attribute (= score × scale_factor in metres) and a
`color_hex` attribute (yellow→red ramp) so it drops straight into the
PlanX 3D City viewer (or Three.js / deck.gl / Cesium) without manual
styling. This is the most dramatic visualisation in the suite — a city
silhouette where the tallest blocks are the worst hot spots.

Inputs:
  - scored polygon layer + score field
  - scale factor (default: max extrusion 100 m for score = 100)
  - optional base height field (additive, useful when buildings already
    have a height attribute)
  - colour ramp choice: Yellow-Red, Blue-Red (diverging), or Greys

Outputs:
  - GeoJSON file on disk
  - Same layer also returned as a vector sink so it can be added to the
    project and inspected in the attribute table.

The GeoJSON is in EPSG:4326 to match common web-mapping expectations; the
plain in-QGIS layer keeps the source CRS.
"""
from __future__ import annotations

import json

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
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
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProject,
)


COLOR_RAMPS = ("Yellow-Red (sequential)", "Blue-Red (diverging)", "Greys")


def _yellow_red(t: float) -> str:
    """t in 0..1 → '#rrggbb' along a yellow-orange-red ramp."""
    t = max(0.0, min(1.0, t))
    # Anchor stops: pale-yellow #fef0d9, orange #fdbb84, red #b30000
    if t <= 0.5:
        s = t / 0.5
        r = 254 + (253 - 254) * s
        g = 240 + (187 - 240) * s
        b = 217 + (132 - 217) * s
    else:
        s = (t - 0.5) / 0.5
        r = 253 + (179 - 253) * s
        g = 187 + (0 - 187) * s
        b = 132 + (0 - 132) * s
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _blue_red(t: float) -> str:
    """Diverging blue → grey → red."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        s = t / 0.5
        r = 33 + (210 - 33) * s
        g = 102 + (210 - 102) * s
        b = 172 + (210 - 172) * s
    else:
        s = (t - 0.5) / 0.5
        r = 210 + (179 - 210) * s
        g = 210 + (0 - 210) * s
        b = 210 + (0 - 210) * s
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _greys(t: float) -> str:
    t = max(0.0, min(1.0, t))
    v = int(230 - 230 * t)
    return f"#{v:02x}{v:02x}{v:02x}"


COLOR_FUNCS = (_yellow_red, _blue_red, _greys)


def _polygon_to_coords(geom, transform):
    """Convert a (possibly multipart) polygon QgsGeometry to GeoJSON coords."""
    if geom.isMultipart():
        polys = geom.asMultiPolygon()
        out = []
        for poly in polys:
            rings = []
            for ring in poly:
                rings.append([_xform_pt(p, transform) for p in ring])
            out.append(rings)
        return ("MultiPolygon", out)
    poly = geom.asPolygon()
    rings = []
    for ring in poly:
        rings.append([_xform_pt(p, transform) for p in ring])
    return ("Polygon", rings)


def _xform_pt(point, transform):
    if transform is not None:
        p = transform.transform(point)
        return [round(p.x(), 7), round(p.y(), 7)]
    return [round(point.x(), 7), round(point.y(), 7)]


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class Risk3DVolumeExportAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_risk_3d_volume_export.png"
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    MAX_HEIGHT = "MAX_HEIGHT"
    BASE_HEIGHT_FIELD = "BASE_HEIGHT_FIELD"
    COLOR_RAMP = "COLOR_RAMP"
    OUTPUT_GEOJSON = "OUTPUT_GEOJSON"
    OUTPUT = "OUTPUT"

    OUT_HEIGHT = "extrusion_height"
    OUT_COLOR = "color_hex"
    OUT_SCORE_NORM = "score_norm"

    def tr(self, string):
        return string

    def createInstance(self):
        return Risk3DVolumeExportAlgorithm()

    def name(self):
        return "risk_3d_volume_export"

    def displayName(self):
        return self.tr("3D Risk Volume Export (GeoJSON for PlanX 3D City)")

    def shortHelpString(self):
        return self.tr(
            "<h3>3D Risk Volume Export</h3> <p>Turns a 0-100 scored polygon layer into a GeoJSON file "
            "with <code>extrusion_height</code> and <code>color_hex</code> attributes so it drops "
            "straight into the PlanX 3D City viewer (or Three.js / deck.gl / Cesium) without manual "
            "styling - exploiting the human visual system's sensitivity to height variation (Ware, "
            "2012) so equal risk differences read as equal vertical displacement. Colour is "
            "deliberately redundant with height (two channels for one variable), improving "
            "interpretability for viewers who may not perceive height accurately due to perspective, "
            "occlusion, or colour vision deficiency.</p> <p>The tallest, most saturated blocks in the "
            "resulting 3D view are the worst hot spots — a single picture worth a thousand choropleth "
            "slides.</p> <p>GeoJSON is written in EPSG:4326 for web-map compatibility; the in-QGIS "
            "vector output keeps the source CRS. MAX_HEIGHT is a display-tuning parameter with no "
            "inherent physical meaning - unless BASE_HEIGHT_FIELD carries real building heights and "
            "is used additively, extrusion is purely visual, not an actual 3D building model.</p> "
            "<p>Using the results: 3D perspective introduces occlusion (tall extrusions can hide "
            "shorter ones) and makes precise value comparison harder than a flat map - keep this "
            "alongside the 2D choropleth in a report, not as a replacement for it.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored polygon layer"),
            [QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SCORE_FIELD, self.tr("Score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_HEIGHT, self.tr("Maximum extrusion height (metres for score=100)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=100.0, minValue=0.1, maxValue=10000.0,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.BASE_HEIGHT_FIELD, self.tr("Optional base height field (metres, added to extrusion)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric, optional=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.COLOR_RAMP, self.tr("Colour ramp"),
            options=list(COLOR_RAMPS), defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_GEOJSON, self.tr("Output GeoJSON"),
            fileFilter="GeoJSON (*.geojson *.json)",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr("In-QGIS preview layer (with extrusion attributes)")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        max_height = self.parameterAsDouble(parameters, self.MAX_HEIGHT, context)
        base_field = self.parameterAsString(parameters, self.BASE_HEIGHT_FIELD, context) or ""
        ramp_idx = self.parameterAsEnum(parameters, self.COLOR_RAMP, context)
        out_geojson = self.parameterAsFileOutput(parameters, self.OUTPUT_GEOJSON, context)
        color_fn = COLOR_FUNCS[ramp_idx]

        # Build CRS transform once.
        src_crs = source.sourceCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        if src_crs.isValid() and src_crs != wgs84:
            transform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
        else:
            transform = None

        # Output field schema.
        out_fields = source.fields()
        for fname, ftype in (
            (self.OUT_HEIGHT, QVariant.Double),
            (self.OUT_COLOR, QVariant.String),
            (self.OUT_SCORE_NORM, QVariant.Double),
        ):
            if out_fields.indexOf(fname) < 0:
                out_fields.append(QgsField(fname, ftype))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, out_fields,
            source.wkbType(), source.sourceCrs(),
        )

        # Collect GeoJSON features as we go.
        features_json: list = []
        total = max(source.featureCount(), 1)
        for idx, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            if not feat.hasGeometry():
                continue
            try:
                score = float(feat.attribute(score_field))
            except (TypeError, ValueError):
                score = 0.0
            score = max(0.0, min(100.0, score))
            norm = score / 100.0
            extrusion = max_height * norm
            try:
                base_h = float(feat.attribute(base_field)) if base_field else 0.0
            except (TypeError, ValueError):
                base_h = 0.0
            total_height = base_h + extrusion
            color = color_fn(norm)

            # In-QGIS preview row.
            new_feat = QgsFeature(out_fields)
            new_feat.setGeometry(feat.geometry())
            new_attrs = list(feat.attributes())
            while len(new_attrs) < out_fields.size() - 3:
                new_attrs.append(None)
            new_attrs.extend([total_height, color, norm])
            new_feat.setAttributes(new_attrs)
            sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

            # GeoJSON row.
            geom_type, coords = _polygon_to_coords(feat.geometry(), transform)
            props = {name: feat.attribute(name) for name in feat.fields().names()}
            props["extrusion_height"] = round(total_height, 3)
            props["color_hex"] = color
            props["score_norm"] = round(norm, 4)
            features_json.append({
                "type": "Feature",
                "geometry": {"type": geom_type, "coordinates": coords},
                "properties": props,
            })

            if idx % 25 == 0:
                feedback.setProgress(int(100 * (idx + 1) / total))

        # Serialise.
        geojson = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
            "features": features_json,
            "metadata": {
                "generator": "PlanX Urban Resilience 1.22.0",
                "source_field": score_field,
                "max_height_m": max_height,
                "color_ramp": COLOR_RAMPS[ramp_idx],
                "feature_count": len(features_json),
            },
        }
        with open(out_geojson, "w", encoding="utf-8", newline="\n") as fp:
            json.dump(geojson, fp, ensure_ascii=False, default=lambda x: None)
        feedback.pushInfo(f"Wrote GeoJSON: {out_geojson}")
        feedback.pushInfo("Open in PlanX 3D City Viewer or any Three.js / Cesium scene.")
        return {self.OUTPUT_GEOJSON: out_geojson, self.OUTPUT: dest_id}
