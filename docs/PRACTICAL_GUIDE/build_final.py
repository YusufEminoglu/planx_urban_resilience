#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the PlanX Urban Resilience Practical Guide (interactive, self-contained).

Inputs
------
``manifest/algorithms_detailed.json``  live registry (ids, help, parameters, outputs)
``manifest/screenshots_all.json``      what the runner produced, and with which values
``screenshots/<algo_id>/<algo_id>_4panel.png``

Output
------
``practical_guide.html``  one file with the registry, the parameters and every
                          screenshot inlined as base64 - it opens from disk,
                                          needs no server and no network.

    python build_final.py
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from pathlib import Path

GUIDE = Path(__file__).resolve().parent
SHOT = GUIDE / "screenshots"
MAN = GUIDE / "manifest"

with open(MAN / "algorithms_detailed.json", encoding="utf-8") as f:
    registry = json.load(f)
with open(MAN / "screenshots_all.json", encoding="utf-8") as f:
    run_summary = json.load(f)

results = run_summary.get("results", {})
details = registry.get("algo_details", {})
groups_map = registry.get("groups", {})

# ---------------------------------------------------------------- helpers
_SECTION_SPLIT = re.compile(
    r"(How to read the results|Using the results|Interpretation)", re.I)


def _clean_html(text: str) -> str:
    """Turn the algorithm help HTML into readable plain text."""
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|table)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'")
            .replace("&ndash;", "-").replace("&mdash;", "-"))
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def split_sections(help_text: str):
    """Split the tool's own help into (theory, how-to-read, how-to-use)."""
    plain = _clean_html(help_text)
    if not plain:
        return "", "", ""
    marks = [(m.start(), m.group(1).lower()) for m in _SECTION_SPLIT.finditer(plain)]
    if not marks:
        return plain, "", ""
    theory = plain[:marks[0][0]].strip()
    buckets = {"how to read the results": [], "using the results": [],
               "interpretation": []}
    for idx, (start, kind) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(plain)
        buckets[kind].append(plain[start + len(kind):end].strip())
    how_read = "\n\n".join(buckets["how to read the results"]).strip()
    how_use = "\n\n".join(buckets["using the results"]).strip()
    if not how_use:
        how_use = "\n\n".join(buckets["interpretation"]).strip()
    # the help text writes "Using the results: ..." - drop the dangling colon
    how_use = how_use.lstrip(": ").lstrip()
    how_read = how_read.lstrip(": ").lstrip()
    return theory, how_read, how_use


def b64(path: Path):
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None


