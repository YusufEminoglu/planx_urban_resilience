#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the Urban Resilience algorithm registry from the LIVE QGIS provider.

Run inside the QGIS Python environment::

    C:\\OSGeo4W\\bin\\python-qgis-ltr.bat manifest\\build_registry.py

Writes two files next to this script:

``algorithms.json``
    Lightweight registry: group -> ordered algorithm ids (used by the HTML
    sidebar and the cover index).

``algorithms_detailed.json``
    Full per-algorithm description: display name, group, help text, every
    input parameter (name / label / type / default / enum options /
    mandatory) and every output.  This is the single source of truth for the
    "Parameters & Outputs" tab of the Practical Guide.

Unlike PlanX's regex scrapers this introspects the actual provider, so the
ids, parameter names and defaults are the ones QGIS itself will use.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUIDE_DIR = HERE.parent
PLUGIN_ROOT = GUIDE_DIR.parent.parent.parent          # -> qgis_plugins/
sys.path.insert(0, str(PLUGIN_ROOT))

for _p in (r'C:\OSGeo4W\apps\qgis-ltr\python\plugins',
           r'C:\OSGeo4W\apps\qgis\python\plugins'):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
)

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
APP = QgsApplication([], False)
QgsApplication.initQgis()

from planx_urban_resilience.processing.urban_resilience_provider import (  # noqa: E402
    PlanXUrbanResilienceProvider,
)

provider = PlanXUrbanResilienceProvider()
QgsApplication.processingRegistry().addProvider(provider)
algos = list(provider.algorithms())
print(f"[OK] provider '{provider.id()}' -> {len(algos)} algorithms", flush=True)


def _default(prm):
    try:
        value = prm.defaultValue()
    except Exception:
        return None
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def _describe(prm):
    info = {
        "name": prm.name(),
        "label": prm.description(),
        "type": type(prm).__name__.replace("QgsProcessingParameter", ""),
        "default": _default(prm),
        "mandatory": bool(prm.flags() & getattr(prm, "FlagMandatory", 0)),
    }
    try:
        info["optional"] = bool(prm.flags() & getattr(prm, "FlagOptional", 0))
    except Exception:
        info["optional"] = False
    if isinstance(prm, QgsProcessingParameterEnum):
        info["options"] = list(prm.options())
    if isinstance(prm, QgsProcessingParameterField):
        try:
            info["parent"] = prm.parentLayerParameterName()
        except Exception:
            info["parent"] = ""
        info["data_type"] = "Numeric" if prm.dataType() == 0 else "Any"
    if isinstance(prm, QgsProcessingParameterNumber):
        info["data_type"] = ("Integer" if prm.dataType() == 0 else "Double")
    if isinstance(prm, QgsProcessingParameterFileDestination):
        try:
            info["extension"] = prm.defaultFileExtension()
        except Exception:
            info["extension"] = ""
    return info


algorithms = []
details = {}
groups = {}
group_order = {}

for algo in algos:
    aid = algo.id().split(":")[-1]
    grp = algo.group()
    params = []
    outputs = []
    for prm in algo.parameterDefinitions():
        info = _describe(prm)
        if isinstance(prm, (QgsProcessingParameterFeatureSink,
                            QgsProcessingParameterRasterDestination,
                            QgsProcessingParameterVectorDestination,
                            QgsProcessingParameterFileDestination)):
            info["kind"] = "output"
            outputs.append(info)
        else:
            info["kind"] = "input"
            params.append(info)
    help_text = ""
    try:
        help_text = algo.shortHelpString()
    except Exception:
        pass
    entry = {
        "algo_id": aid,
        "display_name": algo.displayName(),
        "group": grp,
        "group_id": algo.groupId(),
        "class_name": type(algo).__name__,
        "file": getattr(type(algo), "__module__", "").split(".")[-1] + ".py",
        "icon": getattr(type(algo), "ICON", ""),
        "help_summary": help_text,
        "parameters": params,
        "outputs": outputs,
    }
    algorithms.append(entry)
    details[aid] = entry
    groups.setdefault(grp, []).append(aid)

# group order follows the numeric prefix the suite uses ("0 - ...", "1 - ...")
def _grp_key(name):
    head = name.split("-")[0].strip()
    try:
        return (0, int(head))
    except ValueError:
        return (1, name)


ordered_groups = {}
for grp in sorted(groups, key=_grp_key):
    ordered_groups[grp] = groups[grp]

light = {
    "version": "1.0",
    "generated": __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
    "provider": provider.id(),
    "total_algorithms": len(algorithms),
    "groups": ordered_groups,
    "algorithms": [
        {"algo_id": a["algo_id"], "display_name": a["display_name"],
         "group": a["group"], "group_id": a["group_id"]}
        for a in algorithms
    ],
}

detailed = {
    "version": "1.0",
    "generated": light["generated"],
    "provider": provider.id(),
    "total_algorithms": len(algorithms),
    "groups": ordered_groups,
    "algorithms": light["algorithms"],
    "algo_details": details,
}

with open(HERE / "algorithms.json", "w", encoding="utf-8") as f:
    json.dump(light, f, indent=2, ensure_ascii=False)
with open(HERE / "algorithms_detailed.json", "w", encoding="utf-8") as f:
    json.dump(detailed, f, indent=2, ensure_ascii=False)

print(f"[OK] wrote algorithms.json ({len(algorithms)} algorithms, "
      f"{len(ordered_groups)} groups)", flush=True)
print(f"[OK] wrote algorithms_detailed.json", flush=True)
for grp, ids in ordered_groups.items():
    print(f"     - {grp}: {len(ids)}", flush=True)
