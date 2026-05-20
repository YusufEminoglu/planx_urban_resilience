# PlanX Urban Resilience — Roadmap

Mevcut **27** algoritma. Aşağıdaki maddelerin çoğu v1.11–v1.14 arasında tamamlandı; kalanlar için öncelik: yüksek-değer + düşük-bağımlılık.

## 1. Multi-Hazard Composite Index ✅ (v1.11)

**Sorun:** Adaptation Priority Synthesis tek bir composite score üretiyor ama hangi hazard'ın dominant olduğunu gizliyor.

**Çözüm:** Yeni algoritma `multi_hazard_composite`:
- Input: planning units + 4-8 hazard skor alanı (seismik, ısı, taşkın, hava, vs.)
- Çıktı: 0-100 composite + her hazard için percentile rank + dominant hazard label + diversity score (Shannon entropy)
- Kullanım: "bu mahalle ısı baskın", "bu mahalle multi-stress (3+ hazard yüksek)"

**Tahmini iş:** 1 algoritma dosyası (~150 satır), `synthesis/multi_hazard_composite.py`.

## 2. Network Betweenness for Criticality ✅ (v1.12, `network_criticality`)

**Sorun:** Network Emergency Accessibility origin→shelter zamanını veriyor ama hangi yol segmenti kritik?

**Çözüm:** `network_criticality`:
- Input: road network + shelter veya OD pairs
- Edge betweenness (NetworkX kullanarak veya QGIS native) → her segment için 0-100 önem skoru
- "Bu yol kapanırsa erişim %X düşer" senaryosu (single link removal)

**Tahmini iş:** ~200 satır, NetworkX dependency yoksa graph yapısı zaten `network_accessibility.py`'de var, oradan adapt edilebilir.

## 3. Evacuation Time Simulation ✅ (v1.15 greedy v1, v1.16 timestep queue + edge capacity)

**Sorun:** Static accessibility ≠ acil tahliye gerçekliği (yol kapasitesi, nüfus yığılması).

**Çözüm:** `evacuation_simulation`:
- Input: origins + population + shelters + road network + road capacity field
- Macro-level capacity-constrained shortest path (per timestep)
- Çıktı: shelter doluluk eğrisi, tahliye süresi P50/P95, kritik bottleneck segmentleri

**Tahmini iş:** ~300 satır, daha karmaşık. İlk versiyon basit greedy assignment, sonra iyileştirilebilir.

## 4. Climate Projection Overlay ✅ (v1.12)

**Sorun:** Mevcut analizler bugün için; gelecekte iklim değişikliğine nasıl direnç?

**Çözüm:** `climate_projection_overlay`:
- Input: any 0-100 risk grid + projection scenario (kullanıcı seçer: +1.5°C, +2°C, +3°C)
- Her hazard'a göre pre-defined amplification factor (heat ×1.3, flood ×1.5 vb. — literatür bazlı)
- Çıktı: today vs future risk delta + yeni risk class

**Veri-bağımsız:** CMIP/local downscale gerektirmez. Sadece amplification tablosu. Hızlı.

**Tahmini iş:** ~120 satır.

## 5. Recovery Capacity Index ✅ (v1.13)

**Sorun:** Resilience = absorb + recover. Şu an sadece "stress/exposure" var.

**Çözüm:** `recovery_capacity_index`:
- Input: planning units + asset diversity (mixed-use), green coverage, social cohesion proxies (population stability, ownership rate), redundancy (multiple road accesses, multiple shelters in range)
- Çıktı: 0-100 recovery capacity score
- Adaptation Priority ile **complementary**: hangi mahalleler hem yüksek-risk hem düşük-recovery = öncelikli müdahale

**Tahmini iş:** ~180 satır.

## 6. PDF Atlas Export ✅ (v1.14, `resilience_pdf_atlas`)

**Sorun:** HTML/Markdown var ama saha çalışmaları için printable atlas isteniyor.

**Çözüm:** `resilience_pdf_atlas`:
- Input: scored layer(s) + study area + basemap optional + cover page metadata
- QgsLayout API ile haritalar + tablolar + brand kapak → tek PDF
- Output: file path

**Tahmini iş:** ~250 satır, QgsLayout API öğrenme eğrisi.

## 7. Resilience Time-Series Tracker ✅ (v1.13)

**Sorun:** Tek snapshot. İlerleme nasıl ölçülecek?

**Çözüm:** `resilience_time_series`:
- Input: aynı planning unit layer'ın 2+ tarihli versiyonu (örn. 2020, 2025, 2030 hedef)
- Çıktı: per-unit trend (artıyor/sabit/azalıyor), aggregate trend, hedef-açığı haritası

**Tahmini iş:** ~150 satır. Veri sahipliği zor.

## 8. Equity-Adjusted Adaptation Priority ✅ (v1.11)

**Sorun:** Adaptation Priority en yüksek risk olanları öne çıkarır, ama bu zaten zengin mahalleler olabilir (better data + better infrastructure).

**Çözüm:** `equity_adjusted_priority`:
- Mevcut adaptation priority skoru + social vulnerability skoru
- Çıktı: equity-weighted priority (yüksek risk + yüksek sosyal kırılganlık = en yüksek müdahale önceliği)
- Pareto front görselleştirme parametresi

**Tahmini iş:** ~100 satır. Mevcut iki algoritmanın çıktısını birleştirir.

## 9. Scenario Sensitivity Analysis ✅ (v1.14, `scenario_sensitivity`)

**Sorun:** Composite skorlar ağırlıklara hassas. Hangi ağırlık ne kadar etkili?

**Çözüm:** `scenario_sensitivity`:
- Input: any composite scored layer + ağırlık aralıkları
- Latin Hypercube Sampling → 100-1000 ağırlık kombinasyonu → her unit için skor dağılımı
- Çıktı: stability score (düşük varyans = robust), tipping-point sıralaması

**Tahmini iş:** ~200 satır. Numpy gerekir (zaten transitive olarak QGIS Python'da var).

---

## Önerilen sürüm planı (güncel)

- **v1.10–v1.14:** Tamamlandı (yukarıdaki ✅ maddeler).
- **v1.17:** Shelter arrival summary ✅, PDF map-book presets ✅, `_helpers.py` ✅, `network_accessibility` → `_network_graph` ✅.
- **v1.18:** Risk-recovery matrix ✅, directional roads (ft/bt) ✅, equity/scenario → `_helpers` ✅.
- **v1.19:** Join scores to planning units ✅; full `_helpers` rollout (hazard + reporting/synthesis) ✅; `build_local_zip.ps1` ✅.
- **v2.0+:** GEE climate connectors (büyük adım).
- **v2.0.0:** GEE climate connectors + map-book presets (büyük adım).

## Mimari notlar

- Yeni algoritmalar için **mevcut helper pattern**'ini kullan: `_clamp`, `_risk_class`, `_features`, `_union` (heat/flood'ta var). Belki bunları `processing/_helpers.py` ortak modüle taşımak gerekir — DRY ihlali olmaması için sürüm planında refactor adımı düşün.
- Provider `loadAlgorithms` listesine ekleme zorunlu — yeni algoritma görünmez aksi halde.
- Dashboard `MODULES` listesine de ekleme — UI'da görünmesi için.
- Her yeni algoritma için **synthetic_dataset**'i de güncelle: smoke test girdi katmanları üretsin.