# ------------------------------------------------- per-group workflow steps
GROUP_STEPS = {
    "0 - Demo and QA": [
        "Run this FIRST on a clean install. It writes the nine layers every other "
        "tool in the suite expects: study area, buildings, roads, impervious surfaces, "
        "green infrastructure, water, shelters, social units and sensitive receptors.",
        "Open each of the nine outputs and confirm the field names - floor_count, "
        "year, population on the buildings; class, capacity_ph, direction on the roads; "
        "population, elderly, children, disability, low_income on the social units.",
        "Treat it as a regression fixture: the same SCALE always produces byte-identical "
        "geometry, so a change in a downstream result is a change in the code, not in "
        "the data.",
        "Never publish anything derived from it - the attribute values are hand-picked "
        "plausible numbers, not observations.",
    ],
    "1 - Seismic: Debris and Logistics": [
        "Start with the Monte Carlo debris run: give it buildings (floor_count + year) "
        "and land parcels. The year field is what drives the fragility band, so it is "
        "not optional in practice.",
        "Read the VULNERABILITY output first: collapse_prob, collapsed, debris_radius_m "
        "and debris_vol_m3 tell you what the simulation drew. debris_vol_m3 comes from "
        "footprint x height x solid volume ratio.",
        "The HAZARD MODEL output is the dissolved debris envelope of every collapsed "
        "building; the CUMULATIVE BLOCKAGE output is the part of that envelope which "
        "actually falls on the open network.",
        "Feed the HAZARD MODEL output straight into Seismic Cascade as the DEBRIS "
        "layer to see which origins lose their route.",
        "Re-run with a different SEED to sample another stochastic realisation of the "
        "same magnitude; re-run with the same SEED to reproduce one exactly.",
    ],
    "2 - Heat: Comfort and Exposure": [
        "Give the tool a study area and a buildings layer; the more context you add "
        "(impervious surfaces, green, water, vulnerable areas) the more of the heat "
        "score is explained rather than assumed.",
        "COOLING_DISTANCE is the radius at which a water or green feature cools its "
        "surroundings. Too small and the blue corridor does nothing; too large and "
        "everywhere is 'cool'.",
        "Read OUTPUT_GRID for the spatial pattern and OUTPUT_EXPOSED for the assets "
        "that sit in the hot cells - the second one is what a planning report quotes.",
        "The four weights sum to 1; raise IMPERVIOUS_WEIGHT for a dense-city question, "
        "VULNERABILITY_WEIGHT for an equity question.",
    ],
    "3 - Flood & Coastal: Pluvial and SLR Susceptibility": [
        "The DEM is mandatory for both tools and must cover the whole study area - "
        "both of them sample it at cell level and clamp to the raster extent.",
        "For pluvial flood, DRAINAGE is optional but strongly recommended: without it "
        "the drainage term is a neutral 50, not zero. Use a stream or storm-water line.",
        "NEIGHBORHOOD is the radius of the four-point local-relief sample. Too small "
        "and every cell looks flat; too large and the score smears over the whole area.",
        "For coastal SLR, the coastline layer is what seeds the hydrological "
        "connectivity flood fill. A cell is only 'priority' if the water can reach it "
        "from the sea - an inland pit below sea level stays a disconnected sink.",
        "Raise SCENARIO_PRESET before touching WATER_LEVEL_M: the preset is the "
        "IPCC-aligned scenario, the override is for your own datum.",
    ],
    "4 - Social: Vulnerability and Equity": [
        "The AREAS layer should be your social units (neighbourhoods, wards, blocks) "
        "- not individual buildings. The index is an area-level composite.",
        "All five indicator fields are optional, but every field you leave empty is "
        "dropped and the remaining weights are renormalised. data_flags records which.",
        "The result is a 0-100 svi_score with an svi_class; keep it as a separate "
        "layer rather than dissolving it into the hazard grid.",
        "This is the layer that turns a hazard map into an equity argument - join it "
        "to any hazard output before writing the report.",
    ],
    "5 - Emergency: Accessibility and Coverage": [
        "Use a NODED road network. The emergency tools build their graph from line "
        "vertices, so streets that cross without a shared vertex come out as "
        "disconnected components and most origins read as 'Unreachable'.",
        "Keep every street vertex on a regular lattice and set SNAP_TOLERANCE to that "
        "lattice: the tolerance quantises the node coordinates, so a tolerance that "
        "does not match the network rounds the distances.",
        "Distances are measured to the nearest graph NODE, not to the nearest street "
        "edge - so place the network so it runs along the frontage of the buildings "
        "you want to serve.",
        "Always read qa_flag: 'not_connected' means the origin never reached the "
        "network, 'large_snap_distance' means the snap distance exceeded five times "
        "the tolerance and the number is not trustworthy.",
        "Evacuation Time Simulation adds capacity: it assigns people to shelters in "
        "order of distance (or population) and stops when a shelter is full. The "
        "'Unassigned' class is the real finding - shelter capacity, not distance, is "
        "usually the binding constraint.",
    ],
    "6 - Air: Exposure Screening": [
        "ROADS is required; everything else adds a term. With only roads, the score "
        "measures proximity to traffic, which is still a useful screening question.",
        "EMISSION_SOURCES, SENSITIVE and GREEN_BUFFERS each carry a weight; the four "
        "weights are normalised, so you can raise one without touching the others.",
        "The result is a screening surface, not a concentration field: it says where "
        "exposure conditions stack up, not how many micrograms per cubic metre.",
        "Cross-reference OUTPUT_EXPOSED with the social vulnerability layer before "
        "publishing - that pairing is the whole point of the tool.",
    ],
    "7 - Drought & Wildfire: Green and WUI Stress": [
        "Green Infrastructure Stress works on green assets, not on the whole city: "
        "the score describes how exposed each green area is to drought stress.",
        "SIZE_WEIGHT rewards larger parks (they hold more water), TREE_WEIGHT rewards "
        "the presence of trees. Supply a tree point layer to activate the second term.",
        "WUI Exposure needs a VEGETATION polygon layer - the wildland side of the "
        "interface. The DEM is optional but adds a slope term to the wildfire score.",
        "Read the WUI score per structure, not per cell: the tool counts how many "
        "buildings sit in each WUI cell so the intervention can be targeted.",
    ],
    "8 - Synthesis: Adaptation Priorities": [
        "This is where the hazard modules become a decision. Run the hazard tools "
        "first, join their scores onto your planning units, then synthesise.",
        "Join Scores To Planning Units takes the MAXIMUM intersecting score per unit "
        "for up to five score layers at a time; run it twice to combine more.",
        "Every field the synthesis tools read is optional. A missing field is reported "
        "in the 'missing' column - check it, because a synthesis run with three of "
        "eight drivers is a different map than it looks.",
        "Climate Adaptation Priority Synthesis is the master tool: it takes one field "
        "per hazard domain and returns a single adapt_score, a class and the drivers "
        "that produced it.",
        "The statistical tools (Getis-Ord, LISA) are not decoration: they tell you "
        "whether the high scores are spatially clustered or evenly spread, which "
        "changes the intervention from 'everywhere' to 'these places'.",
    ],
    "9 - Report and QA": [
        "Every reporting tool reads a scored layer and a score field. Get the field "
        "name from the previous step - do not guess.",
        "Apply Resilience Symbology styles a layer IN PLACE. Run it on the layer in "
        "your project, not on a copy, and it changes how the layer looks everywhere.",
        "The four presets only work with the values the suite produces: 0-100 for the "
        "risk score, and the exact class labels (Covered / Watch / Underserved / "
        "Critical / Unreachable) for the others.",
        "Resilience PDF Atlas renders a print atlas at 150 or 200 dpi. Set METHOD to "
        "quantile when the distribution is skewed - equal interval over-represents "
        "the empty cells.",
        "Risk 3D Volume Export writes a GeoJSON ready for PlanX 3D City: the "
        "extrusion height is the score scaled to MAX_HEIGHT.",
    ],
}

