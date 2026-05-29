"""Smoke pipeline for PlanX Urban Resilience.

Run **inside the QGIS Python Console** after installing the plugin. The
script:

  1. Generates the synthetic dataset (no project layers needed).
  2. Runs Heat, Air, Social, Emergency (Euclidean), Network Emergency,
     Drought and Adaptation Priority Synthesis end-to-end using only
     the synthetic outputs as inputs.
  3. Prints PASS / FAIL per step.

Usage (QGIS Python Console):
    >>> exec(open(r"C:\\Users\\YE\\PyCharmMiscProject\\qgis_plugins\\planx_urban_resilience\\tests\\smoke_pipeline.py").read())

If a step fails, the console keeps going to surface the next failure.
This is a sanity check, not a unit-test rig.
"""
import processing
from qgis.core import QgsProject, QgsVectorLayer


def _ok(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}{(' - ' + detail) if detail else ''}")
    return cond


def _run(alg_id, params, label):
    try:
        result = processing.run(alg_id, params)
    except Exception as exc:
        _ok(label, False, f"run raised: {exc}")
        return None
    _ok(label, True, f"outputs: {list(result.keys())}")
    return result


def _add(result, key, layer_name):
    path = result.get(key) if result else None
    if not path:
        return None
    layer = QgsVectorLayer(path, layer_name, "ogr") if isinstance(path, str) else path
    if hasattr(layer, "isValid") and layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        return layer
    return path


