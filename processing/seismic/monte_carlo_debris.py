# -*- coding: utf-8 -*-

"""
PlanX: Urban Resilience — Seismic / debris module (Monte Carlo).
"""

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsFeatureSink,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsField,
    QgsFields,
    QgsSpatialIndex,
    QgsMessageLog,
    Qgis
)
from qgis.PyQt.QtCore import QVariant  # Qt5/Qt6 forward-compatible (was: PyQt5.QtCore)
import math


from .._helpers import SeededRng  # noqa: E402
from .._mixins import HelpUrlMixin  # noqa: E402


class UrbanResilienceSeismicAnalystV2(HelpUrlMixin, QgsProcessingAlgorithm):

    INPUT_BUILDINGS = 'INPUT_BUILDINGS'
    FIELD_FLOORS = 'FIELD_FLOORS'
    FIELD_YEAR = 'FIELD_YEAR'
    MAGNITUDE = 'MAGNITUDE'
    INPUT_PARCELS = 'INPUT_PARCELS'
    INPUT_STUDY_AREA = 'INPUT_STUDY_AREA'
    FLOOR_HEIGHT = 'FLOOR_HEIGHT'
    DEBRIS_FACTOR = 'DEBRIS_FACTOR'
    SOLID_VOLUME_RATIO = 'SOLID_VOLUME_RATIO'
    SEED = 'SEED'

    OUTPUT_NET_ROAD = 'OUTPUT_NET_ROAD'
    OUTPUT_MORPHOLOGY = 'OUTPUT_MORPHOLOGY'
    OUTPUT_VULNERABILITY = 'OUTPUT_VULNERABILITY'
    OUTPUT_HAZARD_MODEL = 'OUTPUT_HAZARD_MODEL'
    OUTPUT_CUMULATIVE_BLOCKAGE = 'OUTPUT_CUMULATIVE_BLOCKAGE'
    OUTPUT_CLEARANCE_CORRIDORS = 'OUTPUT_CLEARANCE_CORRIDORS'

    def tr(self, string):
        return string

    def createInstance(self):
        return UrbanResilienceSeismicAnalystV2()

    def name(self):
        return 'seismic_debris_monte_carlo'

    def displayName(self):
        return self.tr('Post-Earthquake Collapse, Debris & Evacuation Network (Monte Carlo)')

    def group(self):
        return self.tr('1 — Seismic: Debris & Logistics')

    def groupId(self):
        return 'planx_urban_resilience_seismic'

    def shortHelpString(self):
        return self.tr(
            """
            <h3><b>Methodology &amp; Theoretical Framework</b></h3>
            <p>This module is a stochastic spatial decision-support engine that models structural
            vulnerability and urban mobility loss for a given earthquake scenario. A Monte Carlo
            simulation evaluates the interaction between building age and moment magnitude (Mw),
            producing a dynamic risk envelope on every run. A seed parameter is exposed so a given
            scenario can be reproduced exactly, or re-rolled by changing the seed.</p>

            <h3><b>Input Parameter Guide</b></h3>
            <table border="1" style="border-collapse: collapse; width: 100%;">
              <tr>
                <th style="padding: 5px; text-align: left;">Parameter</th>
                <th style="padding: 5px; text-align: left;">Description &amp; Recommended Values</th>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Moment Magnitude (Mw)</b></td>
                <td style="padding: 5px;">Earthquake energy. Has an exponential effect on the fragility function (e.g. 7.0 - 7.6).</td>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Debris Spread Coefficient (k)</b></td>
                <td style="padding: 5px;">Fraction of a collapsed building's height thrown horizontally onto adjacent roads (Goretti &amp; Sarli, 2006). Typically <b>0.30 to 0.50</b>.</td>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Void/Solid Volume Ratio</b></td>
                <td style="padding: 5px;">Fraction of the gross building volume that becomes actual debris (concrete/brick). Per FEMA guidance: <br>• Steel/Glass: <b>0.10 - 0.20</b><br>• Reinforced concrete (RC): <b>0.25 - 0.35</b><br>• Unreinforced masonry: <b>0.35 - 0.45</b></td>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Random Seed</b></td>
                <td style="padding: 5px;">Fixes the Monte Carlo draw so results are reproducible run-to-run; change it to sample a different stochastic realization of the same scenario.</td>
              </tr>
            </table>

            <h3><b>Output Schema</b></h3>
            <ul>
                <li><b>[01_Static] Net Logistics Network Topology:</b> Cadastral road/void fabric with building footprints subtracted.</li>
                <li><b>[02_Static] Morphological Conflict:</b> Static form index modelling encroachments onto parcel boundaries as negative vectors.</li>
                <li><b>[03_Dynamic] Stochastic Risk &amp; Volume Index:</b> Point layer with collapse probability, estimated debris volume (m3), and severity class per building.</li>
                <li><b>[04_Dynamic] Macro-Debris Spread Envelope:</b> Dissolved debris polygon covering all collapsed buildings.</li>
                <li><b>[05_Dynamic] Critical Network Blockage Areas:</b> Cumulative debris mass that falls specifically on the road network.</li>
                <li><b>[06_Dynamic] Post-Disaster Active Evacuation Corridors:</b> Remaining accessible routes for search-and-rescue logistics.</li>
            </ul>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_BUILDINGS, self.tr('Input: Building Footprints (Polygon)'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.FIELD_FLOORS, self.tr('Attribute: Floor Count'), parentLayerParameterName=self.INPUT_BUILDINGS, type=QgsProcessingParameterField.Any))
        self.addParameter(QgsProcessingParameterField(self.FIELD_YEAR, self.tr('Attribute: Construction Year'), parentLayerParameterName=self.INPUT_BUILDINGS, type=QgsProcessingParameterField.Numeric))

        param_mag = QgsProcessingParameterNumber(self.MAGNITUDE, self.tr('Scenario: Moment Magnitude (Mw)'), type=QgsProcessingParameterNumber.Double, minValue=4.0, maxValue=9.0, defaultValue=7.0)
        param_mag.setMetadata({'widget_wrapper': {'tooltip': 'Exponentially affects the fragility curve. (e.g. 7.2)'}})
        self.addParameter(param_mag)

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_PARCELS, self.tr('Input: Cadastral Parcels (Polygon)'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_STUDY_AREA, self.tr('Input: Study Area / Network Boundary (Polygon)'), [QgsProcessing.TypeVectorPolygon]))

        self.addParameter(QgsProcessingParameterNumber(self.FLOOR_HEIGHT, self.tr('Parameter: Average Floor Height (m)'), type=QgsProcessingParameterNumber.Double, defaultValue=3.0))

        param_k = QgsProcessingParameterNumber(self.DEBRIS_FACTOR, self.tr('Parameter: Debris Spread Coefficient (k)'), type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.4)
        param_k.setMetadata({'widget_wrapper': {'tooltip': 'Horizontal spread ratio of building height (typically 0.3 - 0.5)'}})
        self.addParameter(param_k)

        param_solid = QgsProcessingParameterNumber(self.SOLID_VOLUME_RATIO, self.tr('Parameter: Void/Solid Volume Ratio (for debris volume)'), type=QgsProcessingParameterNumber.Double, minValue=0.1, maxValue=1.0, defaultValue=0.3)
        param_solid.setMetadata({'widget_wrapper': {'tooltip': 'FEMA guidance:\nReinforced concrete: 0.25 - 0.35\nUnreinforced masonry: 0.35 - 0.45\nSteel: 0.10 - 0.20'}})
        self.addParameter(param_solid)

        param_seed = QgsProcessingParameterNumber(self.SEED, self.tr('Parameter: Random Seed (Monte Carlo reproducibility)'), type=QgsProcessingParameterNumber.Integer, minValue=0, maxValue=2**31 - 1, defaultValue=42)
        param_seed.setMetadata({'widget_wrapper': {'tooltip': 'Same seed + same inputs = identical collapse draw. Change it to sample a different realization.'}})
        self.addParameter(param_seed)

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_NET_ROAD, self.tr('[01_Static] Net Logistics Network Topology')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_MORPHOLOGY, self.tr('[02_Static] Morphological Conflict & Encroachment Areas')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_VULNERABILITY, self.tr('[03_Dynamic] Stochastic Structural Damage & Debris Volume Index')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_HAZARD_MODEL, self.tr('[04_Dynamic] Macro-Debris Spread Envelope (Dissolved)')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_CUMULATIVE_BLOCKAGE, self.tr('[05_Dynamic] Critical Network Blockage Areas')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_CLEARANCE_CORRIDORS, self.tr('[06_Dynamic] Post-Disaster Active Evacuation Corridors')))

    def processAlgorithm(self, parameters, context, feedback):
        source_buildings = self.parameterAsSource(parameters, self.INPUT_BUILDINGS, context)
        source_parcels = self.parameterAsSource(parameters, self.INPUT_PARCELS, context)
        source_study_area = self.parameterAsSource(parameters, self.INPUT_STUDY_AREA, context)

        magnitude = self.parameterAsDouble(parameters, self.MAGNITUDE, context)
        floor_h = self.parameterAsDouble(parameters, self.FLOOR_HEIGHT, context)
        debris_k = self.parameterAsDouble(parameters, self.DEBRIS_FACTOR, context)
        vol_ratio = self.parameterAsDouble(parameters, self.SOLID_VOLUME_RATIO, context)
        seed = self.parameterAsInt(parameters, self.SEED, context)
        rng = SeededRng(seed)

        f_floors = self.parameterAsString(parameters, self.FIELD_FLOORS, context)
        f_year = self.parameterAsString(parameters, self.FIELD_YEAR, context)

        (sink_net_road, id_net_road) = self.parameterAsSink(parameters, self.OUTPUT_NET_ROAD, context, source_study_area.fields(), QgsWkbTypes.MultiPolygon, source_study_area.sourceCrs())
        (sink_morphology, id_morphology) = self.parameterAsSink(parameters, self.OUTPUT_MORPHOLOGY, context, source_parcels.fields(), QgsWkbTypes.MultiPolygon, source_parcels.sourceCrs())
        (sink_cumulative, id_cumulative) = self.parameterAsSink(parameters, self.OUTPUT_CUMULATIVE_BLOCKAGE, context, source_study_area.fields(), QgsWkbTypes.MultiPolygon, source_study_area.sourceCrs())
        (sink_clearance, id_clearance) = self.parameterAsSink(parameters, self.OUTPUT_CLEARANCE_CORRIDORS, context, source_study_area.fields(), QgsWkbTypes.MultiPolygon, source_study_area.sourceCrs())
        (sink_hazard, id_hazard) = self.parameterAsSink(parameters, self.OUTPUT_HAZARD_MODEL, context, QgsFields(), QgsWkbTypes.MultiPolygon, source_buildings.sourceCrs())

        v_fields = source_buildings.fields()
        v_fields.append(QgsField("height_m", QVariant.Double))
        v_fields.append(QgsField("setback_dist_m", QVariant.Double))
        v_fields.append(QgsField("collapse_prob", QVariant.Double))
        v_fields.append(QgsField("collapsed", QVariant.Int))
        v_fields.append(QgsField("debris_radius_m", QVariant.Double))
        v_fields.append(QgsField("debris_vol_m3", QVariant.Double))
        v_fields.append(QgsField("blocked_area_m2", QVariant.Double))
        (sink_vulnerability, id_vulnerability) = self.parameterAsSink(parameters, self.OUTPUT_VULNERABILITY, context, v_fields, QgsWkbTypes.Point, source_buildings.sourceCrs())

        parcel_cache = {}
        spatial_index_parcels = QgsSpatialIndex()
        occupied_geoms = []

        for p_feat in source_parcels.getFeatures():
            if p_feat.hasGeometry():
                g = p_feat.geometry().makeValid()
                parcel_cache[p_feat.id()] = (g, p_feat.attributes())
                spatial_index_parcels.addFeature(p_feat)
                occupied_geoms.append(g)

        original_road_union = QgsGeometry.unaryUnion([f.geometry().makeValid() for f in source_study_area.getFeatures() if f.hasGeometry()]).makeValid()
        dissolved_obstacles = QgsGeometry.unaryUnion(occupied_geoms + [f.geometry().makeValid() for f in source_buildings.getFeatures() if f.hasGeometry()]).makeValid()
        net_road_geom = original_road_union.difference(dissolved_obstacles).makeValid()

        if not net_road_geom.isEmpty():
            feat = QgsFeature()
            feat.setGeometry(net_road_geom)
            sink_net_road.addFeature(feat, QgsFeatureSink.FastInsert)

        debris_all_list = []
        debris_on_road_list = []
        total_buildings = max(source_buildings.featureCount(), 1)  # avoid divide-by-zero on empty input

        idx_f = source_buildings.fields().indexFromName(f_floors)
        idx_y = source_buildings.fields().indexFromName(f_year)
        total_blocked_area = 0.0
        total_debris_volume = 0.0

        for current_step, b_feat in enumerate(source_buildings.getFeatures()):
            if feedback.isCanceled():
                break

            if not b_feat.hasGeometry():
                continue
            b_geom = b_feat.geometry().makeValid()
            b_attrs = b_feat.attributes()
            b_area = b_geom.area()

            is_encroaching = original_road_union.intersects(b_geom)
            S = -1.0 * math.sqrt(b_geom.intersection(original_road_union).area()) if is_encroaching else b_geom.distance(original_road_union)

            # Narrowed exception scope: only catch type/value errors from bad attribute values,
            # not KeyboardInterrupt / SystemExit (bare except was masking real errors).
            try:
                floors = float(b_attrs[idx_f]) if idx_f >= 0 and b_attrs[idx_f] is not None else 1.0
            except (TypeError, ValueError):
                floors = 1.0
            try:
                year = int(b_attrs[idx_y]) if idx_y >= 0 and b_attrs[idx_y] is not None else 2000
            except (TypeError, ValueError):
                year = 2000

            H = floors * floor_h

            if year <= 1985:
                base_p = 0.85
            elif year <= 2000:
                base_p = 0.60
            elif year <= 2018:
                base_p = 0.25
            else:
                base_p = 0.05

            mag_factor = math.exp(0.8 * (magnitude - 7.0))
            p_collapse = min(base_p * mag_factor, 1.0)

            will_collapse = 1 if rng.random() < p_collapse else 0

            E = H * debris_k if will_collapse else 0.0
            debris_vol_m3 = (b_area * H * vol_ratio) if will_collapse else 0.0
            blocked_area_m2 = 0.0

            if will_collapse:
                total_debris_volume += debris_vol_m3
                debris_geom = b_geom.buffer(E, 8, QgsGeometry.EndCapStyle.Square, QgsGeometry.JoinStyle.Miter, 2.0).makeValid()
                debris_all_list.append(debris_geom)

                road_blocked_geom = debris_geom.intersection(net_road_geom)
                blocked_area_m2 = road_blocked_geom.area()
                if not road_blocked_geom.isEmpty():
                    debris_on_road_list.append(road_blocked_geom)
                    total_blocked_area += blocked_area_m2

            out_attrs = list(b_attrs)
            out_attrs.extend([H, S, p_collapse, will_collapse, E, debris_vol_m3, blocked_area_m2])
            v_feat = QgsFeature()
            v_feat.setGeometry(b_geom.centroid())
            v_feat.setAttributes(out_attrs)
            sink_vulnerability.addFeature(v_feat, QgsFeatureSink.FastInsert)

            if S < 0:
                candidate_ids = spatial_index_parcels.intersects(b_geom.boundingBox())
                for pid in candidate_ids:
                    if pid in parcel_cache:
                        p_geom, p_attrs = parcel_cache[pid]
                        if p_geom.intersects(b_geom):
                            setback_geom = p_geom.difference(b_geom)
                            if not setback_geom.isEmpty():
                                s_feat = QgsFeature()
                                s_feat.setGeometry(setback_geom)
                                s_feat.setAttributes(p_attrs)
                                sink_morphology.addFeature(s_feat, QgsFeatureSink.FastInsert)
                                break

            feedback.setProgress(int(current_step / total_buildings * 100))

        if debris_all_list:
            dissolved_hazard = QgsGeometry.unaryUnion(debris_all_list).makeValid()
            h_feat = QgsFeature()
            h_feat.setGeometry(dissolved_hazard)
            sink_hazard.addFeature(h_feat, QgsFeatureSink.FastInsert)

        if debris_on_road_list:
            total_debris_blob = QgsGeometry.unaryUnion(debris_on_road_list).makeValid()
            d_feat = QgsFeature()
            d_feat.setGeometry(total_debris_blob)
            sink_cumulative.addFeature(d_feat, QgsFeatureSink.FastInsert)

            open_road_geom = net_road_geom.difference(total_debris_blob)
            if not open_road_geom.isEmpty():
                geoms = open_road_geom.asGeometryCollection() if open_road_geom.isMultipart() else [open_road_geom]
                for g in geoms:
                    o_feat = QgsFeature()
                    o_feat.setGeometry(g)
                    sink_clearance.addFeature(o_feat, QgsFeatureSink.FastInsert)
        else:
            o_feat = QgsFeature()
            o_feat.setGeometry(net_road_geom)
            sink_clearance.addFeature(o_feat, QgsFeatureSink.FastInsert)

        QgsMessageLog.logMessage(f"Mw {magnitude} simulation (seed {seed}): {total_blocked_area:.2f} m2 blocked. Estimated debris: {total_debris_volume:.2f} m3", "PlanX Urban Resilience", Qgis.Success)

        return {
            self.OUTPUT_NET_ROAD: id_net_road,
            self.OUTPUT_MORPHOLOGY: id_morphology,
            self.OUTPUT_VULNERABILITY: id_vulnerability,
            self.OUTPUT_HAZARD_MODEL: id_hazard,
            self.OUTPUT_CUMULATIVE_BLOCKAGE: id_cumulative,
            self.OUTPUT_CLEARANCE_CORRIDORS: id_clearance
        }
