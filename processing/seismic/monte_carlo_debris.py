# -*- coding: utf-8 -*-

"""
PlanX: Urban Resilience — Seismic / debris module (Monte Carlo).
Yazar: Araş. Gör. Yusuf Eminoğlu
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
from PyQt5.QtCore import QVariant
import math
import random

class UrbanResilienceSeismicAnalystV2(QgsProcessingAlgorithm):

    INPUT_BUILDINGS = 'INPUT_BUILDINGS'
    FIELD_FLOORS = 'FIELD_FLOORS'
    FIELD_YEAR = 'FIELD_YEAR'
    MAGNITUDE = 'MAGNITUDE'
    INPUT_PARCELS = 'INPUT_PARCELS'
    INPUT_STUDY_AREA = 'INPUT_STUDY_AREA'
    FLOOR_HEIGHT = 'FLOOR_HEIGHT'
    DEBRIS_FACTOR = 'DEBRIS_FACTOR'
    SOLID_VOLUME_RATIO = 'SOLID_VOLUME_RATIO'

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
        return 'sismik_risk_dinamik_analizor_v2'

    def displayName(self):
        return self.tr('Deprem sonrası yıkım–enkaz–tahliye ağı (Monte Carlo)')

    def group(self):
        return self.tr('1 — Deprem: enkaz ve lojistik')

    def groupId(self):
        return 'planx_urban_resilience_seismic'

    def shortHelpString(self):
        return self.tr(
            """
            <h3><b>Algoritma Metodolojisi ve Teorik Çerçeve</b></h3>
            <p>Bu modül, sismik senaryolara dayalı olarak yapısal kırılganlık ve kentsel mobilite kaybını modelleyen gelişmiş bir stokastik mekansal karar destek sistemidir. Monte Carlo simülasyonu ile yapı yaşı ve moment magnitüd (Mw) etkileşimini değerlendirerek her iterasyonda dinamik risk zarfları üretir.</p>
            
            <h3><b>Girdi Parametreleri Kılavuzu</b></h3>
            <table border="1" style="border-collapse: collapse; width: 100%;">
              <tr>
                <th style="padding: 5px; text-align: left;">Parametre</th>
                <th style="padding: 5px; text-align: left;">Açıklama & Tavsiye Edilen Değerler</th>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Moment Magnitüd (Mw)</b></td>
                <td style="padding: 5px;">Deprem enerjisi. Kırılganlık fonksiyonunda eksponansiyel etki yaratır (Örn: 7.0 - 7.6).</td>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Enkaz Yayılım Katsayısı (k)</b></td>
                <td style="padding: 5px;">Yıkılan binanın yüksekliğinin ne kadarının yatayda yola savrulacağını belirler (Goretti & Sarli, 2006). Genellikle <b>0.30 ile 0.50</b> arası alınır.</td>
              </tr>
              <tr>
                <td style="padding: 5px;"><b>Yapı Boşluk/Katı Oranı</b></td>
                <td style="padding: 5px;">Brüt bina hacminin ne kadarının gerçek moloz (beton/tuğla) olacağını belirler. FEMA standartlarına göre: <br>• Çelik/Cam: <b>0.10 - 0.20</b><br>• Betonarme (RC): <b>0.25 - 0.35</b><br>• Yığma Yapı: <b>0.35 - 0.45</b></td>
              </tr>
            </table>

            <h3><b>Çıktı Şeması (Output Specifications)</b></h3>
            <ul>
                <li><b>[01_Sabit] Net Lojistik Ağ Topolojisi:</b> Yapı izdüşümleri düşülmüş net kadastral yol/boşluk dokusu.</li>
                <li><b>[02_Sabit] Morfolojik Çatışma:</b> Parsel sınırlarına olan tecavüzleri negatif vektörlerle modellediğimiz statik form indeksi.</li>
                <li><b>[03_Dinamik] Stokastik Risk ve Hacim İndeksi:</b> Yıkılma olasılıkları, tahmini enkaz hacmi (m³) ve şiddet sınıflarını içeren nokta katmanı.</li>
                <li><b>[04_Dinamik] Makro-Enkaz Yayılım Zarfı:</b> Yıkılan yapıların oluşturduğu birleşik (dissolved) enkaz poligonu.</li>
                <li><b>[05_Dinamik] Kritik Ağ Blokaj Alanları:</b> Sadece yol ağı üzerine düşen kümülatif enkaz kütlesi.</li>
                <li><b>[06_Dinamik] Afet Sonrası Aktif Tahliye Koridorları:</b> Arama-kurtarma lojistiği için açık kalan erişilebilir rotalar.</li>
            </ul>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_BUILDINGS, self.tr('Giriş: Bina İzdüşümleri (Poligon)'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(self.FIELD_FLOORS, self.tr('Öznitelik: Kat Adedi'), parentLayerParameterName=self.INPUT_BUILDINGS, type=QgsProcessingParameterField.Any))
        self.addParameter(QgsProcessingParameterField(self.FIELD_YEAR, self.tr('Öznitelik: İnşa Yılı'), parentLayerParameterName=self.INPUT_BUILDINGS, type=QgsProcessingParameterField.Numeric))

        param_mag = QgsProcessingParameterNumber(self.MAGNITUDE, self.tr('Senaryo: Moment Magnitüd (Mw)'), type=QgsProcessingParameterNumber.Double, minValue=4.0, maxValue=9.0, defaultValue=7.0)
        param_mag.setMetadata({'widget_wrapper': {'tooltip': 'Kırılganlık eğrisini eksponansiyel olarak etkiler. (Örn: 7.2)'}})
        self.addParameter(param_mag)

        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_PARCELS, self.tr('Giriş: Kadastral Parseller (Poligon)'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT_STUDY_AREA, self.tr('Giriş: Çalışma Alanı / Ağ Sınırları (Poligon)'), [QgsProcessing.TypeVectorPolygon]))

        self.addParameter(QgsProcessingParameterNumber(self.FLOOR_HEIGHT, self.tr('Parametre: Ortalama Kat Yüksekliği (m)'), type=QgsProcessingParameterNumber.Double, defaultValue=3.0))

        param_k = QgsProcessingParameterNumber(self.DEBRIS_FACTOR, self.tr('Parametre: Enkaz Yayılım Katsayısı (k)'), type=QgsProcessingParameterNumber.Double, minValue=0.0, maxValue=1.0, defaultValue=0.4)
        param_k.setMetadata({'widget_wrapper': {'tooltip': 'Bina yüksekliğinin yatay yayılım oranı (Genellikle 0.3 - 0.5)'}})
        self.addParameter(param_k)

        param_solid = QgsProcessingParameterNumber(self.SOLID_VOLUME_RATIO, self.tr('Parametre: Yapı Boşluk/Katı Oranı (Hafriyat İçin)'), type=QgsProcessingParameterNumber.Double, minValue=0.1, maxValue=1.0, defaultValue=0.3)
        param_solid.setMetadata({'widget_wrapper': {'tooltip': 'FEMA Standartları:\nBetonarme: 0.25 - 0.35\nYığma: 0.35 - 0.45\nÇelik: 0.10 - 0.20'}})
        self.addParameter(param_solid)

        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_NET_ROAD, self.tr('[01_Sabit] Net Lojistik Ağ Topolojisi')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_MORPHOLOGY, self.tr('[02_Sabit] Morfolojik Çatışma ve Tecavüz Alanları')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_VULNERABILITY, self.tr('[03_Dinamik] Stokastik Yapısal Hasar ve Enkaz Hacim İndeksi')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_HAZARD_MODEL, self.tr('[04_Dinamik] Makro-Enkaz Yayılım Zarfı (Dissolved)')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_CUMULATIVE_BLOCKAGE, self.tr('[05_Dinamik] Kritik Ağ Blokaj (Kapanma) Alanları')))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT_CLEARANCE_CORRIDORS, self.tr('[06_Dinamik] Afet Sonrası Aktif Tahliye Koridorları')))

    def processAlgorithm(self, parameters, context, feedback):
        source_buildings = self.parameterAsSource(parameters, self.INPUT_BUILDINGS, context)
        source_parcels = self.parameterAsSource(parameters, self.INPUT_PARCELS, context)
        source_study_area = self.parameterAsSource(parameters, self.INPUT_STUDY_AREA, context)

        magnitude = self.parameterAsDouble(parameters, self.MAGNITUDE, context)
        floor_h = self.parameterAsDouble(parameters, self.FLOOR_HEIGHT, context)
        debris_k = self.parameterAsDouble(parameters, self.DEBRIS_FACTOR, context)
        vol_ratio = self.parameterAsDouble(parameters, self.SOLID_VOLUME_RATIO, context)

        f_floors = self.parameterAsString(parameters, self.FIELD_FLOORS, context)
        f_year = self.parameterAsString(parameters, self.FIELD_YEAR, context)

        (sink_net_road, id_net_road) = self.parameterAsSink(parameters, self.OUTPUT_NET_ROAD, context, source_study_area.fields(), QgsWkbTypes.MultiPolygon, source_study_area.sourceCrs())
        (sink_morphology, id_morphology) = self.parameterAsSink(parameters, self.OUTPUT_MORPHOLOGY, context, source_parcels.fields(), QgsWkbTypes.MultiPolygon, source_parcels.sourceCrs())
        (sink_cumulative, id_cumulative) = self.parameterAsSink(parameters, self.OUTPUT_CUMULATIVE_BLOCKAGE, context, source_study_area.fields(), QgsWkbTypes.MultiPolygon, source_study_area.sourceCrs())
        (sink_clearance, id_clearance) = self.parameterAsSink(parameters, self.OUTPUT_CLEARANCE_CORRIDORS, context, source_study_area.fields(), QgsWkbTypes.MultiPolygon, source_study_area.sourceCrs())
        (sink_hazard, id_hazard) = self.parameterAsSink(parameters, self.OUTPUT_HAZARD_MODEL, context, QgsFields(), QgsWkbTypes.MultiPolygon, source_buildings.sourceCrs())

        v_fields = source_buildings.fields()
        v_fields.append(QgsField("Yukseklik_m", QVariant.Double))
        v_fields.append(QgsField("Cekme_Mes_m", QVariant.Double))
        v_fields.append(QgsField("Cokme_Olasilik", QVariant.Double))
        v_fields.append(QgsField("Yikildi_Mi", QVariant.Int))
        v_fields.append(QgsField("Enkaz_Y_Cap", QVariant.Double))
        v_fields.append(QgsField("Hafriyat_m3", QVariant.Double))
        v_fields.append(QgsField("Kapanan_Alan", QVariant.Double))
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
        total_buildings = source_buildings.featureCount()

        idx_f = source_buildings.fields().indexFromName(f_floors)
        idx_y = source_buildings.fields().indexFromName(f_year)
        total_blocked_area = 0.0
        total_debris_volume = 0.0

        for current_step, b_feat in enumerate(source_buildings.getFeatures()):
            if feedback.isCanceled(): break

            b_geom = b_feat.geometry().makeValid()
            b_attrs = b_feat.attributes()
            b_area = b_geom.area()

            is_encroaching = original_road_union.intersects(b_geom)
            S = -1.0 * math.sqrt(b_geom.intersection(original_road_union).area()) if is_encroaching else b_geom.distance(original_road_union)

            try: floors = float(b_attrs[idx_f]) if b_attrs[idx_f] is not None else 1.0
            except: floors = 1.0
            try: year = int(b_attrs[idx_y]) if b_attrs[idx_y] is not None else 2000
            except: year = 2000

            H = floors * floor_h

            if year <= 1985: base_p = 0.85
            elif year <= 2000: base_p = 0.60
            elif year <= 2018: base_p = 0.25
            else: base_p = 0.05

            mag_factor = math.exp(0.8 * (magnitude - 7.0))
            p_collapse = min(base_p * mag_factor, 1.0)

            will_collapse = 1 if random.random() < p_collapse else 0

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

        QgsMessageLog.logMessage(f"Mw {magnitude} SİMÜLASYONU: {total_blocked_area:.2f} m2 alan kapandı. Tahmini Hafriyat: {total_debris_volume:.2f} m3", "PlanX Urban Resilience", Qgis.Success)

        return {
            self.OUTPUT_NET_ROAD: id_net_road,
            self.OUTPUT_MORPHOLOGY: id_morphology,
            self.OUTPUT_VULNERABILITY: id_vulnerability,
            self.OUTPUT_HAZARD_MODEL: id_hazard,
            self.OUTPUT_CUMULATIVE_BLOCKAGE: id_cumulative,
            self.OUTPUT_CLEARANCE_CORRIDORS: id_clearance
        }