def run_all():
    print("=" * 60)
    print(" PlanX Urban Resilience - smoke pipeline")
    print("=" * 60)

    # 1) Synthetic dataset
    syn = _run(
        "planx_urban_resilience:synthetic_resilience_demo_dataset",
        {"SCALE": 1.0, "SEED": 42,
         "STUDY_AREA": "memory:study", "BUILDINGS": "memory:buildings",
         "ROADS": "memory:roads", "IMPERVIOUS": "memory:impervious",
         "GREEN": "memory:green", "WATER": "memory:water",
         "SHELTERS": "memory:shelters", "SOCIAL_UNITS": "memory:social",
         "SENSITIVE": "memory:sensitive"},
        "synthetic dataset",
    )
    if not syn:
        print("Cannot continue — synthetic generation failed.")
        return False

    study     = syn.get("STUDY_AREA")
    buildings = syn.get("BUILDINGS")
    roads     = syn.get("ROADS")
    imperv    = syn.get("IMPERVIOUS")
    green     = syn.get("GREEN")
    water     = syn.get("WATER")
    shelters  = syn.get("SHELTERS")
    social    = syn.get("SOCIAL_UNITS")
    sensitive = syn.get("SENSITIVE")

    # 2) Heat
    _run(
        "planx_urban_resilience:urban_heat_comfort_risk",
        {"STUDY_AREA": study, "BUILDINGS": buildings, "IMPERVIOUS": imperv,
         "GREEN": green, "WATER": water, "VULNERABLE": sensitive,
         "CELL_SIZE": 50, "COOLING_DISTANCE": 200,
         "IMPERVIOUS_WEIGHT": 0.3, "GREEN_DEFICIT_WEIGHT": 0.3,
         "BUILDING_WEIGHT": 0.2, "VULNERABILITY_WEIGHT": 0.2,
         "OUTPUT_GRID": "memory:heat_grid",
         "OUTPUT_PRIORITY": "memory:heat_priority",
         "OUTPUT_EXPOSED": "memory:heat_exposed"},
        "heat comfort risk",
    )

    # 3) Air
    _run(
        "planx_urban_resilience:air_quality_exposure_screening",
        {"STUDY_AREA": study, "ROADS": roads, "SENSITIVE": sensitive,
         "GREEN_BUFFER": green, "CELL_SIZE": 50,
         "ROAD_WEIGHT": 0.5, "SOURCE_WEIGHT": 0.2, "SENSITIVE_WEIGHT": 0.3,
         "OUTPUT_GRID": "memory:air_grid", "OUTPUT_EXPOSED": "memory:air_exposed"},
        "air quality exposure",
    )

    # 4) Social
    _run(
        "planx_urban_resilience:social_vulnerability_index",
        {"AREAS": social,
         "POPULATION_FIELD": "population",
         "ELDERLY_FIELD": "elderly",
         "CHILDREN_FIELD": "children",
         "DISABILITY_FIELD": "disability",
         "LOW_INCOME_FIELD": "low_income",
         "OUTPUT": "memory:svi"},
        "social vulnerability index",
    )

    # 5) Emergency (Euclidean)
    _run(
        "planx_urban_resilience:emergency_accessibility_shelter_coverage",
        {"STUDY_AREA": study, "SHELTERS": shelters, "ASSETS": buildings,
         "CELL_SIZE": 50, "DEFICIT_THRESHOLD": 500,
         "OUTPUT_GRID": "memory:emg_grid",
         "OUTPUT_UNDERSERVED": "memory:emg_under"},
        "emergency accessibility (Euclidean)",
    )

    # 6) Network Emergency
    _run(
        "planx_urban_resilience:network_emergency_accessibility",
        {"ROADS": roads, "ORIGINS": buildings, "DESTINATIONS": shelters,
         "SPEED_KMH": 30.0, "SNAP_TOLERANCE": 500.0,
         "OUTPUT_ORIGINS": "memory:net_origins",
         "OUTPUT_UNDERSERVED": "memory:net_under"},
        "network emergency accessibility",
    )

    # 7) Drought
    _run(
        "planx_urban_resilience:green_infrastructure_drought_stress",
        {"GREEN": green, "IMPERVIOUS": imperv, "WATER": water,
         "OUTPUT_STRESS": "memory:drought", "OUTPUT_PRIORITY": "memory:drought_priority"},
        "green infrastructure drought stress",
    )

    # 8) Evacuation (instant greedy)
    _run(
        "planx_urban_resilience:evacuation_time_simulation",
        {"ROADS": roads, "ORIGINS": buildings, "POP_FIELD": "population",
         "SHELTERS": shelters, "CAPACITY_FIELD": "capacity",
         "ROAD_CAPACITY_FIELD": "capacity_ph", "ROAD_CLASS_FIELD": "class",
         "ROAD_DIRECTION_FIELD": "direction",
         "SPEED_KMH": 30.0, "TARGET_MINUTES": 15.0, "CRITICAL_MINUTES": 45.0,
         "TIMESTEP_MINUTES": 0.0, "MAX_TIMESTEPS": 48,
         "SNAP_TOLERANCE": 500.0, "ASSIGN_ORDER": 0,
         "OUTPUT_ORIGINS": "memory:evac_origins",
         "OUTPUT_SHELTERS": "memory:evac_shelters",
         "OUTPUT_EDGES": "memory:evac_edges"},
        "evacuation (instant)",
    )

    # 9) Evacuation (timestep queue)
    evac_q = _run(
        "planx_urban_resilience:evacuation_time_simulation",
        {"ROADS": roads, "ORIGINS": buildings, "POP_FIELD": "population",
         "SHELTERS": shelters, "CAPACITY_FIELD": "capacity",
         "ROAD_CLASS_FIELD": "class",
         "SPEED_KMH": 30.0, "TIMESTEP_MINUTES": 5.0, "MAX_TIMESTEPS": 24,
         "SNAP_TOLERANCE": 500.0, "ASSIGN_ORDER": 1,
         "OUTPUT_ORIGINS": "memory:evac_q_origins",
         "OUTPUT_SHELTERS": "memory:evac_q_shelters",
         "OUTPUT_EDGES": "memory:evac_q_edges"},
        "evacuation (timestep queue)",
    )

    evac_q_origins = evac_q.get("OUTPUT_ORIGINS") if evac_q else None

    # 10) Shelter arrival summary (from queue evacuation output)
    _run(
        "planx_urban_resilience:evacuation_shelter_arrival_summary",
        {"INPUT": evac_q_origins,
         "SHELTER_FIELD": "evac_shelter", "POP_FIELD": "evac_pop",
         "TIMESTEP_FIELD": "evac_timestep", "MINUTES_FIELD": "evac_min",
         "MINUTE_BIN": 5,
         "OUTPUT_TABLE": "memory:arrival_table"},
        "evacuation shelter arrival summary",
    )

    print("-" * 60)
    print("  Smoke pipeline finished.")
    return True


if __name__ == "__main__":
    run_all()
else:
    run_all()