#: per-algorithm reading notes: what the result fields mean and how not to
#: over-read them. Every tool has one, so no page ends in a bare screenshot.
EXTRA_NOTES = {
    "synthetic_resilience_demo_dataset":
        "The nine layers are a regression fixture, not observations: the same SCALE "
        "always reproduces byte-identical geometry, and every attribute value is a "
        "hand-picked plausible number. Never publish anything derived from it.",
    "urban_heat_comfort_risk":
        "heat_score is a 0-100 composite, not a temperature: read it as a relative "
        "ranking of cells within this run only.",
    "pluvial_flood_susceptibility":
        "flood_score >= 75 marks the classic floodplain floor. drain_dist = -1 means "
        "no DRAINAGE layer was supplied, so that term is neutral rather than zero.",
    "coastal_slr_exposure":
        "OUTPUT_PRIORITY only contains cells the sea can actually reach. A low-lying "
        "inland pocket appears in OUTPUT_GRID with connected = 0 and is a sink, not a "
        "coastal inundation cell.",
    "social_vulnerability_index":
        "svi_score is an area-level index, so it is only meaningful on units of a "
        "comparable size. data_flags names the indicators that were missing, and a "
        "missing indicator silently renormalises the remaining weights.",
    "seismic_debris_monte_carlo":
        "collapse_prob is the fragility probability; 'collapsed' is the single Monte "
        "Carlo draw. Only collapsed buildings contribute debris, so the debris "
        "volume is a realisation, not an expectation - re-run with a different SEED "
        "to see the spread.",
    "emergency_accessibility_shelter_coverage":
        "This is Euclidean distance to the nearest shelter, not a network route. "
        "Use it for a first screen and Network Emergency Accessibility for the "
        "walking-distance answer.",
    "network_emergency_accessibility":
        "access_cls comes from the travel time you set as the threshold, so the "
        "classification is relative to your own parameters, not an absolute "
        "standard. qa_flag warns when the snap distance is too large to trust.",
    "network_criticality":
        "criticality_score is an edge-betweenness proxy: 100 means the segment is "
        "on every origin-destination path. It is a relative ranking within one run, "
        "not a traffic count.",
    "evacuation_time_simulation":
        "Read OUTPUT_SHELTERS first: cap_pct tells you how full each shelter got. "
        "Origins left Unassigned ran out of shelter capacity, not out of time.",
    "seismic_cascade_accessibility":
        "cas_status is the result: 'Newly cut off' means the debris severed a route "
        "that existed before the earthquake, 'Recovered' the opposite. cas_delta_dist "
        "is the extra metres a survivor now has to walk.",
    "optimal_shelter_siting":
        "oss_pop_added is the population each new site covers that no other site "
        "covered - the marginal gain, in the order the greedy algorithm picked them.",
    "evacuation_shelter_arrival_summary":
        "The table is a cumulative arrival curve per shelter. pct_total is the share "
        "of the whole assigned population, so a shelter at 60% means most people "
        "still have to travel further.",
    "air_quality_exposure_screening":
        "air_score is a screening surface, not a concentration field: it says where "
        "exposure conditions stack up, never how many micrograms per cubic metre.",
    "green_infrastructure_drought_stress":
        "stress_score describes each green asset's exposure, so it is read per park, "
        "not per hectare. OUTPUT_PRIORITY keeps only the assets that cross the "
        "intervention threshold.",
    "wui_exposure_screening":
        "Read the WUI score per structure, not per cell: wui_bldg_n counts how many "
        "buildings sit in each interface cell, which is what the intervention "
        "targets.",
    "join_scores_to_planning_units":
        "Each joined field is the MAXIMUM intersecting score of its source layer, so "
        "a unit inherits the worst cell it touches. That is deliberate - it keeps a "
        "single hot cell from disappearing inside a large unit.",
    "multi_hazard_composite_index":
        "mh_score is the weighted sum of the normalised hazard fields. mh_dominant "
        "names the driver that contributed most and mh_diversity says how many "
        "drivers were actually above their threshold.",
    "equity_adjusted_priority":
        "eq_factor is the equity multiplier applied to the hazard score: a high "
        "eq_factor means the unit is both risky and vulnerable. eq_adjusted_score is "
        "the number to rank on.",
    "climate_adaptation_priority_synthesis":
        "adapt_score is a weighted sum of normalised drivers. Read the 'drivers' "
        "column to know WHICH hazard pushed a unit up, and 'missing' to see whether "
        "a driver was actually available.",
    "climate_projection_overlay":
        "cp_projected is the scenario score, cp_delta the change from today. The "
        "factor is a single scalar per scenario, so this is a sensitivity test, not "
        "a climate simulation.",
    "recovery_capacity_index":
        "rc_score combines diversity, redundancy, green and cohesion. rc_data_gap "
        "flags the components that were unavailable - a low score with a large gap "
        "means 'not measured', not 'not resilient'.",
    "risk_recovery_priority_matrix":
        "rr_deficit is the gap between hazard and recovery. The priority class is "
        "driven by that deficit, so a high-hazard but high-recovery area is not the "
        "same problem as a high-hazard low-recovery one.",
    "hotspot_analysis_getis_ord":
        "gi_zscore above +1.96 marks a statistically significant hot spot at the 95% "
        "level. The FDR column is the stricter, multiple-testing-corrected version.",
    "lisa_local_moran":
        "The quadrant is the whole result: High-High is a hot spot, Low-Low a cold "
        "spot, High-Low and Low-High are outliers. 'Not significant' is a real answer.",
    "population_weighted_exposure":
        "pop_exposed is the population living in the exposed fraction of a unit. It "
        "is the number that turns a hazard map into a planning argument.",
    "hazard_frequency_aggregation":
        "hf_frequency is how many of the periods exceeded the threshold - a "
        "recurrence measure, not a severity one. hf_composite combines the two.",
    "vulnerability_surface_idw":
        "vs_value is the inverse-distance-weighted value of the sample points; it "
        "is an interpolation, so it says nothing outside the convex hull of the "
        "samples. vs_n_points tells you how many samples backed each cell.",
    "critical_infrastructure_exposure":
        "ci_combined multiplies hazard by criticality. A low-hazard hospital still "
        "outranks a high-hazard unstaffed shed - that is the point of the "
        "criticality field.",
    "scenario_sensitivity":
        "ss_p05 and ss_p95 are the 5th and 95th percentile of the perturbed runs. "
        "ss_stability is the ratio of the spread to the baseline: a high value means "
        "the result is an artefact of the weights.",
    "risk_trend_hotspot":
        "trh_label combines the trend with the cluster test: 'Increasing hot spot' "
        "is a different finding from 'Decreasing hot spot'.",
    "cost_benefit_analyzer":
        "cb_ratio is benefit per unit cost, so it ranks interventions - but it is "
        "only as good as UNIT_COST and DEFAULT_REDUCTION, both of which you set.",
    "pareto_optimal_selector":
        "pareto_rank 1 marks the efficient frontier. A dominated option is not "
        "wrong, it is simply beaten on both cost and benefit by another option.",
    "lifecycle_cost_calculator":
        "lc_total_npv discounts every component to present value. AREA_SCALE turns "
        "the per-unit costs into per-area costs, so do not mix the two in one "
        "comparison.",
    "resilience_time_series":
        "ts_delta is the change between the two snapshots and ts_target_gap is what "
        "is left to reach the target. ts_trend is the direction, not the size.",
    "resilience_scenario_comparison":
        "pct_change is the relative move from the baseline. action_hint is a "
        "suggestion, not a decision - it does not know your budget.",
    "scenario_planning_template":
        "This tool produces a WORKING TEMPLATE, not an analysis: scen_score is the "
        "baseline minus the reduction you claim. The point is to hand a table to the "
        "team that then edits it.",
    "resilience_score_html_report":
        "The report is generated from the layer you pass, so its class distribution "
        "and driver breakdown are only as good as that layer. It states the tool is "
        "a screening summary - keep that caveat in your own report.",
    "resilience_studio_brief_markdown":
        "A short narrative brief for a planning meeting. It restates the layer, it "
        "does not add analysis.",
    "recommended_actions_report":
        "TOP_N controls how many units the report names. The action text is derived "
        "from the class and driver fields, so it is as good as the class vocabulary "
        "of the layer you passed.",
    "apply_resilience_symbology":
        "This tool produces no new layer - its output is the style applied to the "
        "layer you selected, plus an optional QML file you can reuse.",
    "bivariate_choropleth_symbology":
        "The 3x3 matrix needs comparable units: put risk and vulnerability on a "
        "common scale before trusting the corner you land in.",
    "resilience_pdf_atlas":
        "The atlas is a screening document. The subtitle it carries should say so "
        "in your own project, because a printed atlas outlives the caveat.",
    "multi_hazard_correlation_matrix":
        "pearson_r is linear, spearman_r is rank-based. They answer different "
        "questions: a high spearman with a low pearson means a non-linear "
        "relationship. n_pairs tells you how much of the layer was actually used.",
    "risk_3d_volume_export":
        "extrusion_height is the score scaled to MAX_HEIGHT, so the massing encodes "
        "risk, not building height. Use BASE_HEIGHT_FIELD if you want the real "
        "height with risk as colour.",
}


