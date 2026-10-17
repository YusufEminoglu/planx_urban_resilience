# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import deque
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
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
)

from .._helpers import clamp, composite_risk_class
from .._mixins import GROUP_FLOOD, GroupMixin, HelpUrlMixin


SCENARIO_LEVELS_M = (0.5, 1.0, 2.0)


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


def _sample_dem(provider, pt_xy, transform=None):
    if provider is None:
        return None
    sample_pt = transform.transform(pt_xy) if transform is not None else pt_xy
    val, ok = provider.sample(sample_pt, 1)
    if not ok or val is None or math.isnan(float(val)):
        return None
    return float(val)


class CoastalSlrExposureAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_FLOOD
    ICON = "tool_coastal_slr_exposure.png"

    STUDY_AREA = "STUDY_AREA"
    DEM = "DEM"
    COASTLINE = "COASTLINE"
    BUILDINGS = "BUILDINGS"
    ROADS = "ROADS"
    SCENARIO_PRESET = "SCENARIO_PRESET"
    WATER_LEVEL_M = "WATER_LEVEL_M"
    MHHW_OFFSET_M = "MHHW_OFFSET_M"
    CONNECTIVITY_RULE = "CONNECTIVITY_RULE"
    CELL_SIZE = "CELL_SIZE"
    NEAR_SHORE_BUFFER_M = "NEAR_SHORE_BUFFER_M"
    OUTPUT_GRID = "OUTPUT_GRID"
    OUTPUT_PRIORITY = "OUTPUT_PRIORITY"
    OUTPUT_EXPOSED = "OUTPUT_EXPOSED"

    SCENARIO_OPTIONS = [
        "+0.5 m (IPCC AR6 Intermediate-Low 2100)",
        "+1.0 m (IPCC AR6 High 2100)",
        "+2.0 m (Extreme SLR + 100-yr Storm Surge)",
        "Custom water level",
    ]
    CONNECTIVITY_OPTIONS = [
        "8-connected (cardinal + diagonal)",
        "4-connected (cardinal only)",
    ]

    def tr(self, string):
        return string

    def createInstance(self):
        return CoastalSlrExposureAlgorithm()

    def name(self):
        return "coastal_slr_exposure"

    def displayName(self):
        return self.tr("Coastal / Sea-Level-Rise (SLR) Exposure Screening")

    def shortHelpString(self):
        return self.tr(
            "<h3>Coastal / Sea-Level-Rise (SLR) Exposure Screening</h3> "
            "<p>Evaluates coastal inundation and sea-level-rise (SLR) plus storm-surge exposure "
            "using a hydrologically connected bathtub flood-fill model (Poulter &amp; Halpin, 2008; "
            "Gesch, 2009; Nicholls &amp; Cazenave, 2010). Unlike a naive elevation threshold that "
            "falsely flags disconnected inland topographic pits below the target water level, this "
            "algorithm runs a breadth-first search (BFS) from coastline-adjacent submerged cells "
            "across either 8-connected or 4-connected grid neighbours so only hydrologically "
            "connected cells (<code>connected = 1</code>) receive full inundation scoring.</p> "
            "<p>For each grid cell, the 0-100 <code>slr_score</code> combines connected inundation "
            "depth (<code>inund_m</code>) or low freeboard margin (<code>freeboard_m</code> within "
            "2.0 m above the design water level), coastal proximity within "
            "<code>NEAR_SHORE_BUFFER_M</code>, and exposed building/road asset density. Isolated "
            "low-lying inland depressions below the design water level are tagged with "
            "<code>connected = 0</code> and <code>sink_depth &gt; 0</code> for diagnostic inspection.</p> "
            "<p>How to read the results: cells scoring <code>slr_score &gt;= 55</code> or "
            "hydrologically connected submerged cells (<code>connected = 1</code>) are written to "
            "the priority coastal zone output, and structures located inside impacted cells are "
            "exported as point features to the exposed coastal structures layer.</p>"
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
            QgsProcessingParameterRasterLayer(
                self.DEM,
                self.tr("Coastal elevation DEM (raster, metres)"),
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.COASTLINE,
                self.tr("Coastline / shoreline or marine water body (line or polygon)"),
                [QgsProcessing.TypeVectorLine, QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BUILDINGS,
                self.tr("Buildings / coastal structures (optional polygon or point)"),
                [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ROADS,
                self.tr("Road network (optional line)"),
                [QgsProcessing.TypeVectorLine],
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SCENARIO_PRESET,
                self.tr("Sea-level-rise + surge scenario preset"),
                options=self.SCENARIO_OPTIONS,
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.WATER_LEVEL_M,
                self.tr("Custom water level above datum (m, used when Custom selected)"),
                QgsProcessingParameterNumber.Double,
                defaultValue=1.0,
                minValue=0.0,
                maxValue=50.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MHHW_OFFSET_M,
                self.tr("Local tidal datum / MHHW offset (m)"),
                QgsProcessingParameterNumber.Double,
                defaultValue=0.0,
                minValue=-10.0,
                maxValue=25.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.CONNECTIVITY_RULE,
                self.tr("Hydrological connectivity rule (Poulter & Halpin, 2008)"),
                options=self.CONNECTIVITY_OPTIONS,
                defaultValue=0,
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
                self.NEAR_SHORE_BUFFER_M,
                self.tr("Coastal wave / surge proximity buffer (map units)"),
                QgsProcessingParameterNumber.Double,
                defaultValue=250.0,
                minValue=10.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_GRID,
                self.tr("Coastal SLR exposure grid"),
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_PRIORITY,
                self.tr("Hydrologically connected inundation priority zones"),
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_EXPOSED,
                self.tr("Exposed coastal structures"),
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        study_source = self.parameterAsSource(parameters, self.STUDY_AREA, context)
        dem_layer = self.parameterAsRasterLayer(parameters, self.DEM, context)
        coast_source = self.parameterAsSource(parameters, self.COASTLINE, context)
        bldg_source = self.parameterAsSource(parameters, self.BUILDINGS, context)
        road_source = self.parameterAsSource(parameters, self.ROADS, context)

        if study_source is None:
            raise QgsProcessingException("Study area boundary is required.")
        if dem_layer is None or not dem_layer.isValid():
            raise QgsProcessingException("A valid coastal elevation DEM raster is required.")
        if coast_source is None:
            raise QgsProcessingException("Coastline / shoreline or marine water body layer is required.")

        preset_idx = self.parameterAsEnum(parameters, self.SCENARIO_PRESET, context)
        custom_wl = self.parameterAsDouble(parameters, self.WATER_LEVEL_M, context)
        mhhw_offset = self.parameterAsDouble(parameters, self.MHHW_OFFSET_M, context)
        conn_rule = self.parameterAsEnum(parameters, self.CONNECTIVITY_RULE, context)
        cell_size = max(10.0, self.parameterAsDouble(parameters, self.CELL_SIZE, context))
        shore_buf = max(10.0, self.parameterAsDouble(parameters, self.NEAR_SHORE_BUFFER_M, context))

        base_wl = SCENARIO_LEVELS_M[preset_idx] if preset_idx in (0, 1, 2) else custom_wl
        total_wl = base_wl + mhhw_offset

        study_union = _union(_features(study_source))
        if study_union is None or study_union.isEmpty():
            raise QgsProcessingException("Study area contains no valid polygon geometry.")

        coast_union = _union(_features(coast_source))
        if coast_union is None or coast_union.isEmpty():
            raise QgsProcessingException("Coastline layer contains no valid geometry.")

        bldg_feats = _features(bldg_source)
        bldg_index = QgsSpatialIndex()
        bldg_by_id = {}
        for bf in bldg_feats:
            bldg_index.addFeature(bf)
            bldg_by_id[bf.id()] = bf

        road_union = _union(_features(road_source))

        dem_provider = dem_layer.dataProvider()
        dem_transform = None
        if dem_layer.crs() != study_source.sourceCrs():
            dem_transform = QgsCoordinateTransform(
                study_source.sourceCrs(),
                dem_layer.crs(),
                context.transformContext(),
            )

        bbox = study_union.boundingBox()
        cols = max(1, int(math.ceil(bbox.width() / cell_size)))
        rows = max(1, int(math.ceil(bbox.height() / cell_size)))

        # Step 1: Build grid cells and sample DEM elevation + coastline distance
        cells = {}
        cell_id = 0
        seed_tolerance = max(cell_size * 1.25, 25.0)
        for r in range(rows):
            if feedback.isCanceled():
                break
            y_min = bbox.yMinimum() + r * cell_size
            y_max = min(bbox.yMaximum(), y_min + cell_size)
            for c in range(cols):
                x_min = bbox.xMinimum() + c * cell_size
                x_max = min(bbox.xMaximum(), x_min + cell_size)
                rect = QgsRectangle(x_min, y_min, x_max, y_max)
                raw_cell = QgsGeometry.fromRect(rect)
                if not raw_cell.intersects(study_union):
                    continue
                cell_geom = raw_cell.intersection(study_union)
                if cell_geom is None or cell_geom.isEmpty() or cell_geom.area() <= 0:
                    continue

                cell_id += 1
                center_xy = cell_geom.centroid().asPoint()
                # Sample centroid and quarter-offset points to capture low coastal edges
                dx = (x_max - x_min) * 0.25
                dy = (y_max - y_min) * 0.25
                sample_pts = [
                    center_xy,
                    QgsPointXY(center_xy.x() - dx, center_xy.y()),
                    QgsPointXY(center_xy.x() + dx, center_xy.y()),
                    QgsPointXY(center_xy.x(), center_xy.y() - dy),
                    QgsPointXY(center_xy.x(), center_xy.y() + dy),
                ]
                samples = [
                    v for v in (_sample_dem(dem_provider, pt, dem_transform) for pt in sample_pts)
                    if v is not None
                ]
                elev_m = min(samples) if samples else None
                coast_dist = float(cell_geom.distance(coast_union))
                submerged_raw = bool(elev_m is not None and elev_m <= total_wl)

                cells[(r, c)] = {
                    "cell_id": cell_id,
                    "geom": cell_geom,
                    "elev_m": elev_m,
                    "coast_dist": coast_dist,
                    "submerged_raw": submerged_raw,
                    "connected": 0,
                }

        # Step 2: Hydrological connectivity BFS (Poulter & Halpin, 2008)
        neighbors_delta = (
            [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
            if conn_rule == 0
            else [(-1, 0), (1, 0), (0, -1), (0, 1)]
        )
        queue = deque()
        for rc_key, info in cells.items():
            if info["submerged_raw"] and info["coast_dist"] <= seed_tolerance:
                info["connected"] = 1
                queue.append(rc_key)

        while queue:
            r_curr, c_curr = queue.popleft()
            for dr, dc in neighbors_delta:
                nb_key = (r_curr + dr, c_curr + dc)
                nb = cells.get(nb_key)
                if nb is not None and nb["submerged_raw"] and nb["connected"] == 0:
                    nb["connected"] = 1
                    queue.append(nb_key)

        # Step 3: Score cells and write outputs
        grid_fields = QgsFields()
        grid_fields.append(QgsField("cell_id", QVariant.Int))
        grid_fields.append(QgsField("elev_m", QVariant.Double))
        grid_fields.append(QgsField("water_lvl_m", QVariant.Double))
        grid_fields.append(QgsField("inund_m", QVariant.Double))
        grid_fields.append(QgsField("freeboard_m", QVariant.Double))
        grid_fields.append(QgsField("sink_depth", QVariant.Double))
        grid_fields.append(QgsField("connected", QVariant.Int))
        grid_fields.append(QgsField("coast_dist", QVariant.Double))
        grid_fields.append(QgsField("bldg_count", QVariant.Int))
        grid_fields.append(QgsField("road_hit", QVariant.Int))
        grid_fields.append(QgsField("slr_score", QVariant.Double))
        grid_fields.append(QgsField("risk_class", QVariant.String))

        exposed_fields = QgsFields()
        exposed_fields.append(QgsField("struct_id", QVariant.Int))
        exposed_fields.append(QgsField("cell_id", QVariant.Int))
        exposed_fields.append(QgsField("inund_m", QVariant.Double))
        exposed_fields.append(QgsField("connected", QVariant.Int))
        exposed_fields.append(QgsField("slr_score", QVariant.Double))
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

        exposed_struct_ids = set()
        total_items = max(len(cells), 1)
        for idx, ((r, c), info) in enumerate(cells.items()):
            if feedback.isCanceled():
                break
            cell_geom = info["geom"]
            elev_m = info["elev_m"]
            coast_dist = info["coast_dist"]
            connected = info["connected"]
            submerged_raw = info["submerged_raw"]

            if elev_m is None:
                inund_m = 0.0
                freeboard_m = -1.0
                sink_depth = 0.0
                depth_score = 25.0
            elif connected == 1:
                inund_m = max(0.0, total_wl - elev_m)
                freeboard_m = 0.0
                sink_depth = 0.0
                # Connected inundation depth: 0 m -> 65, >= 2.0 m -> 100
                depth_score = clamp(65.0 + (inund_m / 2.0) * 35.0, 65.0, 100.0)
            elif submerged_raw:
                # Disconnected inland depression below water level
                inund_m = 0.0
                freeboard_m = 0.0
                sink_depth = max(0.0, total_wl - elev_m)
                depth_score = clamp(15.0 + (sink_depth / 2.0) * 15.0, 15.0, 30.0)
            else:
                inund_m = 0.0
                freeboard_m = max(0.0, elev_m - total_wl)
                sink_depth = 0.0
                # Low freeboard within 2.5 m above design water level still carries surge/wave risk
                depth_score = clamp((1.0 - freeboard_m / 2.5) * 55.0, 0.0, 55.0)

            shore_score = clamp((1.0 - coast_dist / max(shore_buf * 2.0, 1.0)) * 100.0, 0.0, 100.0)

            bldg_count = 0
            cell_bldgs = []
            if bldg_feats:
                for fid in bldg_index.intersects(cell_geom.boundingBox()):
                    bf = bldg_by_id.get(fid)
                    if bf and bf.geometry().intersects(cell_geom):
                        bldg_count += 1
                        cell_bldgs.append(bf)
            road_hit = 1 if (road_union is not None and not road_union.isEmpty() and cell_geom.intersects(road_union)) else 0
            asset_score = clamp((bldg_count / 5.0) * 75.0 + road_hit * 25.0, 0.0, 100.0)

            slr_score = clamp(
                0.55 * depth_score + 0.25 * shore_score + 0.20 * asset_score,
                0.0,
                100.0,
            )
            r_class = composite_risk_class(slr_score)

            attrs = [
                info["cell_id"],
                round(elev_m, 2) if elev_m is not None else -9999.0,
                round(total_wl, 2),
                round(inund_m, 2),
                round(freeboard_m, 2),
                round(sink_depth, 2),
                connected,
                round(coast_dist, 2),
                bldg_count,
                road_hit,
                round(slr_score, 2),
                r_class,
            ]

            feat = QgsFeature(grid_fields)
            feat.setGeometry(cell_geom)
            feat.setAttributes(attrs)
            grid_sink.addFeature(feat, QgsFeatureSink.FastInsert)

            if connected == 1 or slr_score >= 55.0:
                pfeat = QgsFeature(grid_fields)
                pfeat.setGeometry(cell_geom)
                pfeat.setAttributes(attrs)
                prio_sink.addFeature(pfeat, QgsFeatureSink.FastInsert)

            if (connected == 1 or slr_score >= 50.0) and cell_bldgs:
                for bf in cell_bldgs:
                    if bf.id() in exposed_struct_ids:
                        continue
                    exposed_struct_ids.add(bf.id())
                    efeat = QgsFeature(exposed_fields)
                    efeat.setGeometry(bf.geometry().centroid())
                    efeat.setAttributes([
                        int(bf.id()),
                        info["cell_id"],
                        round(inund_m, 2),
                        connected,
                        round(slr_score, 2),
                        r_class,
                    ])
                    exp_sink.addFeature(efeat, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(((idx + 1) / total_items) * 100))

        return {
            self.OUTPUT_GRID: grid_id,
            self.OUTPUT_PRIORITY: prio_id,
            self.OUTPUT_EXPOSED: exp_id,
        }
