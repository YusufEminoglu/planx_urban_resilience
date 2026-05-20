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
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsRectangle,
    QgsWkbTypes,
)

from .._helpers import clamp, composite_risk_class


def _features(source):
    if source is None:
        return []
    return [feature for feature in source.getFeatures() if feature.hasGeometry()]


def _union(source):
    geometries = [feature.geometry().makeValid() for feature in _features(source)]
    if not geometries:
        return None
    return QgsGeometry.unaryUnion(geometries).makeValid()


def _sample(provider, point):
    value, ok = provider.sample(point, 1)
    if not ok or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class PluvialFloodSusceptibilityAlgorithm(QgsProcessingAlgorithm):
    DEM = "DEM"
    STUDY_AREA = "STUDY_AREA"
    BUILDINGS = "BUILDINGS"
    ROADS = "ROADS"
    DRAINAGE = "DRAINAGE"
    CELL_SIZE = "CELL_SIZE"
    NEIGHBORHOOD = "NEIGHBORHOOD"
    ELEVATION_WEIGHT = "ELEVATION_WEIGHT"
    SLOPE_WEIGHT = "SLOPE_WEIGHT"
    DRAINAGE_WEIGHT = "DRAINAGE_WEIGHT"
    EXPOSURE_THRESHOLD = "EXPOSURE_THRESHOLD"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_BUILDINGS = "OUTPUT_BUILDINGS"
    OUTPUT_ROADS = "OUTPUT_ROADS"

    def tr(self, string):
        return string

    def createInstance(self):
        return PluvialFloodSusceptibilityAlgorithm()

    def name(self):
        return "pluvial_flood_susceptibility"

    def displayName(self):
        return self.tr("Pluvial Flood Susceptibility (screening)")

    def group(self):
        return self.tr("3 - Flood: pluvial susceptibility")

    def groupId(self):
        return "planx_urban_resilience_flood"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Pluvial Flood Susceptibility</h3>
            <p>Offline-first screening model for identifying low-lying and drainage-sensitive urban areas from a DEM, study area, and optional exposed assets.</p>
            <p>This is not a hydrodynamic model. It is intended for early-stage planning, classroom analysis, and prioritization.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, self.tr("DEM raster")))
        self.addParameter(QgsProcessingParameterFeatureSource(self.STUDY_AREA, self.tr("Study area (polygon)"), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.BUILDINGS, self.tr("Buildings (optional)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.ROADS, self.tr("Roads (optional)"), [QgsProcessing.TypeVectorLine], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(self.DRAINAGE, self.tr("Drainage / stream / water network (optional)"), [QgsProcessing.TypeVectorLine, QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.CELL_SIZE, self.tr("Grid cell size (map units)"), QgsProcessingParameterNumber.Double, defaultValue=100.0, minValue=5.0))
        self.addParameter(QgsProcessingParameterNumber(self.NEIGHBORHOOD, self.tr("DEM neighborhood radius (map units)"), QgsProcessingParameterNumber.Double, defaultValue=150.0, minValue=5.0))
        self.addParameter(QgsProcessingParameterNumber(self.ELEVATION_WEIGHT, self.tr("Relative low-elevation weight"), QgsProcessingParameterNumber.Double, defaultValue=0.45, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.SLOPE_WEIGHT, self.tr("Flat / low-slope weight"), QgsProcessingParameterNumber.Double, defaultValue=0.30, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.DRAINAGE_WEIGHT, self.tr("Drainage proximity weight"), QgsProcessingParameterNumber.Double, defaultValue=0.25, minValue=0.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(self.EXPOSURE_THRESHOLD, self.tr("Exposure threshold score"), QgsProcessingParameterNumber.Double, defaultValue=55.0, minValue=0.0, maxValue=100.0))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_GRID, self.tr("Flood susceptibility grid")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_BUILDINGS, self.tr("Exposed buildings")))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_ROADS, self.tr("Exposed road segments")))

    def processAlgorithm(self, parameters, context, feedback):
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        study = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        buildings = self.parameterAsSource(parameters, self.BUILDINGS, context)
        roads = self.parameterAsSource(parameters, self.ROADS, context)
        drainage = self.parameterAsSource(parameters, self.DRAINAGE, context)
        cell_size = self.parameterAsDouble(parameters, self.CELL_SIZE, context)
        radius = self.parameterAsDouble(parameters, self.NEIGHBORHOOD, context)
        w_elev = self.parameterAsDouble(parameters, self.ELEVATION_WEIGHT, context)
        w_slope = self.parameterAsDouble(parameters, self.SLOPE_WEIGHT, context)
        w_drain = self.parameterAsDouble(parameters, self.DRAINAGE_WEIGHT, context)
        threshold = self.parameterAsDouble(parameters, self.EXPOSURE_THRESHOLD, context)
        weight_sum = max(w_elev + w_slope + w_drain, 0.0001)

        provider = dem.dataProvider()
        study_union = _union(study)
        drainage_union = _union(drainage)

        fields = QgsFields()
        for name in ("cell_id", "elev", "rel_low", "slope_proxy", "drain_dist", "flood_score", "risk_class"):
            field_type = QVariant.String if name == "risk_class" else QVariant.Double
            if name == "cell_id":
                field_type = QVariant.Int
            fields.append(QgsField(name, field_type))
        (grid_sink, grid_id) = self.parameterAsSink(parameters, self.OUTPUT_GRID, context, fields, QgsWkbTypes.Polygon, study.sourceCrs())

        asset_fields = QgsFields()
        asset_fields.append(QgsField("asset_type", QVariant.String))
        asset_fields.append(QgsField("flood_score", QVariant.Double))
        asset_fields.append(QgsField("risk_class", QVariant.String))
        (building_sink, building_id) = self.parameterAsSink(parameters, self.OUTPUT_BUILDINGS, context, asset_fields, QgsWkbTypes.Point, study.sourceCrs())
        (road_sink, road_id) = self.parameterAsSink(parameters, self.OUTPUT_ROADS, context, asset_fields, QgsWkbTypes.MultiLineString, study.sourceCrs())

        extent = study.sourceExtent()
        xs = []
        sample_step = max(cell_size * 2.0, radius)
        x = extent.xMinimum()
        while x <= extent.xMaximum():
            y = extent.yMinimum()
            while y <= extent.yMaximum():
                value = _sample(provider, QgsPointXY(x, y))
                if value is not None:
                    xs.append(value)
                y += sample_step
            x += sample_step
        min_elev = min(xs) if xs else 0.0
        max_elev = max(xs) if xs else min_elev + 1.0
        elev_range = max(max_elev - min_elev, 1.0)

        scored_cells = []
        cell_id = 0
        total_cols = max(1, int((extent.xMaximum() - extent.xMinimum()) / cell_size) + 1)
        total_rows = max(1, int((extent.yMaximum() - extent.yMinimum()) / cell_size) + 1)
        total = total_cols * total_rows
        x = extent.xMinimum()
        while x < extent.xMaximum():
            y = extent.yMinimum()
            while y < extent.yMaximum():
                if feedback.isCanceled():
                    break
                rect = QgsRectangle(x, y, min(x + cell_size, extent.xMaximum()), min(y + cell_size, extent.yMaximum()))
                cell_geom = QgsGeometry.fromRect(rect)
                if study_union is None or not cell_geom.intersects(study_union):
                    y += cell_size
                    cell_id += 1
                    continue
                clipped = cell_geom.intersection(study_union).makeValid()
                center = clipped.centroid().asPoint()
                elev = _sample(provider, QgsPointXY(center.x(), center.y()))
                if elev is None:
                    y += cell_size
                    cell_id += 1
                    continue
                neighbors = []
                for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                    value = _sample(provider, QgsPointXY(center.x() + dx, center.y() + dy))
                    if value is not None:
                        neighbors.append(value)
                local_relief = max(neighbors) - min(neighbors) if len(neighbors) > 1 else 0.0
                rel_low = clamp((1.0 - ((elev - min_elev) / elev_range)) * 100.0)
                slope_proxy = clamp(100.0 - (local_relief / max(radius, 1.0)) * 100.0)
                if drainage_union and not drainage_union.isEmpty():
                    drain_dist = clipped.centroid().distance(drainage_union)
                    drain_score = clamp(100.0 - (drain_dist / max(radius * 4.0, 1.0)) * 100.0)
                else:
                    drain_dist = -1.0
                    drain_score = 50.0
                flood_score = clamp((rel_low * w_elev + slope_proxy * w_slope + drain_score * w_drain) / weight_sum)
                risk = composite_risk_class(flood_score)
                attrs = [cell_id, elev, rel_low, slope_proxy, drain_dist, flood_score, risk]
                feat = QgsFeature(fields)
                feat.setGeometry(clipped)
                feat.setAttributes(attrs)
                grid_sink.addFeature(feat, QgsFeatureSink.FastInsert)
                scored_cells.append((clipped, flood_score, risk))
                feedback.setProgress(int(min(100, cell_id / total * 100)))
                y += cell_size
                cell_id += 1
            x += cell_size

        high_cells = [geom for geom, score, _risk in scored_cells if score >= threshold]
        high_union = QgsGeometry.unaryUnion(high_cells).makeValid() if high_cells else None
        if high_union and not high_union.isEmpty():
            for feature in _features(buildings):
                if feature.geometry().intersects(high_union):
                    point = feature.geometry().centroid()
                    out = QgsFeature(asset_fields)
                    out.setGeometry(point)
                    out.setAttributes(["building", threshold, composite_risk_class(threshold)])
                    building_sink.addFeature(out, QgsFeatureSink.FastInsert)
            for feature in _features(roads):
                inter = feature.geometry().intersection(high_union)
                if not inter.isEmpty():
                    out = QgsFeature(asset_fields)
                    out.setGeometry(inter)
                    out.setAttributes(["road", threshold, composite_risk_class(threshold)])
                    road_sink.addFeature(out, QgsFeatureSink.FastInsert)

        return {
            self.OUTPUT_GRID: grid_id,
            self.OUTPUT_BUILDINGS: building_id,
            self.OUTPUT_ROADS: road_id,
        }
