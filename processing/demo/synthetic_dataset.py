# -*- coding: utf-8 -*-
from __future__ import annotations

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
)


def _polygon(x1, y1, x2, y2):
    return QgsGeometry.fromPolygonXY(
        [[
            QgsPointXY(x1, y1),
            QgsPointXY(x2, y1),
            QgsPointXY(x2, y2),
            QgsPointXY(x1, y2),
            QgsPointXY(x1, y1),
        ]]
    )


def _line(points):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in points])


def _point(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


def _fields(definitions):
    fields = QgsFields()
    for name, field_type in definitions:
        fields.append(QgsField(name, field_type))
    return fields


def _add(sink, fields, geometry, attrs):
    feature = QgsFeature(fields)
    feature.setGeometry(geometry)
    feature.setAttributes(attrs)
    sink.addFeature(feature, QgsFeatureSink.FastInsert)


class SyntheticResilienceDatasetAlgorithm(QgsProcessingAlgorithm):
    SCALE = "SCALE"
    STUDY_AREA = "STUDY_AREA"
    BUILDINGS = "BUILDINGS"
    ROADS = "ROADS"
    IMPERVIOUS = "IMPERVIOUS"
    GREEN = "GREEN"
    WATER = "WATER"
    SHELTERS = "SHELTERS"
    SOCIAL_UNITS = "SOCIAL_UNITS"
    SENSITIVE = "SENSITIVE"

    def tr(self, string):
        return string

    def createInstance(self):
        return SyntheticResilienceDatasetAlgorithm()

    def name(self):
        return "synthetic_resilience_demo_dataset"

    def displayName(self):
        return self.tr("Synthetic Resilience Demo Dataset")

    def group(self):
        return self.tr("0 - Demo and QA")

    def groupId(self):
        return "planx_urban_resilience_demo"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Synthetic Resilience Demo Dataset</h3>
            <p>Creates a small metric demo dataset for testing the PlanX Urban Resilience modules inside QGIS. The outputs include study area, buildings, roads, impervious surfaces, green infrastructure, water, shelters, social units, and sensitive receptors.</p>
            <p>The generated data is artificial and only intended for smoke testing, teaching, and workflow demonstrations.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterNumber(self.SCALE, self.tr("Scenario scale multiplier"), QgsProcessingParameterNumber.Double, defaultValue=1.0, minValue=0.25, maxValue=5.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.STUDY_AREA, self.tr("Synthetic study area")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.BUILDINGS, self.tr("Synthetic buildings")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.ROADS, self.tr("Synthetic roads")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.IMPERVIOUS, self.tr("Synthetic impervious surfaces")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.GREEN, self.tr("Synthetic green infrastructure")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.WATER, self.tr("Synthetic water / blue infrastructure")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.SHELTERS, self.tr("Synthetic shelters / assembly areas")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.SOCIAL_UNITS, self.tr("Synthetic social units")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.SENSITIVE, self.tr("Synthetic sensitive receptors")))

    def processAlgorithm(self, parameters, context, feedback):
        scale = self.parameterAsDouble(parameters, self.SCALE, context)
        crs = QgsCoordinateReferenceSystem("EPSG:3857")
        s = 1000.0 * scale

        area_fields = _fields([("name", QVariant.String), ("scenario", QVariant.String)])
        building_fields = _fields([
            ("name", QVariant.String),
            ("katadedi", QVariant.Int),
            ("uipfonksiyon", QVariant.String),
            ("year", QVariant.Int),
        ])
        road_fields = _fields([("name", QVariant.String), ("class", QVariant.String)])
        imperv_fields = _fields([("name", QVariant.String), ("type", QVariant.String)])
        green_fields = _fields([("name", QVariant.String), ("type", QVariant.String)])
        water_fields = _fields([("name", QVariant.String), ("type", QVariant.String)])
        shelter_fields = _fields([("name", QVariant.String), ("capacity", QVariant.Int)])
        social_fields = _fields([
            ("name", QVariant.String),
            ("population", QVariant.Int),
            ("elderly", QVariant.Int),
            ("children", QVariant.Int),
            ("disability", QVariant.Int),
            ("low_income", QVariant.Int),
        ])
        sensitive_fields = _fields([("name", QVariant.String), ("type", QVariant.String)])

        study_sink, study_id = self.parameterAsSink(parameters, self.STUDY_AREA, context, area_fields, QgsWkbTypes.Polygon, crs)
        buildings_sink, buildings_id = self.parameterAsSink(parameters, self.BUILDINGS, context, building_fields, QgsWkbTypes.Polygon, crs)
        roads_sink, roads_id = self.parameterAsSink(parameters, self.ROADS, context, road_fields, QgsWkbTypes.LineString, crs)
        imperv_sink, imperv_id = self.parameterAsSink(parameters, self.IMPERVIOUS, context, imperv_fields, QgsWkbTypes.Polygon, crs)
        green_sink, green_id = self.parameterAsSink(parameters, self.GREEN, context, green_fields, QgsWkbTypes.Polygon, crs)
        water_sink, water_id = self.parameterAsSink(parameters, self.WATER, context, water_fields, QgsWkbTypes.LineString, crs)
        shelters_sink, shelters_id = self.parameterAsSink(parameters, self.SHELTERS, context, shelter_fields, QgsWkbTypes.Point, crs)
        social_sink, social_id = self.parameterAsSink(parameters, self.SOCIAL_UNITS, context, social_fields, QgsWkbTypes.Polygon, crs)
        sensitive_sink, sensitive_id = self.parameterAsSink(parameters, self.SENSITIVE, context, sensitive_fields, QgsWkbTypes.Point, crs)

        _add(study_sink, area_fields, _polygon(0, 0, 2 * s, 1.4 * s), ["PlanX synthetic district", "balanced"])

        social_specs = [
            ("NW", 0, 0.7 * s, s, 1.4 * s, 850, 90, 140, 35, 190),
            ("NE", s, 0.7 * s, 2 * s, 1.4 * s, 620, 55, 80, 18, 90),
            ("SW", 0, 0, s, 0.7 * s, 1100, 150, 220, 55, 360),
            ("SE", s, 0, 2 * s, 0.7 * s, 760, 70, 120, 22, 130),
        ]
        for spec in social_specs:
            name, x1, y1, x2, y2, pop, elderly, children, disability, low_income = spec
            _add(social_sink, social_fields, _polygon(x1, y1, x2, y2), [name, pop, elderly, children, disability, low_income])

        for idx, x in enumerate((0.35 * s, 0.75 * s, 1.15 * s, 1.55 * s)):
            _add(buildings_sink, building_fields, _polygon(x, 0.18 * s, x + 0.16 * s, 0.34 * s), [f"Residential {idx + 1}", 4 + idx, "Residential", 1990 + idx * 8])
            _add(buildings_sink, building_fields, _polygon(x, 0.86 * s, x + 0.18 * s, 1.08 * s), [f"Mixed use {idx + 1}", 6 + idx, "Mixed Use", 1980 + idx * 6])
        _add(buildings_sink, building_fields, _polygon(0.18 * s, 0.45 * s, 0.38 * s, 0.62 * s), ["School block", 3, "Education", 2008])
        _add(buildings_sink, building_fields, _polygon(1.62 * s, 0.42 * s, 1.84 * s, 0.62 * s), ["Health block", 5, "Health", 2015])

        for name, pts, cls in (
            ("Main avenue", [(0, 0.42 * s), (2 * s, 0.42 * s)], "arterial"),
            ("North connector", [(0.25 * s, 0), (0.25 * s, 1.4 * s)], "collector"),
            ("Central connector", [(1.0 * s, 0), (1.0 * s, 1.4 * s)], "collector"),
            ("East connector", [(1.75 * s, 0), (1.75 * s, 1.4 * s)], "local"),
        ):
            _add(roads_sink, road_fields, _line(pts), [name, cls])

        _add(imperv_sink, imperv_fields, _polygon(0.0, 0.35 * s, 2 * s, 0.50 * s), ["Main hardscape corridor", "road_hardscape"])
        _add(imperv_sink, imperv_fields, _polygon(0.95 * s, 0.0, 1.10 * s, 1.4 * s), ["Central hardscape corridor", "road_hardscape"])

        _add(green_sink, green_fields, _polygon(0.42 * s, 0.55 * s, 0.78 * s, 0.86 * s), ["Neighborhood park", "park"])
        _add(green_sink, green_fields, _polygon(1.18 * s, 0.92 * s, 1.52 * s, 1.25 * s), ["Canopy patch", "urban_forest"])
        _add(green_sink, green_fields, _polygon(1.46 * s, 0.12 * s, 1.66 * s, 0.30 * s), ["Pocket park", "pocket_park"])

        _add(water_sink, water_fields, _line([(0.05 * s, 1.25 * s), (1.95 * s, 1.18 * s)]), ["Blue corridor", "stream"])

        for name, x, y, capacity in (
            ("Primary assembly area", 0.55 * s, 0.70 * s, 900),
            ("Eastern shelter", 1.55 * s, 1.05 * s, 600),
        ):
            _add(shelters_sink, shelter_fields, _point(x, y), [name, capacity])

        for name, kind, x, y in (
            ("School receptor", "school", 0.28 * s, 0.54 * s),
            ("Hospital receptor", "hospital", 1.73 * s, 0.54 * s),
            ("Care home receptor", "care", 0.82 * s, 1.02 * s),
            ("Dense housing receptor", "housing", 1.30 * s, 0.25 * s),
        ):
            _add(sensitive_sink, sensitive_fields, _point(x, y), [name, kind])

        feedback.pushInfo("Synthetic PlanX Urban Resilience demo dataset created.")
        return {
            self.STUDY_AREA: study_id,
            self.BUILDINGS: buildings_id,
            self.ROADS: roads_id,
            self.IMPERVIOUS: imperv_id,
            self.GREEN: green_id,
            self.WATER: water_id,
            self.SHELTERS: shelters_id,
            self.SOCIAL_UNITS: social_id,
            self.SENSITIVE: sensitive_id,
        }