# ------------------------------------------------------------------- build
def build():
    data = {}
    for aid, det in details.items():
        run = results.get(aid, {})
        png = SHOT / aid / f"{aid}_4panel.png"
        theory, how_read, how_use = split_sections(det.get("help_summary", ""))
        entry = {
            "algo_id": aid,
            "display_name": det.get("display_name", aid),
            "group": det.get("group", ""),
            "group_id": det.get("group_id", ""),
            "icon": det.get("icon", ""),
            "help_summary": det.get("help_summary", ""),
            "theory": theory,
            "how_read": how_read,
            "how_use": how_use,
            "note": EXTRA_NOTES.get(aid, ""),
            "params": det.get("parameters", []),
            "outputs": det.get("outputs", []),
            "run_params": run.get("params", {}),
            "seconds": run.get("seconds"),
            "png_b64": b64(png),
            "ok": bool(run.get("ok")),
        }
        data[aid] = entry

    groups = []
    for order, (gname, ids) in enumerate(groups_map.items()):
        groups.append({
            "order": order,
            "name": gname,
            "algos": [i for i in ids if i in data],
            "steps": GROUP_STEPS.get(gname, []),
        })

    ok_count = sum(1 for v in data.values() if v["ok"])
    meta = {
        "generated": date.today().isoformat(),
        "total": len(data),
        "ok": ok_count,
        "failed": len(data) - ok_count,
        "provider": registry.get("provider", "planx_urban_resilience"),
        "qgis": run_summary.get("generated", ""),
    }

    js = JS.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    js = js.replace("__GROUPS__", json.dumps(groups, ensure_ascii=False))

    html = (PAGE
            .replace("__CSS__", CSS)
            .replace("__JS__", js)
            .replace("__META__", json.dumps(meta, ensure_ascii=False)))

    out = GUIDE / "practical_guide.html"
    out.write_text(html, encoding="utf-8")
    print(f"[OK] {out.name}: {out.stat().st_size / 1024:.0f} kB, "
          f"{len(data)} algorithms, {ok_count} with screenshots")
    return 0


