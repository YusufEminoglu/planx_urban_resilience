# -*- coding: utf-8 -*-
"""Best-effort QGIS runtime smoke test for PlanX Urban Resilience.

Run inside QGIS Python Console:

    exec(open(r"C:\\path\\to\\planx_urban_resilience\\tools\\qgis_synthetic_smoke.py", encoding="utf-8").read())

The script generates synthetic layers, then runs the modules that do not require
an external DEM or pre-joined synthesis layer.
"""
from __future__ import annotations

import sys
import traceback


try:
    import processing
    from qgis.core import QgsProcessingContext, QgsProcessingFeedback, QgsProcessingUtils
except Exception as exc:  # pragma: no cover - designed for QGIS runtime.
    print("QGIS runtime is not available:", exc)
    sys.exit(0)


ALG = "planx_urban_resilience:"
TEMP = "TEMPORARY_OUTPUT"


def _layer(result, key, context):
    value = result.get(key)
    if hasattr(value, "getFeatures"):
        return value
    return QgsProcessingUtils.mapLayerFromString(str(value), context)


def _run(name, params, context, feedback):
    print(f"Running {name}...")
    result = processing.run(ALG + name, params, context=context, feedback=feedback, is_child_algorithm=False)
    print(f"  ok: {', '.join(result.keys())}")
    return result


def main():
    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()
    failures = []

    demo_params = {
        "SCALE": 1.0,
        "STUDY_AREA": TEMP,
        "BUILDINGS": TEMP,
        "ROADS": TEMP,
        "IMPERVIOUS": TEMP,
        "GREEN": TEMP,
        "WATER": TEMP,
        "SHELTERS": TEMP,
        "SOCIAL_UNITS": TEMP,
        "SENSITIVE": TEMP,
    }

    try:
        demo = _run("synthetic_resilience_demo_dataset", demo_params, context, feedback)
        study = _layer(demo, "STUDY_AREA", context)
        buildings = _layer(demo, "BUILDINGS", context)
        roads = _layer(demo, "ROADS", context)
        impervious = _layer(demo, "IMPERVIOUS", context)
        green = _layer(demo, "GREEN", context)
        water = _layer(demo, "WATER", context)
        shelters = _layer(demo, "SHELTERS", context)
        social = _layer(demo, "SOCIAL_UNITS", context)
        sensitive = _layer(demo, "SENSITIVE", context)

        tests = [
            (
                "urban_heat_comfort_risk",
                {
                    "STUDY_AREA": study,
                    "BUILDINGS": buildings,
                    "IMPERVIOUS": impervious,
                    "GREEN": green,
                    "WATER": water,
                    "VULNERABLE": sensitive,
                    "CELL_SIZE": 200.0,
                    "COOLING_DISTANCE": 400.0,
                    "IMPERVIOUS_WEIGHT": 0.30,
                    "GREEN_DEFICIT_WEIGHT": 0.30,
                    "BUILDING_WEIGHT": 0.25,
                    "VULNERABILITY_WEIGHT": 0.15,
                    "OUTPUT_GRID": TEMP,
                    "OUTPUT_PRIORITY": TEMP,
                    "OUTPUT_EXPOSED": TEMP,
                },
            ),
            (
                "air_quality_exposure_screening",
                {
                    "STUDY_AREA": study,
                    "ROADS": roads,
                    "EMISSION_SOURCES": buildings,
                    "SENSITIVE": sensitive,
                    "GREEN_BUFFERS": green,
                    "CELL_SIZE": 200.0,
                    "ROAD_DISTANCE": 300.0,
                    "SOURCE_DISTANCE": 600.0,
                    "ROAD_WEIGHT": 0.35,
                    "SOURCE_WEIGHT": 0.25,
                    "SENSITIVE_WEIGHT": 0.25,
                    "BUFFER_WEIGHT": 0.15,
                    "OUTPUT_GRID": TEMP,
                    "OUTPUT_EXPOSED": TEMP,
                },
            ),
            (
                "social_vulnerability_index",
                {
                    "AREAS": social,
                    "POPULATION_FIELD": "population",
                    "ELDERLY_FIELD": "elderly",
                    "CHILDREN_FIELD": "children",
                    "DISABILITY_FIELD": "disability",
                    "LOW_INCOME_FIELD": "low_income",
                    "WEIGHT_ELDERLY": 0.25,
                    "WEIGHT_CHILDREN": 0.15,
                    "WEIGHT_DISABILITY": 0.20,
                    "WEIGHT_LOW_INCOME": 0.25,
                    "WEIGHT_DENSITY": 0.15,
                    "OUTPUT": TEMP,
                },
            ),
            (
                "emergency_accessibility_shelter_coverage",
                {
                    "STUDY_AREA": study,
                    "SHELTERS": shelters,
                    "POPULATION_ASSETS": buildings,
                    "BARRIERS": impervious,
                    "CELL_SIZE": 200.0,
                    "SERVICE_DISTANCE": 500.0,
                    "CRITICAL_DISTANCE": 1200.0,
                    "BARRIER_WEIGHT": 25.0,
                    "OUTPUT_GRID": TEMP,
                    "OUTPUT_UNDERSERVED": TEMP,
                },
            ),
            (
                "green_infrastructure_drought_stress",
                {
                    "GREEN": green,
                    "STUDY_AREA": study,
                    "IMPERVIOUS": impervious,
                    "WATER": water,
                    "TREES": sensitive,
                    "MAX_WATER_DISTANCE": 500.0,
                    "IMPERVIOUS_WEIGHT": 0.35,
                    "WATER_WEIGHT": 0.25,
                    "SIZE_WEIGHT": 0.25,
                    "TREE_WEIGHT": 0.15,
                    "OUTPUT_STRESS": TEMP,
                    "OUTPUT_PRIORITY": TEMP,
                },
            ),
        ]

        for name, params in tests:
            try:
                _run(name, params, context, feedback)
            except Exception:
                failures.append(name)
                traceback.print_exc()

    except Exception:
        failures.append("synthetic_resilience_demo_dataset")
        traceback.print_exc()

    if failures:
        print("Synthetic smoke test completed with failures:", ", ".join(failures))
        raise SystemExit(1)

    print("Synthetic smoke test completed successfully.")
    print("Skipped by design: pluvial flood needs a DEM; synthesis needs a joined risk layer.")


if __name__ == "__main__":
    main()
