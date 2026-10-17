# -*- coding: utf-8 -*-
"""End-to-end headless QGIS test for ALL planx_urban_resilience algorithms.

Run with OSGeo4W:
  C:/OSGeo4W/bin/python-qgis-ltr.bat tests/e2e_qgis_full.py   (QGIS 3.44)
  C:/OSGeo4W/bin/python-qgis.bat tests/e2e_qgis_full.py        (QGIS 4.x)
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import QgsApplication  # noqa: E402

qgs = QgsApplication([], False)
qgs.initQgis()

import qgis  # noqa: E402

# Prepend QGIS plugins dir so that `import processing` resolves to QGIS's
# own processing framework, not the plugin's processing/ subdirectory.
_qgis_plugins_dir = os.path.join(
    os.path.dirname(os.path.dirname(qgis.__file__)), "plugins"
)
if _qgis_plugins_dir not in sys.path:
    sys.path.insert(0, _qgis_plugins_dir)

# Make the monorepo importable for plugin discovery.
_MONOREPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(_MONOREPO_DIR)

from qgis.core import Qgis  # noqa: E402

print(f"QGIS version: {Qgis.QGIS_VERSION}")

import processing  # noqa: E402
from processing.core.Processing import Processing  # noqa: E402

Processing.initialize()

from qgis.core import (  # noqa: E402
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingUtils,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
)

from planx_urban_resilience.processing.urban_resilience_provider import (  # noqa: E402
    PlanXUrbanResilienceProvider,
)

provider = PlanXUrbanResilienceProvider()
QgsApplication.processingRegistry().addProvider(provider)

P = "planx_urban_resilience:"
TMP = tempfile.mkdtemp(prefix="urbres_e2e_")
fails = []
passed = []


class QuietFeedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.warnings = []

    def reportError(self, error, fatalError=False):
        self.warnings.append(error)


def check(cond, label):
    print(f"  [{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)


def run(algo, params, label):
    ctx = QgsProcessingContext()
    ctx.setProject(QgsProject.instance())
    fb = QuietFeedback()
    try:
        res = processing.run(P + algo, params, context=ctx, feedback=fb)
    except Exception as exc:
        traceback.print_exc()
        fails.append(f"{label}: raised {exc}")
        print(f"  [FAIL] {label}: raised {exc}")
        return None
    out = {}
    for k, v in res.items():
        if isinstance(v, str) and not v.lower().endswith(
            (".html", ".pdf", ".md", ".qml", ".geojson", ".json", ".csv")
        ):
            lyr = QgsProcessingUtils.mapLayerFromString(v, ctx)
            if lyr is not None:
                # detach from the context so the layer survives
                ctx.temporaryLayerStore().takeMapLayer(lyr)
                QgsProject.instance().addMapLayer(lyr)
                out[k] = lyr
                continue
        out[k] = v
    passed.append(label)
    print(f"  [OK] {label}")
    if fb.warnings:
        print(f"       warnings: {fb.warnings[:3]}")
    return out


def vec(out, key):
    v = (out or {}).get(key)
    return v if isinstance(v, QgsVectorLayer) else None


def nonempty(out, key, label):
    lyr = vec(out, key)
    ok = lyr is not None and lyr.isValid() and lyr.featureCount() > 0
    n = lyr.featureCount() if lyr else "n/a"
    check(ok, f"{label}: {key} non-empty (n={n})")
    return lyr


def fexists(out, key, label, minsize=10):
    pth = (out or {}).get(key)
    ok = isinstance(pth, str) and os.path.isfile(pth) and os.path.getsize(pth) >= minsize
    check(ok, f"{label}: {key} file written ({pth})")
    return pth


# ---------------------------------------------------------------- units grid
def build_units():
    """5x4 grid of 350 m cells with deterministic analytic fields."""
    uri = (
        "Polygon?crs=EPSG:3857"
        "&field=uid:integer&field=score:double&field=score_b:double"
        "&field=svi:double&field=recovery:double&field=pop:double"
        "&field=cost:double&field=benefit:double&field=capex:double"
        "&field=opex:double&field=delta:double"
    )
    lyr = QgsVectorLayer(uri, "units", "memory")
    pr = lyr.dataProvider()
    feats = []
    uid = 0
    for row in range(4):
        for col in range(5):
            uid += 1
            x0, y0 = col * 350.0, row * 350.0
            g = QgsGeometry.fromPolygonXY([[
                QgsPointXY(x0, y0), QgsPointXY(x0 + 350, y0),
                QgsPointXY(x0 + 350, y0 + 350), QgsPointXY(x0, y0 + 350),
                QgsPointXY(x0, y0),
            ]])
            # high-score cluster in the NE corner, low elsewhere
            score = 85.0 if (row >= 2 and col >= 3) else 20.0 + 2.0 * col + row
            score_b = score + 10.0 - row  # later snapshot
            svi = 30.0 + 3.0 * uid % 60
            recovery = 100.0 - score
            pop = 100.0 + 10.0 * uid
            cost = 100.0 * uid
            benefit = 50.0 * uid  # rises with cost -> a true Pareto frontier
            capex = 1000.0
            opex = 100.0
            f = QgsFeature(lyr.fields())
            f.setGeometry(g)
            f.setAttributes([uid, score, score_b, svi, recovery, pop,
                             cost, benefit, capex, opex, score_b - score])
            feats.append(f)
    pr.addFeatures(feats)
    lyr.updateExtents()
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def build_dem():
    import numpy as np
    from osgeo import gdal, osr

    nx, ny = 100, 70
    xs = np.linspace(0, 1, nx)
    arr = np.tile(20.0 + 30.0 * xs, (ny, 1)).astype(np.float32)
    arr[30:40, 40:55] = 12.0  # depression / pit
    tif = os.path.join(TMP, "dem.tif")
    ds = gdal.GetDriverByName("GTiff").Create(tif, nx, ny, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((0, 20, 0, 1400, 0, -20))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(-9999.0)
    band.WriteArray(arr)
    band.FlushCache()
    ds = None
    return tif


units = build_units()
dem = build_dem()

print("=== 1 synthetic dataset ===")
syn = run("synthetic_resilience_demo_dataset", {
    "SCALE": 1.0,
    "STUDY_AREA": "TEMPORARY_OUTPUT", "BUILDINGS": "TEMPORARY_OUTPUT",
    "ROADS": "TEMPORARY_OUTPUT", "IMPERVIOUS": "TEMPORARY_OUTPUT",
    "GREEN": "TEMPORARY_OUTPUT", "WATER": "TEMPORARY_OUTPUT",
    "SHELTERS": "TEMPORARY_OUTPUT", "SOCIAL_UNITS": "TEMPORARY_OUTPUT",
    "SENSITIVE": "TEMPORARY_OUTPUT",
}, "synthetic dataset")
study = nonempty(syn, "STUDY_AREA", "syn")
buildings = nonempty(syn, "BUILDINGS", "syn")
roads = nonempty(syn, "ROADS", "syn")
imperv = nonempty(syn, "IMPERVIOUS", "syn")
green = nonempty(syn, "GREEN", "syn")
water = nonempty(syn, "WATER", "syn")
shelters = nonempty(syn, "SHELTERS", "syn")
social = nonempty(syn, "SOCIAL_UNITS", "syn")
sensitive = nonempty(syn, "SENSITIVE", "syn")
if not all([study, buildings, roads, imperv, green, water, shelters, social, sensitive]):
    print("Cannot continue without synthetic data")
    sys.exit(1)

print("=== 2 seismic monte carlo ===")
seis = run("seismic_debris_monte_carlo", {
    "INPUT_BUILDINGS": buildings, "FIELD_FLOORS": "floor_count",
    "FIELD_YEAR": "year", "MAGNITUDE": 7.2,
    "INPUT_PARCELS": social, "INPUT_STUDY_AREA": study,
    "OUTPUT_NET_ROAD": "TEMPORARY_OUTPUT", "OUTPUT_MORPHOLOGY": "TEMPORARY_OUTPUT",
    "OUTPUT_VULNERABILITY": "TEMPORARY_OUTPUT", "OUTPUT_HAZARD_MODEL": "TEMPORARY_OUTPUT",
    "OUTPUT_CUMULATIVE_BLOCKAGE": "TEMPORARY_OUTPUT",
    "OUTPUT_CLEARANCE_CORRIDORS": "TEMPORARY_OUTPUT",
}, "seismic monte carlo debris")
if seis:
    nonempty(seis, "OUTPUT_VULNERABILITY", "seismic")

print("=== 3 heat ===")
heat = run("urban_heat_comfort_risk", {
    "STUDY_AREA": study, "BUILDINGS": buildings, "IMPERVIOUS": imperv,
    "GREEN": green, "WATER": water, "VULNERABLE": sensitive,
    "CELL_SIZE": 100, "COOLING_DISTANCE": 200,
    "OUTPUT_GRID": "TEMPORARY_OUTPUT", "OUTPUT_PRIORITY": "TEMPORARY_OUTPUT",
    "OUTPUT_EXPOSED": "TEMPORARY_OUTPUT",
}, "urban heat comfort risk")
heat_grid = nonempty(heat, "OUTPUT_GRID", "heat") if heat else None

print("=== 4 flood ===")
flood = run("pluvial_flood_susceptibility", {
    "DEM": dem, "STUDY_AREA": study, "BUILDINGS": buildings, "ROADS": roads,
    "DRAINAGE": water, "CELL_SIZE": 100,
    "OUTPUT_GRID": "TEMPORARY_OUTPUT", "OUTPUT_BUILDINGS": "TEMPORARY_OUTPUT",
    "OUTPUT_ROADS": "TEMPORARY_OUTPUT",
}, "pluvial flood susceptibility")
if flood:
    nonempty(flood, "OUTPUT_GRID", "flood")

print("=== 5 social vulnerability ===")
svi_out = run("social_vulnerability_index", {
    "AREAS": social, "POPULATION_FIELD": "population", "ELDERLY_FIELD": "elderly",
    "CHILDREN_FIELD": "children", "DISABILITY_FIELD": "disability",
    "LOW_INCOME_FIELD": "low_income", "OUTPUT": "TEMPORARY_OUTPUT",
}, "social vulnerability index")
svi_lyr = nonempty(svi_out, "OUTPUT", "svi") if svi_out else None

print("=== 6 emergency accessibility (euclidean) ===")
emg = run("emergency_accessibility_shelter_coverage", {
    "STUDY_AREA": study, "SHELTERS": shelters, "POPULATION_ASSETS": buildings,
    "CELL_SIZE": 100,
    "OUTPUT_GRID": "TEMPORARY_OUTPUT", "OUTPUT_UNDERSERVED": "TEMPORARY_OUTPUT",
}, "emergency accessibility")
if emg:
    nonempty(emg, "OUTPUT_GRID", "emergency")

print("=== 7 network accessibility ===")
net = run("network_emergency_accessibility", {
    "ROADS": roads, "ORIGINS": buildings, "DESTINATIONS": shelters,
    "SPEED_KMH": 30.0, "SNAP_TOLERANCE": 500.0,
    "OUTPUT_ORIGINS": "TEMPORARY_OUTPUT", "OUTPUT_UNDERSERVED": "TEMPORARY_OUTPUT",
}, "network emergency accessibility")
if net:
    nonempty(net, "OUTPUT_ORIGINS", "network access")

print("=== 8 air quality ===")
air = run("air_quality_exposure_screening", {
    "STUDY_AREA": study, "ROADS": roads, "SENSITIVE": sensitive,
    "GREEN_BUFFERS": green, "CELL_SIZE": 100,
    "OUTPUT_GRID": "TEMPORARY_OUTPUT", "OUTPUT_EXPOSED": "TEMPORARY_OUTPUT",
}, "air quality exposure")
if air:
    nonempty(air, "OUTPUT_GRID", "air")

print("=== 9 drought ===")
dr = run("green_infrastructure_drought_stress", {
    "GREEN": green, "STUDY_AREA": study, "IMPERVIOUS": imperv, "WATER": water,
    "OUTPUT_STRESS": "TEMPORARY_OUTPUT", "OUTPUT_PRIORITY": "TEMPORARY_OUTPUT",
}, "drought stress")
if dr:
    nonempty(dr, "OUTPUT_STRESS", "drought")

print("=== 10 network criticality ===")
crit = run("network_criticality", {
    "ROADS": roads, "ORIGINS": buildings, "DESTINATIONS": shelters,
    "SNAP_TOLERANCE": 500.0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "network criticality")
if crit:
    nonempty(crit, "OUTPUT", "criticality")

print("=== 11 evacuation (instant) ===")
ev1 = run("evacuation_time_simulation", {
    "ROADS": roads, "ORIGINS": buildings, "POP_FIELD": "population",
    "SHELTERS": shelters, "CAPACITY_FIELD": "capacity",
    "ROAD_CAPACITY_FIELD": "capacity_ph", "ROAD_CLASS_FIELD": "class",
    "ROAD_DIRECTION_FIELD": "direction",
    "SPEED_KMH": 30.0, "TIMESTEP_MINUTES": 0.0, "SNAP_TOLERANCE": 500.0,
    "ASSIGN_ORDER": 0,
    "OUTPUT_ORIGINS": "TEMPORARY_OUTPUT", "OUTPUT_SHELTERS": "TEMPORARY_OUTPUT",
    "OUTPUT_EDGES": "TEMPORARY_OUTPUT",
}, "evacuation instant")
if ev1:
    nonempty(ev1, "OUTPUT_ORIGINS", "evac instant")

print("=== 12 evacuation (timestep queue) ===")
ev2 = run("evacuation_time_simulation", {
    "ROADS": roads, "ORIGINS": buildings, "POP_FIELD": "population",
    "SHELTERS": shelters, "CAPACITY_FIELD": "capacity",
    "ROAD_CLASS_FIELD": "class",
    "SPEED_KMH": 30.0, "TIMESTEP_MINUTES": 5.0, "MAX_TIMESTEPS": 24,
    "SNAP_TOLERANCE": 500.0, "ASSIGN_ORDER": 1,
    "OUTPUT_ORIGINS": "TEMPORARY_OUTPUT", "OUTPUT_SHELTERS": "TEMPORARY_OUTPUT",
    "OUTPUT_EDGES": "TEMPORARY_OUTPUT",
}, "evacuation timestep queue")
ev2_orig = nonempty(ev2, "OUTPUT_ORIGINS", "evac queue") if ev2 else None

print("=== 13 evacuation arrival summary ===")
if ev2_orig:
    arr = run("evacuation_shelter_arrival_summary", {
        "INPUT": ev2_orig, "SHELTER_FIELD": "evac_shelter", "POP_FIELD": "evac_pop",
        "TIMESTEP_FIELD": "evac_timestep", "MINUTES_FIELD": "evac_min",
        "MINUTE_BIN": 5,
        "OUTPUT_TABLE": "TEMPORARY_OUTPUT",
        "OUTPUT_HTML": os.path.join(TMP, "arrivals.html"),
    }, "evacuation arrival summary")
    if arr:
        nonempty(arr, "OUTPUT_TABLE", "arrival summary")

print("=== 14 seismic cascade ===")
casc = run("seismic_cascade_accessibility", {
    "ROADS": roads, "DEBRIS": imperv, "ORIGINS": buildings,
    "DESTINATIONS": shelters, "SNAP_TOLERANCE": 500.0,
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "seismic cascade")
if casc:
    nonempty(casc, "OUTPUT", "cascade")

print("=== 15 optimal shelter siting ===")
sit = run("optimal_shelter_siting", {
    "CANDIDATES": sensitive, "DEMAND": buildings, "POP_FIELD": "population",
    "MAX_DISTANCE": 1500.0, "NUM_SITES": 2, "OUTPUT": "TEMPORARY_OUTPUT",
}, "optimal shelter siting")
if sit:
    nonempty(sit, "OUTPUT", "siting")

print("=== 16 adaptation priority synthesis ===")
ad = run("climate_adaptation_priority_synthesis", {
    "UNITS": units, "HEAT_FIELD": "score", "FLOOD_FIELD": "score_b",
    "SOCIAL_FIELD": "svi", "OUTPUT": "TEMPORARY_OUTPUT",
}, "adaptation priority synthesis")
if ad:
    nonempty(ad, "OUTPUT", "adaptation")

print("=== 17 multi-hazard composite ===")
mh = run("multi_hazard_composite_index", {
    "INPUT": units, "HAZARD_FIELDS": ["score", "score_b"], "WEIGHTS": "0.6,0.4",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "multi-hazard composite")
if mh:
    nonempty(mh, "OUTPUT", "composite")

print("=== 18 equity adjusted priority ===")
eq = run("equity_adjusted_priority", {
    "INPUT": units, "HAZARD_FIELD": "score", "SVI_FIELD": "svi",
    "EQUITY_WEIGHT": 0.4, "OUTPUT": "TEMPORARY_OUTPUT",
}, "equity adjusted priority")
if eq:
    nonempty(eq, "OUTPUT", "equity")

print("=== 19 climate projection overlay ===")
cp = run("climate_projection_overlay", {
    "INPUT": units, "SCORE_FIELD": "score", "SCENARIO": 0,
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "climate projection overlay")
if cp:
    nonempty(cp, "OUTPUT", "projection")

print("=== 20 recovery capacity ===")
rc = run("recovery_capacity_index", {
    "INPUT": units, "DIVERSITY_FIELDS": ["score", "score_b"],
    "GREEN_FIELD": "svi", "OUTPUT": "TEMPORARY_OUTPUT",
}, "recovery capacity index")
if rc:
    nonempty(rc, "OUTPUT", "recovery")

print("=== 21 risk-recovery priority matrix ===")
rr = run("risk_recovery_priority_matrix", {
    "INPUT": units, "HAZARD_FIELD": "score", "RECOVERY_FIELD": "recovery",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "risk-recovery matrix")
if rr:
    nonempty(rr, "OUTPUT", "risk-recovery")

print("=== 22 join scores to units ===")
js = run("join_scores_to_planning_units", {
    "UNITS": social, "SOURCE1": units, "FIELD1": "score", "OUT1": "joined_score",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "join scores to units")
if js:
    lyr = nonempty(js, "OUTPUT", "join")
    if lyr:
        vals = [f["joined_score"] for f in lyr.getFeatures()]
        check(any(v is not None for v in vals), f"join: joined_score populated ({vals})")

print("=== 23 time series ===")
ts = run("resilience_time_series", {
    "EARLIER": units, "EARLIER_ID": "uid", "EARLIER_SCORE": "score",
    "LATER": units, "LATER_ID": "uid", "LATER_SCORE": "score_b",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "time series")
if ts:
    nonempty(ts, "OUTPUT", "time series")

print("=== 24 scenario sensitivity ===")
ss = run("scenario_sensitivity", {
    "INPUT": units, "COMPONENT_FIELDS": ["score", "score_b"],
    "WEIGHTS": "0.5,0.5", "PERTURB": 0.2, "SAMPLES": 50, "SEED": 7,
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "scenario sensitivity")
if ss:
    nonempty(ss, "OUTPUT", "sensitivity")

print("=== 25 scenario comparison ===")
sc = run("resilience_scenario_comparison", {
    "INPUT": units, "BASELINE_FIELD": "score", "SCENARIO_FIELD": "score_b",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "scenario comparison")
if sc:
    nonempty(sc, "OUTPUT", "comparison")

print("=== 26 scenario template ===")
st = run("scenario_planning_template", {
    "INPUT": units, "BASE_SCORE_FIELD": "score", "SCENARIO_NAME": "test",
    "INTERVENTION_TYPE": 0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "scenario template")
if st:
    nonempty(st, "OUTPUT", "template")

print("=== 27 html report ===")
hr = run("resilience_score_html_report", {
    "INPUT": units, "SCORE_FIELD": "score", "TITLE": "E2E",
    "OUTPUT_HTML": os.path.join(TMP, "report.html"),
}, "html report")
if hr:
    fexists(hr, "OUTPUT_HTML", "html report")

print("=== 28 studio brief ===")
sb = run("resilience_studio_brief_markdown", {
    "INPUT": units, "SCORE_FIELD": "score", "TITLE": "E2E",
    "OUTPUT_MD": os.path.join(TMP, "brief.md"),
}, "studio brief")
if sb:
    fexists(sb, "OUTPUT_MD", "studio brief")

print("=== 29 recommended actions ===")
ra = run("recommended_actions_report", {
    "INPUT": units, "SCORE_FIELD": "score", "TOP_N": 5,
    "OUTPUT": os.path.join(TMP, "actions.html"),
}, "recommended actions")
if ra:
    fexists(ra, "OUTPUT", "recommended actions")

print("=== 30 pdf atlas ===")
pa = run("resilience_pdf_atlas", {
    "INPUT": units, "SCORE_FIELD": "score", "TITLE": "E2E Atlas",
    "METHOD": 0, "ATLAS_PRESET": 0,
    "OUTPUT": os.path.join(TMP, "atlas.pdf"),
}, "pdf atlas")
if pa:
    fexists(pa, "OUTPUT", "pdf atlas", minsize=500)

print("=== 31 apply symbology ===")
sym = run("apply_resilience_symbology", {
    "LAYER": units, "FIELD": "score", "PRESET": 0, "REFRESH": False,
    "OUTPUT_QML": os.path.join(TMP, "style.qml"),
}, "apply symbology")
if sym:
    fexists(sym, "OUTPUT_QML", "symbology")

print("=== 32 bivariate symbology ===")
bv = run("bivariate_choropleth_symbology", {
    "INPUT": units, "RISK_FIELD": "score", "VULN_FIELD": "svi",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "bivariate symbology")
if bv:
    nonempty(bv, "OUTPUT", "bivariate")

# The renderer must reach the layer QGIS loads, for temporary AND file outputs:
# styling the context's layer during the run never reached a GeoPackage result.
for _kind in ("TEMPORARY_OUTPUT", os.path.join(TMP, "bivariate_styled.gpkg")):
    _before = set(QgsProject.instance().mapLayers())
    processing.runAndLoadResults(P + "bivariate_choropleth_symbology", {
        "INPUT": units, "RISK_FIELD": "score", "VULN_FIELD": "svi", "OUTPUT": _kind,
    })
    _new = [QgsProject.instance().mapLayer(i)
            for i in set(QgsProject.instance().mapLayers()) - _before]
    _r = _new[0].renderer() if _new else None
    check(_r is not None and _r.type() == "categorizedSymbol"
          and _r.classAttribute() == "bv_class" and len(_r.categories()) == 9,
          f"bivariate renderer survives load ({'gpkg' if _kind.endswith('.gpkg') else 'temporary'})")

print("=== 33 hotspot Gi* ===")
hs = run("hotspot_analysis_getis_ord", {
    "INPUT": units, "VALUE_FIELD": "score", "DISTANCE": 500.0,
    "WEIGHT_METHOD": 0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "hotspot Gi*")
if hs:
    lyr = nonempty(hs, "OUTPUT", "hotspot")
    if lyr:
        # NE-corner cluster cell must be a significant hot spot
        flds = [f.name() for f in lyr.fields()]
        zf = "gi_zscore" if "gi_zscore" in flds else None
        if zf:
            zmax = max(f[zf] for f in lyr.getFeatures() if f[zf] is not None)
            check(zmax > 1.95, f"hotspot: max Gi* z > 1.95 (got {zmax:.2f})")
        check("gi_p_fdr" in flds and "gi_class_fdr" in flds,
              f"hotspot: FDR fields present ({flds[-4:]})")

print("=== 34 LISA ===")
li = run("lisa_local_moran", {
    "INPUT": units, "VALUE_FIELD": "score", "DISTANCE": 500.0,
    "WEIGHT_METHOD": 0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "LISA local Moran")
if li:
    lyr = nonempty(li, "OUTPUT", "lisa")
    if lyr:
        quads = {f["lisa_quadrant"] for f in lyr.getFeatures()}
        check(any("HH" in str(q) or "High" in str(q) for q in quads),
              f"lisa: HH quadrant present ({quads})")
        check("Not significant" in quads,
              f"lisa: variance fix => some units NOT significant ({quads})")
        flds = [f.name() for f in lyr.fields()]
        check("lisa_p_fdr" in flds and "lisa_quad_fdr" in flds,
              "lisa: FDR fields present")

print("=== 35 population weighted exposure ===")
pw = run("population_weighted_exposure", {
    "INPUT": units, "SCORE_FIELD": "score", "POP_FIELD": "pop",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "population weighted exposure")
if pw:
    lyr = nonempty(pw, "OUTPUT", "popexp")
    if lyr:
        f1 = next(lyr.getFeatures())
        expect = f1["score"] / 100.0 * f1["pop"]
        check(abs(f1["pop_exposed"] - expect) < 1e-6,
              f"popexp: pop_exposed = score/100*pop ({f1['pop_exposed']} vs {expect})")

print("=== 36 cost benefit ===")
cb = run("cost_benefit_analyzer", {
    "INPUT": units, "SCORE_FIELD": "score", "UNIT_COST": 100.0,
    "POP_FIELD": "pop", "OUTPUT": "TEMPORARY_OUTPUT",
}, "cost benefit")
if cb:
    nonempty(cb, "OUTPUT", "cost benefit")

print("=== 37 critical infrastructure exposure ===")
ci = run("critical_infrastructure_exposure", {
    "HAZARD": units, "HAZARD_FIELD": "score", "FACILITIES": shelters,
    "CRITICALITY_DEFAULT": 60.0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "critical infrastructure")
if ci:
    nonempty(ci, "OUTPUT", "infra")

print("=== 38 risk 3d export ===")
r3 = run("risk_3d_volume_export", {
    "INPUT": units, "SCORE_FIELD": "score", "MAX_HEIGHT": 100.0,
    "COLOR_RAMP": 0,
    "OUTPUT_GEOJSON": os.path.join(TMP, "risk3d.geojson"),
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "risk 3d export")
if r3:
    fexists(r3, "OUTPUT_GEOJSON", "risk 3d")

print("=== 39 pareto ===")
po = run("pareto_optimal_selector", {
    "INPUT": units, "COST_FIELD": "cost", "BENEFIT_FIELD": "benefit",
    "OUTPUT": "TEMPORARY_OUTPUT",
}, "pareto selector")
if po:
    lyr = nonempty(po, "OUTPUT", "pareto")
    if lyr:
        # cost and benefit both rise with uid -> nothing dominates anything
        ranks = {f["pareto_rank"] for f in lyr.getFeatures()}
        check(ranks == {1}, f"pareto: frontier set => all rank 1 ({ranks})")

print("=== 40 hazard frequency ===")
hf = run("hazard_frequency_aggregation", {
    "UNITS": units, "SOURCES": [units, units], "SCORE_FIELD": "score",
    "THRESHOLD": 50.0, "AGG_MODE": 0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "hazard frequency")
if hf:
    nonempty(hf, "OUTPUT", "hazfreq")

print("=== 41 vulnerability surface IDW ===")
iw = run("vulnerability_surface_idw", {
    "POINTS": shelters, "VALUE_FIELD": "capacity", "STUDY": study,
    "CELL_SIZE": 200.0, "POWER": 2.0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "IDW surface")
if iw:
    nonempty(iw, "OUTPUT", "idw")

print("=== 42 correlation matrix ===")
cm = run("multi_hazard_correlation_matrix", {
    "INPUT": units, "FIELDS": ["score", "score_b", "recovery"],
    "PROJECT": "E2E",
    "OUTPUT_HTML": os.path.join(TMP, "corr.html"),
    "OUTPUT_TABLE": "TEMPORARY_OUTPUT",
}, "correlation matrix")
if cm:
    lyr = nonempty(cm, "OUTPUT_TABLE", "correlation")
    fexists(cm, "OUTPUT_HTML", "correlation")
    if lyr:
        for f in lyr.getFeatures():
            if {f["field_a"], f["field_b"]} == {"score", "recovery"}:
                check(abs(f["pearson_r"] + 1.0) < 1e-9,
                      f"corr: pearson(score, 100-score) == -1 (got {f['pearson_r']})")
                break

print("=== 43 risk trend hotspot ===")
rt = run("risk_trend_hotspot", {
    "INPUT": units, "LATER_SCORE": "score_b", "DELTA_FIELD": "delta",
    "DISTANCE": 500.0, "OUTPUT": "TEMPORARY_OUTPUT",
}, "risk trend hotspot")
if rt:
    nonempty(rt, "OUTPUT", "trend")

print("=== 44 lifecycle cost ===")
lc = run("lifecycle_cost_calculator", {
    "INPUT": units, "CAPEX_FIELD": "capex", "OPEX_FIELD": "opex",
    "MAINT_INTERVAL": 5, "MAINT_COST": 200.0, "REPL_YEARS": 20,
    "REPL_COST": 500.0, "HORIZON": 25, "DISCOUNT": 5.0,
    "AREA_SCALE": False, "OUTPUT": "TEMPORARY_OUTPUT",
}, "lifecycle cost")
if lc:
    lyr = nonempty(lc, "OUTPUT", "lifecycle")
    if lyr:
        f1 = next(lyr.getFeatures())
        opex_npv = sum(100.0 / (1.05 ** t) for t in range(1, 26))
        check(abs(f1["lc_opex_npv"] - opex_npv) < 1.0,
              f"lifecycle: opex NPV ~{opex_npv:.0f} (got {f1['lc_opex_npv']})")

print("=== 45 wildfire WUI exposure ===")
wui = run("wui_exposure_screening", {
    "STUDY_AREA": study, "VEGETATION": green, "BUILDINGS": buildings,
    "ROADS": roads, "DEM": dem, "CELL_SIZE": 100.0,
    "OUTPUT_GRID": "TEMPORARY_OUTPUT", "OUTPUT_PRIORITY": "TEMPORARY_OUTPUT",
    "OUTPUT_EXPOSED": "TEMPORARY_OUTPUT",
}, "wildfire WUI exposure")
if wui:
    nonempty(wui, "OUTPUT_GRID", "wui")

print("=== 46 coastal SLR exposure ===")
slr = run("coastal_slr_exposure", {
    "STUDY_AREA": study, "DEM": dem, "COASTLINE": water, "BUILDINGS": buildings,
    "ROADS": roads, "SCENARIO_PRESET": 1, "CELL_SIZE": 100.0,
    "OUTPUT_GRID": "TEMPORARY_OUTPUT", "OUTPUT_PRIORITY": "TEMPORARY_OUTPUT",
    "OUTPUT_EXPOSED": "TEMPORARY_OUTPUT",
}, "coastal SLR exposure")
if slr:
    nonempty(slr, "OUTPUT_GRID", "slr")

print()
print("=" * 60)
print(f"PASSED algorithms: {len(passed)}")
if fails:
    print(f"E2E QGIS: FAIL ({len(fails)})")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("E2E QGIS: PASS — all algorithms + assertions")
sys.exit(0)