CSS = """
:root{
  --bg:#ffffff; --fg:#1b1f1e; --muted:#5b6b68; --accent:#0d9488;
  --accent-dark:#0b6b60; --accent-light:#e6f6f4; --border:#d9e3e1;
  --code-bg:#f4f8f7; --sidebar-bg:#f0f5f4; --sidebar-fg:#2b3533;
  --sidebar-active:#dff1ee; --table-stripe:#f8fbfa; --tab-bg:#f4f8f7;
  --shadow:0 1px 3px rgba(16,40,36,.08); --radius:8px;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#101917; --fg:#e4ecea; --muted:#9db0ac; --accent:#2dd4bf;
    --accent-dark:#5eead4; --accent-light:#16302c; --border:#243633;
    --code-bg:#16211f; --sidebar-bg:#121d1b; --sidebar-fg:#dbe7e4;
    --sidebar-active:#1c3a35; --table-stripe:#141f1d; --tab-bg:#16211f;
    --shadow:0 1px 3px rgba(0,0,0,.4);}
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--fg);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px;line-height:1.6;display:flex;min-height:100vh}
a{color:var(--accent-dark)}
code{font-family:var(--mono);font-size:.88em;background:var(--code-bg);
  padding:.1em .35em;border-radius:4px}
#sidebar{width:320px;flex:0 0 320px;background:var(--sidebar-bg);
  border-right:1px solid var(--border);height:100vh;position:sticky;top:0;
  display:flex;flex-direction:column;overflow:hidden}
#sidebar-header{padding:18px 18px 12px;border-bottom:1px solid var(--border)}
#sidebar-header .logo{display:block;font-weight:700;font-size:17px;
  color:var(--accent-dark);letter-spacing:-.01em}
#sidebar-header .subtitle{display:block;font-size:12px;color:var(--muted);margin-top:3px}
#search-wrap{padding:12px 14px 8px}
#search{width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;
  background:var(--bg);color:var(--fg);font-size:13px}
#search:focus{outline:2px solid var(--accent);outline-offset:-1px}
#toc{flex:1;overflow-y:auto;padding:0 8px 20px;margin:0;list-style:none}
.toc-group{margin:0 0 4px}
.toc-group-btn{width:100%;text-align:left;background:none;border:0;border-left:4px solid var(--accent);
  color:var(--sidebar-fg);font:inherit;font-size:12.5px;font-weight:600;padding:7px 8px;
  cursor:pointer;border-radius:0 4px 4px 0;letter-spacing:.01em}
.toc-group-btn:hover{background:var(--accent-light)}
.toc-group-btn .arrow{display:inline-block;width:12px;color:var(--muted)}
.toc-algos{list-style:none;margin:0;padding:0 0 6px 10px;display:none}
.toc-group.open .toc-algos{display:block}
.toc-algos a{display:block;padding:4px 8px;font-size:12.5px;color:var(--sidebar-fg);
  text-decoration:none;border-radius:4px;border-left:2px solid transparent}
.toc-algos a:hover{background:var(--accent-light)}
.toc-algos a.active{background:var(--sidebar-active);border-left-color:var(--accent);
  color:var(--accent-dark);font-weight:600}
.toc-algos a .tid{color:var(--muted);font-family:var(--mono);font-size:10.5px;
  margin-left:4px}
#sidebar-footer{padding:10px 14px;border-top:1px solid var(--border);font-size:12px;
  display:flex;flex-direction:column;gap:4px}
#sidebar-footer a{text-decoration:none}
main{flex:1;min-width:0;padding:0 0 80px}
.wrap{max-width:1080px;margin:0 auto;padding:0 28px}
h1,h2,h3{line-height:1.25;letter-spacing:-.01em}
#cover{padding:44px 0 10px;border-bottom:1px solid var(--border);margin-bottom:22px}
#cover h1{font-size:31px;margin:0 0 6px}
#cover .sub{color:var(--muted);margin:0 0 20px;font-size:15px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px;padding:0;list-style:none}
.badges li{background:var(--accent-light);color:var(--accent-dark);border-radius:999px;
  padding:4px 12px;font-size:12.5px;font-weight:600}
.cover-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.cover-card{display:block;text-decoration:none;color:inherit;background:var(--code-bg);
  border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;
  transition:border-color .12s,transform .12s}
.cover-card:hover{border-color:var(--accent);transform:translateY(-1px)}
.cover-card b{display:block;font-size:13px;font-weight:600;margin-bottom:2px}
.cover-card span{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--border);margin:16px 0 0;
  flex-wrap:wrap}
.tab-btn{background:var(--tab-bg);border:1px solid var(--border);border-bottom:0;
  border-radius:6px 6px 0 0;padding:8px 14px;font:inherit;font-size:13px;
  cursor:pointer;color:var(--muted);margin-bottom:-1px}
.tab-btn.active{background:var(--bg);color:var(--accent-dark);font-weight:600;
  border-bottom:1px solid var(--bg)}
.tabpane{display:none;padding:18px 0}
.tabpane.active{display:block}
h2.algo-title{font-size:25px;margin:6px 0 4px}
.meta-line{color:var(--muted);font-size:13px;margin:0 0 14px}
.meta-line code{font-size:12px}
.shot{width:100%;margin:0 0 18px}
.shot img{width:100%;height:auto;border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow);display:block;background:#fff}
.shot figcaption{font-size:12.5px;color:var(--muted);margin-top:8px}
.step-badge{display:inline-block;background:var(--accent);color:#fff;border-radius:4px;
  padding:1px 7px;font-size:11px;font-weight:600;margin-right:7px}
table{border-collapse:collapse;width:100%;margin:10px 0 18px;font-size:13.5px}
th,td{border:1px solid var(--border);padding:7px 10px;text-align:left;vertical-align:top}
th{background:var(--tab-bg);font-weight:600}
tbody tr:nth-child(even){background:var(--table-stripe)}
td code{white-space:nowrap}
.prose{white-space:pre-wrap;font-size:14px;line-height:1.65;max-width:78ch}
.prose strong{color:var(--fg)}
.callout{border-left:4px solid var(--accent);background:var(--accent-light);
  border-radius:0 var(--radius) var(--radius) 0;padding:12px 16px;margin:16px 0;
  font-size:13.5px}
.callout b{display:block;margin-bottom:4px;color:var(--accent-dark)}
.steps{counter-reset:step;list-style:none;padding:0;margin:12px 0}
.steps li{counter-increment:step;position:relative;padding:0 0 14px 42px;
  font-size:14px;line-height:1.6}
.steps li::before{content:counter(step);position:absolute;left:0;top:0;width:26px;height:26px;
  border-radius:50%;background:var(--accent);color:#fff;font-size:12.5px;font-weight:700;
  display:flex;align-items:center;justify-content:center}
.steps li::after{content:"";position:absolute;left:13px;top:28px;bottom:2px;width:2px;
  background:var(--border)}
.steps li:last-child::after{display:none}
.howto{white-space:pre-wrap;font-size:14px;line-height:1.7;max-width:78ch;
  padding-left:16px;border-left:2px solid var(--border)}
.group-head{margin:26px 0 6px}
.group-head h2{margin:0}
.group-head .gsteps{font-size:13.5px;color:var(--muted)}
.back{font-size:13px;margin:14px 0 0;display:inline-block}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:900px){.two-col{grid-template-columns:1fr}}
@media(max-width:820px){
  body{flex-direction:column}
  #sidebar{width:100%;flex:none;height:auto;position:static;border-right:0;
    border-bottom:1px solid var(--border)}
  #toc{max-height:42vh}
  .wrap{padding:0 18px}
}
@media print{
  #sidebar,.tabs,#search-wrap{display:none}
  .tabpane{display:block!important}
  body{display:block}
  main{padding:0}
}
"""

