# -*- coding: utf-8 -*-
"""Check that the key result fields of the practical-guide run carry real signal.

A guide is only worth shipping if the screenshots show a real analysis: every
scored output must vary across space, and the chained tools must actually
consume the layer produced before them.
"""
import json
import sys
from pathlib import Path

GUIDE = Path(r"C:\Users\YE\PyCharmMiscProject\qgis_plugins\planx_urban_resilience\docs\PRACTICAL_GUIDE")
WORK = GUIDE / "work"

sys.path.append(r"C:\OSGeo4W\apps\qgis-ltr\python\plugins")
from qgis.core import QgsApplication, QgsVectorLayer  # noqa: E402
from qgis.PyQt.QtCore import QVariant  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

# algo -> (output file, field, min distinct values)
CHECKS = [
    ("urban_heat_comfort_risk", "OUTPUT_GRID.gpkg", "heat_score", 4),
    ("pluvial_flood_susceptibility", "OUTPUT_GRID.gpkg", "flood_score", 4),
    ("pluvial_flood_susceptibility", "OUTPUT_BUILDINGS.gpkg", "flood_score", 1),
    ("coastal_slr_exposure", "OUTPUT_GRID.gpkg", "slr_score", 4),
    ("coastal_slr_exposure", "OUTPUT_PRIORITY.gpkg", "slr_score", 2),
    ("emergency_accessibility_shelter_coverage", "OUTPUT_GRID.gpkg", "access_score", 4),
    ("emergency_accessibility_shelter_coverage", "OUTPUT_UNDERSERVED.gpkg", "access_score", 1),
    ("air_quality_exposure_screening", "OUTPUT_GRID.gpkg", "air_score", 4),
    ("wui_exposure_screening", "OUTPUT_GRID.gpkg", "wui_score", 4),
    ("green_infrastructure_drought_stress", "OUTPUT_STRESS.gpkg", "stress_score", 2),
    ("green_infrastructure_drought_stress", "OUTPUT_PRIORITY.gpkg", "stress_score", 1),
    ("social_vulnerability_index", "OUTPUT.gpkg", "svi_score", 3),
    ("seismic_debris_monte_carlo", "OUTPUT_VULNERABILITY.gpkg", "collapse_prob", 2),
    ("seismic_debris_monte_carlo", "OUTPUT_VULNERABILITY.gpkg", "collapsed", 2),
    ("seismic_debris_monte_carlo", "OUTPUT_CUMULATIVE_BLOCKAGE.gpkg", None, 1),
    ("seismic_debris_monte_carlo", "OUTPUT_CLEARANCE_CORRIDORS.gpkg", None, 1),
    ("network_emergency_accessibility", "OUTPUT_ORIGINS.gpkg", "time_min", 4),
    ("network_emergency_accessibility", "OUTPUT_ORIGINS.gpkg", "net_dist_m", 4),
    ("evacuation_time_simulation", "OUTPUT_ORIGINS.gpkg", "evac_min", 3),
    ("evacuation_time_simulation", "OUTPUT_SHELTERS.gpkg", "cap_used", 2),
    ("evacuation_time_simulation", "OUTPUT_EDGES.gpkg", "trip_count", 2),
    ("network_criticality", "OUTPUT.gpkg", "criticality_score", 2),
    ("seismic_cascade_accessibility", "OUTPUT.gpkg", "cas_status", 2),
    ("optimal_shelter_siting", "OUTPUT.gpkg", "oss_selected", 2),
    ("optimal_shelter_siting", "OUTPUT.gpkg", "oss_rank", 2),
    ("join_scores_to_planning_units", "OUTPUT.gpkg", "heat_score", 6),
    ("join_scores_to_planning_units", "OUTPUT.gpkg", "flood_score", 6),
    ("join_scores_to_planning_units", "OUTPUT.gpkg", "access_score", 6),
    ("multi_hazard_composite_index", "OUTPUT.gpkg", "mh_score", 6),
    ("equity_adjusted_priority", "OUTPUT.gpkg", "eq_adjusted_score", 6),
    ("climate_adaptation_priority_synthesis", "OUTPUT.gpkg", "adapt_score", 6),
    ("climate_adaptation_priority_synthesis", "OUTPUT.gpkg", "adapt_class", 2),
    ("climate_projection_overlay", "OUTPUT.gpkg", "cp_projected", 6),
    ("recovery_capacity_index", "OUTPUT.gpkg", "rc_score", 6),
    ("risk_recovery_priority_matrix", "OUTPUT.gpkg", "rr_priority_score", 6),
    ("hotspot_analysis_getis_ord", "OUTPUT.gpkg", "gi_zscore", 6),
    ("lisa_local_moran", "OUTPUT.gpkg", "lisa_z", 6),
    ("population_weighted_exposure", "OUTPUT.gpkg", "pop_exposed", 6),
    ("hazard_frequency_aggregation", "OUTPUT.gpkg", "hf_composite", 4),
    ("vulnerability_surface_idw", "OUTPUT.gpkg", "vs_value", 4),
    ("critical_infrastructure_exposure", "OUTPUT.gpkg", "ci_combined", 2),
    ("scenario_sensitivity", "OUTPUT.gpkg", "ss_mean", 6),
    ("risk_trend_hotspot", "OUTPUT.gpkg", "trh_gi_z", 6),
    ("cost_benefit_analyzer", "OUTPUT.gpkg", "cb_ratio", 6),
    ("pareto_optimal_selector", "OUTPUT.gpkg", "pareto_rank", 2),
    ("lifecycle_cost_calculator", "OUTPUT.gpkg", "lc_total_npv", 6),
    ("resilience_time_series", "OUTPUT.gpkg", "ts_delta", 6),
    ("resilience_scenario_comparison", "OUTPUT.gpkg", "pct_change", 4),
    ("scenario_planning_template", "OUTPUT.gpkg", "scen_score", 6),
    ("bivariate_choropleth_symbology", "OUTPUT.gpkg", "bv_class", 4),
    ("risk_3d_volume_export", "OUTPUT.gpkg", "extrusion_height", 4),
    ("evacuation_shelter_arrival_summary", "OUTPUT_TABLE.gpkg", "arrivals", 2),
]

