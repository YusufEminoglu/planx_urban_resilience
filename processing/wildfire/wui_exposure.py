# -*- coding: utf-8 -*-
from __future__ import annotations

import math

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .._helpers import clamp, composite_risk_class
from .._mixins import GROUP_DROUGHT, GroupMixin, HelpUrlMixin


def _features(source):
    if source is None:
        return []
    return [f for f in source.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]


def _union(features):
    geoms = [f.geometry().makeValid() for f in features]
    if not geoms:
        return None
    u = QgsGeometry.unaryUnion(geoms)
    return u.makeValid() if u and not u.isEmpty() else None


def _area_share(cell_geom, target_union):
    if target_union is None or target_union.isEmpty() or cell_geom.area() <= 0:
        return 0.0
    inter = cell_geom.intersection(target_union)
    if inter is None or inter.isEmpty():
        return 0.0
    return clamp(inter.area() / cell_geom.area(), 0.0, 1.0)


def _sample_dem_elevation(provider, pt_xy, transform=None):
    if provider is None:
        return None
    sample_pt = transform.transform(pt_xy) if transform is not None else pt_xy
    val, ok = provider.sample(sample_pt, 1)
    if not ok or val is None or math.isnan(float(val)):
        return None
    return float(val)


def _sample_slope_pct(provider, center_xy, step, transform=None):
    if provider is None or step <= 0:
        return None
    e_w = _sample_dem_elevation(provider, QgsPointXY(center_xy.x() - step, center_xy.y()), transform)
    e_e = _sample_dem_elevation(provider, QgsPointXY(center_xy.x() + step, center_xy.y()), transform)
    e_s = _sample_dem_elevation(provider, QgsPointXY(center_xy.x(), center_xy.y() - step), transform)
    e_n = _sample_dem_elevation(provider, QgsPointXY(center_xy.x(), center_xy.y() + step), transform)
    if None in (e_w, e_e, e_s, e_n):
        return None
    dz_dx = (e_e - e_w) / (2.0 * step)
    dz_dy = (e_n - e_s) / (2.0 * step)
    return math.hypot(dz_dx, dz_dy) * 100.0


class WildfireWuiExposureAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_DROUGHT
    ICON = "tool_wui_exposure_screening.png"

    STUDY_AREA = "STUDY_AREA"
    VEGETATION = "VEGETATION"
    BUILDINGS = "BUILDINGS"
    ROADS = "ROADS"
    DEM = "DEM"
    CELL_SIZE = "CELL_SIZE"
    WUI_BUFFER = "WUI_BUFFER"
    MAX_EGRESS_DIST = "MAX_EGRESS_DIST"
    WEIGHT_FUEL = "WEIGHT_FUEL"
    WEIGHT_INTERFACE = "WEIGHT_INTERFACE"
    WEIGHT_SLOPE = "WEIGHT_SLOPE"
    WEIGHT_EGRESS = "WEIGHT_EGRESS"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_PRIORITY = "OUTPUT_PRIORITY"
    OUTPUT_EXPOSED = "OUTPUT_EXPOSED"

    def tr(self, string):
        return string

    def createInstance(self):
        return WildfireWuiExposureAlgorithm()

    def name(self):
        return "wui_exposure_screening"

    def displayName(self):
        return self.tr("Wildfire / WUI Exposure Screening")

    def shortHelpString(self):
        return self.tr(
            "<h3>Wildfire / Wildland-Urban Interface (WUI) Exposure Screening</h3> "
            "<p>Screens a study area for Wildland-Urban Interface (WUI) wildfire exposure by "
            "combining wildland vegetation fuel proximity and cover (Radeloff et al., 2005), "
            "structure-to-vegetation interface density within the radiant/ember ignition zone "
            "(Cohen, 2000), topographic slope rate-of-spread amplification (Rothermel, 1972), "
            "and emergency road egress deficit (Cova, 2005).</p> "
            "<p>For each grid cell, the 0-100 <code>wui_score</code> is the weighted combination of "
            "four standardized sub-scores: (1) <code>fuel_score</code> (vegetated cover share in the "
            "cell plus inverse distance to the wildland fuel boundary within <code>WUI_BUFFER</code>), "
            "(2) <code>inter_score</code> (density of buildings intersecting the WUI fuel buffer), "
            "(3) <code>slope_score</code> (finite-difference slope percentage from the optional DEM, "
            "scaled linearly across 0-35%% slope; defaults to neutral 50.0 with <code>slope_pct = -1.0</code> "
            "when no DEM is supplied), and (4) <code>egress_score</code> (distance to the nearest "
            "evacuation road relative to <code>MAX_EGRESS_DIST</code>).</p> "
            "<p>How to read the results: cells with <code>wui_score &gt;= 60</code> are exported to "
            "the priority WUI intervention layer, and structures inside the radiant/ember buffer of "
            "cells scoring <code>&gt;= 55</code> are written as point features to the exposed interface "
            "structures layer. This is a planning-scale exposure screening model and does not simulate "
            "wind-driven firebrand transport or fuel moisture physics.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.STUDY_AREA,
                self.tr("Study area boundary (polygon)"),
                [QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.VEGETATION,
                self.tr("Wildland / forest / fuel vegetation (polygon)"),
                [QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BUILDINGS,
                self.tr("Buildings / structures (optional polygon or point)"),
                [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ROADS,
                self.tr("Road / egress network (optional line)"),
                [QgsProcessing.TypeVectorLine],
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.DEM,
                self.tr("Elevation DEM for slope amplification (optional raster)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CELL_SIZE,
                self.tr("Analysis grid cell size (map units)"),
                QgsProcessingParameterNumber.Double,
                defaultValue=100.0,
                minValue=10.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WUI_BUFFER,
                self.tr("WUI structure-vegetation interface distance (map units)"),
                QgsProcessingParameterNumber.Double,
                defaultValue=300.0,
                minValue=10.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_EGRESS_DIST,
                self.tr("Maximum emergency road egress distance (map units)"),
                QgsProcessingParameterNumber.Double,
                defaultValue=400.0,
                minValue=10.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WEIGHT_FUEL,
                self.tr("Wildland fuel proximity and cover weight"),
                QgsProcessingParameterNumber.Double,
                defaultValue=0.35,
                minValue=0.0,
                maxValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WEIGHT_INTERFACE,
                self.tr("Structure-fuel interface density weight"),
                QgsProcessingParameterNumber.Double,
                defaultValue=0.30,
                minValue=0.0,
                maxValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WEIGHT_SLOPE,
                self.tr("Topographic slope amplification weight"),
                QgsProcessingParameterNumber.Double,
                defaultValue=0.20,
                minValue=0.0,
                maxValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WEIGHT_EGRESS,
                self.tr("Road egress deficit weight"),
                QgsProcessingParameterNumber.Double,
                defaultValue=0.15,
                minValue=0.0,
                maxValue=1.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_GRID,
                self.tr("WUI exposure screening grid"),
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_PRIORITY,
                self.tr("Priority WUI intervention zones"),
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_EXPOSED,
                self.tr("Exposed interface structures"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        study_source = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        veg_source = self.parameterAsSource(parameters, self.VEGETATION, context)
        bldg_source = self.parameterAsSource(parameters, self.BUILDINGS, context)
        road_source = self.parameterAsSource(parameters, self.ROADS, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)

        if study_source is None:
            raise QgsProcessingException("Study area boundary is required.")
        if veg_source is None:
            raise QgsProcessingException("Wildland / fuel vegetation layer is required.")

        cell_size = max(10.0, self.parameterAsDouble(parameters, self.CELL_SIZE, context))
        wui_buffer = max(10.0, self.parameterAsDouble(parameters, self.WUI_BUFFER, context))
        max_egress = max(10.0, self.parameterAsDouble(parameters, self.MAX_EGRESS_DIST, context))

        w_fuel = self.parameterAsDouble(parameters, self.WEIGHT_FUEL, context)
        w_inter = self.parameterAsDouble(parameters, self.WEIGHT_INTERFACE, context)
        w_slope = self.parameterAsDouble(parameters, self.WEIGHT_SLOPE, context)
        w_egress = self.parameterAsDouble(parameters, self.WEIGHT_EGRESS, context)
        weight_sum = max(w_fuel + w_inter + w_slope + w_egress, 1e-6)

        study_feats = _features(study_source)
        study_union = _union(study_feats)
        if study_union is None or study_union.isEmpty():
            raise QgsProcessingException("Study area contains no valid polygon geometry.")

        veg_feats = _features(veg_source)
        veg_union = _union(veg_feats)
        wui_zone = veg_union.buffer(wui_buffer, 5) if (veg_union and not veg_union.isEmpty()) else None

        bldg_feats = _features(bldg_source)
        bldg_index = QgsSpatialIndex()
        bldg_by_id = {}
        for bf in bldg_feats:
            bldg_index.addFeature(bf)
            bldg_by_id[bf.id()] = bf

        road_feats = _features(road_source)
        road_union = _union(road_feats)

        dem_provider = dem_layer.dataProvider() if (dem_layer and dem_layer.isValid()) else None
        dem_transform = None
        if dem_provider is not None and dem_layer.crs() != study_source.sourceCrs():
            dem_transform = QgsCoordinateTransform(
                study_source.sourceCrs(),
                dem_layer.crs(),
                context.transformContext(),
            )

        grid_fields = QgsFields()
        grid_fields.append(QgsField("cell_id", QVariant.Int))
        grid_fields.append(QgsField("fuel_share", QVariant.Double))
        grid_fields.append(QgsField("fuel_dist_m", QVariant.Double))
        grid_fields.append(QgsField("bldg_count", QVariant.Int))
        grid_fields.append(QgsField("wui_bldg_n", QVariant.Int))
        grid_fields.append(QgsField("slope_pct", QVariant.Double))
        grid_fields.append(QgsField("egress_m", QVariant.Double))
        grid_fields.append(QgsField("fuel_score", QVariant.Double))
        grid_fields.append(QgsField("inter_score", QVariant.Double))
        grid_fields.append(QgsField("slope_score", QVariant.Double))
        grid_fields.append(QgsField("egress_score", QVariant.Double))
        grid_fields.append(QgsField("wui_score", QVariant.Double))
        grid_fields.append(QgsField("risk_class", QVariant.String))

        exposed_fields = QgsFields()
        exposed_fields.append(QgsField("struct_id", QVariant.Int))
        exposed_fields.append(QgsField("cell_id", QVariant.Int))
        exposed_fields.append(QgsField("fuel_dist_m", QVariant.Double))
        exposed_fields.append(QgsField("wui_score", QVariant.Double))
        exposed_fields.append(QgsField("risk_class", QVariant.String))

        crs = study_source.sourceCrs()
        grid_sink, grid_id = self.parameterAsSink(
            parameters, self.OUTPUT_GRID, context, grid_fields, QgsWkbTypes.Polygon, crs
        )
        prio_sink, prio_id = self.parameterAsSink(
            parameters, self.OUTPUT_PRIORITY, context, grid_fields, QgsWkbTypes.Polygon, crs
        )
        exp_sink, exp_id = self.parameterAsSink(
            parameters, self.OUTPUT_EXPOSED, context, exposed_fields, QgsWkbTypes.Point, crs
        )

        bbox = study_union.boundingBox()
        cols = max(1, int(math.ceil(bbox.width() / cell_size)))
        rows = max(1, int(math.ceil(bbox.height() / cell_size)))
        total_cells = cols * rows

        cell_id = 0
        exposed_struct_ids = set()
        for r in range(rows):
            if feedback.isCanceled():
                break
            y_min = bbox.yMinimum() + r * cell_size
            y_max = min(bbox.yMaximum(), y_min + cell_size)
            for c in range(cols):
                rect = QgsRectangle(
                    bbox.xMinimum() + c * cell_size,
                    y_min,
                    min(bbox.xMaximum(), bbox.xMinimum() + (c + 1) * cell_size),
                    y_max,
                )
                raw_cell = QgsGeometry.fromRect(rect)
                if not raw_cell.intersects(study_union):
                    continue
                cell_geom = raw_cell.intersection(study_union)
                if cell_geom is None or cell_geom.isEmpty() or cell_geom.area() <= 0:
                    continue

                cell_id += 1
                centroid_geom = cell_geom.centroid()
                center_xy = centroid_geom.asPoint()

                # 1. Fuel proximity & vegetation share
                fuel_share = _area_share(cell_geom, veg_union)
                if veg_union is not None and not veg_union.isEmpty():
                    fuel_dist = float(cell_geom.distance(veg_union))
                    prox_score = clamp((1.0 - fuel_dist / max(wui_buffer * 2.0, 1.0)) * 100.0, 0.0, 100.0)
                else:
                    fuel_dist = -1.0
                    prox_score = 0.0
                fuel_score = clamp(0.55 * prox_score + 0.45 * (fuel_share * 100.0), 0.0, 100.0)

                # 2. Structure-to-vegetation interface density
                bldg_count = 0
                wui_bldg_n = 0
                cell_bldg_feats = []
                if bldg_feats:
                    for fid in bldg_index.intersects(cell_geom.boundingBox()):
                        bf = bldg_by_id.get(fid)
                        if bf and bf.geometry().intersects(cell_geom):
                            bldg_count += 1
                            cell_bldg_feats.append(bf)
                            if wui_zone is not None and bf.geometry().intersects(wui_zone):
                                wui_bldg_n += 1
                    # Normalize interface building count (5+ interface structures per cell = 100)
                    inter_score = clamp(
                        (wui_bldg_n / 5.0) * 75.0 + (bldg_count / 8.0) * 25.0,
                        0.0,
                        100.0,
                    )
                else:
                    # When no building layer is supplied, estimate potential WUI interface from fuel edge
                    in_wui_belt = (
                        1.0
                        if (wui_zone is not None and cell_geom.intersects(wui_zone) and fuel_share < 0.85)
                        else 0.35
                    )
                    inter_score = clamp(in_wui_belt * prox_score, 0.0, 100.0)

                # 3. Topographic slope amplification (Rothermel 1972)
                slope_val = _sample_slope_pct(dem_provider, center_xy, cell_size * 0.5, dem_transform)
                if slope_val is None:
                    slope_pct = -1.0
                    slope_score = 50.0
                else:
                    slope_pct = round(slope_val, 2)
                    slope_score = clamp((slope_val / 35.0) * 100.0, 0.0, 100.0)

                # 4. Emergency road egress deficit (Cova 2005)
                if road_union is not None and not road_union.isEmpty():
                    egress_m = float(centroid_geom.distance(road_union))
                    egress_score = clamp((egress_m / max_egress) * 100.0, 0.0, 100.0)
                else:
                    egress_m = -1.0
                    egress_score = 60.0

                wui_score = clamp(
                    (
                        w_fuel * fuel_score
                        + w_inter * inter_score
                        + w_slope * slope_score
                        + w_egress * egress_score
                    )
                    / weight_sum,
                    0.0,
                    100.0,
                )
                r_class = composite_risk_class(wui_score)

                attrs = [
                    cell_id,
                    round(fuel_share, 4),
                    round(fuel_dist, 2),
                    bldg_count,
                    wui_bldg_n,
                    slope_pct,
                    round(egress_m, 2),
                    round(fuel_score, 2),
                    round(inter_score, 2),
                    round(slope_score, 2),
                    round(egress_score, 2),
                    round(wui_score, 2),
                    r_class,
                ]

                feat = QgsFeature(grid_fields)
                feat.setGeometry(cell_geom)
                feat.setAttributes(attrs)
                grid_sink.addFeature(feat, QgsFeatureSink.FastInsert)

                if wui_score >= 60.0:
                    pfeat = QgsFeature(grid_fields)
                    pfeat.setGeometry(cell_geom)
                    pfeat.setAttributes(attrs)
                    prio_sink.addFeature(pfeat, QgsFeatureSink.FastInsert)

                if wui_score >= 45.0 and cell_bldg_feats:
                    for bf in cell_bldg_feats:
                        if bf.id() in exposed_struct_ids:
                            continue
                        b_geom = bf.geometry()
                        b_dist = float(b_geom.distance(veg_union)) if (veg_union and not veg_union.isEmpty()) else -1.0
                        if b_dist < 0 or b_dist <= wui_buffer * 1.5:
                            exposed_struct_ids.add(bf.id())
                            efeat = QgsFeature(exposed_fields)
                            efeat.setGeometry(b_geom.centroid())
                            efeat.setAttributes([
                                int(bf.id()),
                                cell_id,
                                round(b_dist, 2),
                                round(wui_score, 2),
                                r_class,
                            ])
                            exp_sink.addFeature(efeat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(((r + 1) / max(rows, 1)) * 100))

        return {
            self.OUTPUT_GRID: grid_id,
            self.OUTPUT_PRIORITY: prio_id,
            self.OUTPUT_EXPOSED: exp_id,
        }