JS = r"""
const DATA = __DATA__;
const GROUPS = __GROUPS__;
let current = null;

function esc(s){
  return String(s==null?'':s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function buildTOC(){
  const toc = document.getElementById('toc');
  toc.innerHTML = '';
  GROUPS.forEach((g, gi) => {
    const li = document.createElement('li');
    li.className = 'toc-group' + (gi < 2 ? ' open' : '');
    const btn = document.createElement('button');
    btn.className = 'toc-group-btn';
    btn.innerHTML = '<span class="arrow">' + (gi < 2 ? '▼' : '▶') + '</span> ' +
                    esc(g.name) + ' <span style="opacity:.6;font-weight:400">(' +
                    g.algos.length + ')</span>';
    btn.onclick = () => {
      li.classList.toggle('open');
      btn.querySelector('.arrow').textContent = li.classList.contains('open') ? '▼' : '▶';
    };
    li.appendChild(btn);
    const ul = document.createElement('ul');
    ul.className = 'toc-algs';
    g.algos.forEach(id => {
      const d = DATA[id];
      const a = document.createElement('a');
      a.href = '#' + id;
      a.dataset.name = id;
      a.innerHTML = esc(d.display_name) + ' <span class="tid">' + esc(id) + '</span>';
      a.onclick = ev => { ev.preventDefault(); show(id); };
      ul.appendChild(a);
    });
    li.appendChild(ul);
    toc.appendChild(li);
  });
}

function paramsTable(list, kind){
  if(!list || !list.length) return '<p class="meta-line">none</p>';
  let h = '<table><thead><tr><th>' + (kind === 'out' ? 'Output' : 'Parameter') +
          '</th><th>Label</th><th>Type</th><th>Default</th><th>' +
          (kind === 'out' ? 'Format' : 'Notes') + '</th></tr></thead><tbody>';
  list.forEach(p => {
    let note = '';
    if(kind !== 'out'){
      const bits = [];
      if(p.options && p.options.length) bits.push(p.options.join(' | '));
      if(p.parent) bits.push('from ' + p.parent);
      if(p.mandatory) bits.push('mandatory');
      else if(p.optional) bits.push('optional');
      note = esc(bits.join(' · '));
    } else {
      note = esc(p.extension || '');
    }
    h += '<tr><td><code>' + esc(p.name) + '</code></td><td>' + esc(p.label || '') +
         '</td><td>' + esc(p.type) + '</td><td><code>' +
         esc(p.default === null || p.default === undefined ? '' : p.default) +
         '</code></td><td>' + note + '</td></tr>';
  });
  return h + '</tbody></table>';
}

function runParamsTable(d){
  const rp = d.run_params || {};
  const keys = Object.keys(rp);
  if(!keys.length) return '';
  let h = '<table><thead><tr><th colspan="2">Values used in the captured run</th></tr></thead><tbody>';
  keys.forEach(k => {
    let v = rp[k];
    if(typeof v === 'string' && v.length > 70) v = v.slice(0, 67) + '...';
    h += '<tr><td><code>' + esc(k) + '</code></td><td>' + esc(v) + '</td></tr>';
  });
  h += '</tbody></table>';
  if(d.seconds !== null && d.seconds !== undefined)
    h += '<p class="meta-line">Execution time in the captured run: ' +
         esc(d.seconds) + ' s</p>';
  return h;
}

function stepsFor(d){
  const g = GROUPS.find(x => x.name === d.group);
  const out = [];
  if(g && g.steps) g.steps.forEach(s => out.push(s));
  if(d.note) out.push(d.note);
  return out;
}

function page(d){
  let h = '';
  h += '<a class="back" href="#top">&larr; All tools</a>';
  h += '<h2 class="algo-title">' + esc(d.display_name) + '</h2>';
  h += '<p class="meta-line">Group <code>' + esc(d.group) + '</code> · ' +
       'Processing ID <code>' + esc(d.group_id) + ':' + esc(d.algo_id) + '</code>' +
       (d.seconds !== null && d.seconds !== undefined ?
         ' · run time ' + esc(d.seconds) + ' s' : '') + '</p>';

  h += '<div class="tabs">';
  h += '<button class="tab-btn active" data-t="shot">&#128247; Screenshot</button>';
  h += '<button class="tab-btn" data-t="theory">&#128214; Theory</button>';
  h += '<button class="tab-btn" data-t="params">&#128203; Parameters</button>';
  h += '<button class="tab-btn" data-t="steps">&#128197; Step by step</button>';
  h += '</div>';

  /* --- screenshot pane --- */
  h += '<div class="tabpane active" id="p-shot">';
  if(d.png_b64){
    h += '<figure class="shot"><img src="data:image/png;base64,' + d.png_b64 +
         '" alt="' + esc(d.display_name) + ' four panel screenshot">' +
         '<figcaption><span class="step-badge">4-panel</span>' +
         'Top left: input data · top right: raw output · bottom left: styled output ' +
         '· bottom right: the parameter values used in this run.</figcaption></figure>';
  } else {
    h += '<div class="callout"><b>No screenshot</b>This tool did not produce a ' +
         'renderable result in the captured run.</div>';
  }
  h += runParamsTable(d);
  h += '</div>';

  /* --- theory pane --- */
  h += '<div class="tabpane" id="p-theory">';
  h += '<h3>What the tool does</h3>';
  h += '<div class="prose">' + esc(d.theory || d.help_summary || '') + '</div>';
  if(d.how_read){
    h += '<h3>How to read the result</h3><div class="howto">' + esc(d.how_read) + '</div>';
  }
  if(d.how_use){
    h += '<h3>Using the result</h3><div class="howto">' + esc(d.how_use) + '</div>';
  }
  h += '<div class="callout"><b>Full theory and academic references</b>' +
       '<a href="../URBAN_RESILIENCE_REFERENCE_MANUAL.html#' + esc(d.algo_id) +
       '">Read the ' + esc(d.display_name) +
       ' section of the academic reference manual</a> for the derivation, the ' +
       'assumptions and the literature behind every number this tool produces.</div>';
  h += '</div>';

  /* --- parameters pane --- */
  h += '<div class="tabpane" id="p-params">';
  h += '<h3>Input parameters</h3>' + paramsTable(d.params, 'in');
  h += '<h3>Outputs</h3>' + paramsTable(d.outputs, 'out');
  h += '</div>';

  /* --- steps pane --- */
  h += '<div class="tabpane" id="p-steps">';
  const steps = stepsFor(d);
  if(steps.length){
    h += '<h3>Working sequence for the ' + esc(d.group) + ' group</h3><ol class="steps">';
    steps.forEach(s => { h += '<li>' + esc(s) + '</li>'; });
    h += '</ol>';
  } else {
    h += '<p class="meta-line">No workflow notes for this tool yet.</p>';
  }
  h += '</div>';
  return h;
}

function bindTabs(){
  const btns = document.querySelectorAll('#content .tab-btn');
  btns.forEach(b => {
    b.onclick = () => {
      btns.forEach(x => x.classList.remove('active'));
      document.querySelectorAll('#content .tabpane').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      const pane = document.getElementById('p-' + b.dataset.t);
      if(pane) pane.classList.add('active');
    };
  });
}

function show(id){
  const d = DATA[id];
  if(!d) return;
  current = id;
  document.querySelectorAll('.toc-algs a').forEach(a =>
    a.classList.toggle('active', a.dataset.name === id));
  document.getElementById('content').innerHTML = page(d);
  bindTabs();
  if(location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
  window.scrollTo({top:0, behavior:'instant'});
}

function cover(){
  let h = '<div id="cover"><h1>PlanX Urban Resilience &mdash; Practical Guide</h1>';
  h += '<p class="sub">45 Processing tools &middot; real QGIS screenshots &middot; ' +
       'step-by-step usage on a deterministic demo district</p>';
  h += '<ul class="badges">' +
       '<li>' + GROUPS.length + ' groups</li>' +
       '<li>' + Object.keys(DATA).length + ' tools</li>' +
       '<li>' + Object.keys(DATA).filter(k => DATA[k].png_b64).length +
       ' captured runs</li>' +
       '<li>EPSG:3857 demo district</li>' +
       '<li>Companion to the academic reference manual</li></ul>';
  h += '<div class="cover-grid">';
  GROUPS.forEach(g => {
    g.algos.forEach(id => {
      const d = DATA[id];
      h += '<a class="cover-card" href="#' + esc(id) + '" data-go="' + esc(id) +
           '"><b>' + esc(d.display_name) + '</b><span>' + esc(id) + '</span></a>';
    });
  });
  h += '</div>';
  h += '<h3 style="margin-top:30px">How this guide was produced</h3>';
  h += '<div class="prose">Every screenshot in this guide is a genuine QGIS render. ' +
       'A headless QGIS session runs each of the 45 tools in turn on the ' +
       'plugin&#8217;s own synthetic district, captures the input layers, the raw ' +
       'result, the styled result and the exact parameter values used, and writes ' +
       'them to this page. Nothing here is drawn by hand and no number is ' +
       'illustrative.</div>';
  h += '</div>';
  h += '<h3 style="margin:26px 0 8px">Groups</h3>';
  GROUPS.forEach(g => {
    h += '<div class="group-head"><h2>' + esc(g.name) +
         ' <span class="meta-line" style="display:inline">(' +
         g.algos.length + ')</span></h2>';
    if(g.steps && g.steps.length){
      h += '<ol class="steps">';
      g.steps.forEach(s => { h += '<li>' + esc(s) + '</li>'; });
      h += '</ol>';
    }
    h += '</div>';
  });
  return h;
}

function init(){
  buildTOC();
  document.getElementById('content').innerHTML = cover();
  document.querySelectorAll('#content .cover-card').forEach(c => {
    c.onclick = ev => { ev.preventDefault(); show(c.dataset.go); };
  });
  const id = decodeURIComponent(location.hash.replace('#',''));
  if(id && DATA[id]) show(id);
  window.addEventListener('hashchange', () => {
    const h = decodeURIComponent(location.hash.replace('#',''));
    if(h && DATA[h]) show(h);
  });
  document.getElementById('search').addEventListener('input', function(){
    const q = this.value.trim().toLowerCase();
    document.querySelectorAll('#toc .toc-group').forEach(g => {
      let any = false;
      g.querySelectorAll('.toc-algos a').forEach(a => {
        const hit = !q || a.textContent.toLowerCase().indexOf(q) >= 0;
        a.style.display = hit ? '' : 'none';
        if(hit) any = true;
      });
      g.style.display = any ? '' : 'none';
      if(q && any) g.classList.add('open');
    });
  });
  document.addEventListener('keydown', e => {
    if((e.ctrlKey || e.metaKey) && e.key === 'k'){
      e.preventDefault();
      document.getElementById('search').focus();
    }
    if(e.key === 'Escape' && document.activeElement &&
       document.activeElement.id === 'search'){
      document.getElementById('search').blur();
    }
  });
}

document.addEventListener('DOMContentLoaded', init);
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PlanX Urban Resilience &mdash; Practical Guide</title>
<meta name="description" content="Step-by-step practical guide for the 45 PlanX
Urban Resilience Processing tools, with real QGIS screenshots captured from
actual algorithm runs.">
<style>__CSS__</style>
</head>
<body id="top">
<nav id="sidebar">
  <div id="sidebar-header">
    <span class="logo">PlanX Urban Resilience</span>
    <span class="subtitle">Practical Guide &middot; 45 tools</span>
  </div>
  <div id="search-wrap">
    <input type="text" id="search" placeholder="Search tools&hellip;" autocomplete="off">
  </div>
  <ul id="toc"></ul>
  <div id="sidebar-footer">
    <a href="../URBAN_RESILIENCE_REFERENCE_MANUAL.html">&larr; Academic Reference Manual</a>
    <a href="../index.html">Plugin documentation</a>
  </div>
</nav>
<main id="content"></main>
<script>__JS__</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(build())