problems = []
print(f"{'algorithm':<42} {'output':<26} {'field':<20} {'n':>5}  {'min':>11} {'max':>11} {'distinct':>9}")
print("-" * 132)
for aid, fname, field, min_distinct in CHECKS:
    path = WORK / f"{aid}__{fname}"
    if not path.exists():
        problems.append(f"{aid}/{fname}: file missing")
        print(f"  !! {aid:<40} {fname:<26} MISSING")
        continue
    lyr = QgsVectorLayer(str(path), aid, "ogr")
    if not lyr.isValid():
        problems.append(f"{aid}/{fname}: invalid layer")
        continue
    if field is None:
        n = lyr.featureCount()
        if n < min_distinct:
            problems.append(f"{aid}/{fname}: only {n} features")
        print(f"     {aid:<40} {fname:<26} {'(all features)':<20} {n:>5}")
        continue
    if lyr.fields().lookupField(field) < 0:
        names = [f.name() for f in lyr.fields()]
        problems.append(f"{aid}/{fname}: no field '{field}' (has {names})")
        print(f"  !! {aid:<40} {fname:<26} NO FIELD '{field}' -> {names}")
        continue
    raw = []
    for feat in lyr.getFeatures():
        v = feat.attribute(field)
        if isinstance(v, QVariant):
            if v.isNull():
                continue
            v = v.value()
        if v is None or v == "":
            continue
        raw.append(v)
    if not raw:
        problems.append(f"{aid}/{fname}: field '{field}' is empty")
        print(f"  !! {aid:<40} {fname:<26} EMPTY FIELD '{field}'")
        continue
    if isinstance(raw[0], str):
        distinct = len(set(raw))
        lo = hi = "-"
    else:
        nums = [float(v) for v in raw]
        distinct = len(set(round(v, 4) for v in nums))
        lo, hi = f"{min(nums):.3f}", f"{max(nums):.3f}"
    if distinct < min_distinct:
        problems.append(f"{aid}: '{field}' has only {distinct} distinct values "
                        f"(expected >= {min_distinct})")
    print(f"     {aid:<40} {fname:<26} {field:<20} {len(raw):>5}  {lo:>11} {hi:>11} {distinct:>9}")

print("\n" + "=" * 132)
if problems:
    print(f"{len(problems)} PROBLEM(S):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("All key result fields carry real signal.")
