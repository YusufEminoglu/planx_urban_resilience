<div align="center">

<img src="icons/icon.png" width="112" alt="PlanX Urban Resilience icon"/>

# PlanX: Urban Resilience

**City-scale resilience screening for QGIS — 45 Processing tools: seismic, flood, coastal SLR, heat, wildfire WUI, social vulnerability, evacuation, spatial statistics, scenarios, reports.**

[![QGIS](https://img.shields.io/badge/QGIS-3.28%2B-93b023?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/planx_urban_resilience/)
[![Version](https://img.shields.io/github/v/tag/YusufEminoglu/planx_urban_resilience?label=version&color=blue)](https://gitlab.com/geophilo1/planx_urban_resilience/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-orange)](LICENSE)
[![QGIS Plugin Hub](https://img.shields.io/badge/QGIS%20Hub-install-589632?logo=qgis&logoColor=white)](https://plugins.qgis.org/plugins/planx_urban_resilience/)
[![Documentation](https://img.shields.io/badge/📖_Reference_Manual-45_algorithms-13a0a0)](https://geophilo.com/planx_urban_resilience/)

</div>

---

PlanX Urban Resilience is a modular QGIS suite for early-stage city-scale resilience screening. The suite ships **45 Processing algorithms**: synthetic QA data, seismic debris and cascade, heat, pluvial flood, coastal sea-level-rise (hydrologically connected BFS flood-fill), social vulnerability, Euclidean and network emergency access, evacuation simulation, optimal shelter siting, network criticality, air, drought, wildfire WUI screening, adaptation/multi-hazard/equity/climate/recovery/sensitivity synthesis, hot-spot (Getis-Ord Gi*) and LISA cluster statistics with FDR-adjusted significance, correlation matrix, IDW vulnerability surfaces, Pareto and cost-benefit economics, lifecycle NPV, time-series tracking, scenario templates and comparison, HTML/Markdown/PDF reporting, 3D risk export, and QGIS style presets — plus a docked Processing panel, colour-grouped by hazard domain with a per-tool icon, for module discovery. All 45 algorithms run on both QGIS 3.44 LTR and QGIS 4.2 — verified via headless e2e harness.

## 📖 Documentation

**[Comprehensive Academic Reference Manual](https://geophilo.com/planx_urban_resilience/)** — 45 algorithms across 10 modules. Every algorithm documented with theoretical background, mathematical formulation, complete parameter tables, output field descriptions, QGIS symbolization guidance, interpretation guides, and DOI-verified academic references. Hosted on Web Documentation with search, collapsible sidebar, and per-algorithm deep links accessible directly from the QGIS Processing dialog (Help button).

**[Practical Guide](https://geophilo.com/planx_urban_resilience/guide/)** — the hands-on companion. Every one of the 45 tools is documented with a **real four-panel QGIS screenshot** (input data → raw output → styled output → the exact parameter values used), a plain-English theory summary, the full parameter table extracted from the live provider, and a step-by-step working sequence for its group. The screenshots are not illustrations: a headless QGIS session runs each tool on the plugin's own synthetic demo district and captures the genuine render, so every number in the guide is reproducible. The guide also ships a print edition (`practical_guide_static.html`) that exports to PDF with `Ctrl+P`.

## Modules

### Synthetic Resilience Demo Dataset

Creates artificial metric layers for smoke testing and teaching the suite without external data. Outputs include study area, buildings, roads, impervious surfaces, green infrastructure, water, shelters, social units, and sensitive receptors.

Suggested smoke-test flow:

- Generate the synthetic dataset.
- Run Heat with study area, buildings, impervious, green, water and sensitive layers.
- Run Air with study area, roads, sensitive receptors and green buffers.
- Run Social with synthetic social units and the generated demographic fields.
- Run Emergency with study area, shelters and buildings or sensitive receptors.
- Run Drought with green infrastructure, impervious surfaces, water and optional tree points.
- Use Synthesis after joining 0-100 risk fields into one planning-unit layer.

A QGIS Console helper is included at `tools/qgis_synthetic_smoke.py`. It generates the demo data and runs the modules that do not require an external DEM or a pre-joined synthesis layer.

> **Note for the network tools.** The emergency-access family builds its routing graph from line *vertices*, so a street network whose lines cross without a shared vertex resolves into disconnected components and most origins come back as `Unreachable`. The demo dataset ships four two-vertex roads for exactly that reason. Before running Network Emergency Accessibility, Network Criticality, Evacuation Time Simulation or Seismic Cascade, split your streets at every intersection (QGIS *Split with lines* on the crossing geometry, or use an OSM-derived network) and set `SNAP_TOLERANCE` to the lattice your street vertices sit on — the tolerance quantises the node coordinates, so a tolerance that does not match the network rounds the reported distances. The [Practical Guide](https://geophilo.com/planx_urban_resilience/guide/) shows a fully prepared 25 m-lattice network doing this correctly.

### Seismic Debris and Logistics

Monte Carlo seismic scenario analysis for building collapse likelihood, debris spread, road blockage, and post-earthquake clearance corridors.

### Urban Heat Comfort Risk

Offline-first screening model that combines impervious surfaces, building density, green/cooling deficit, and optional vulnerable assets into a 0-100 heat risk grid.

Outputs:

- Heat risk grid
- Priority cooling zones
- Exposed buildings / vulnerable assets

### Pluvial Flood Susceptibility

DEM-based screening model for identifying low-lying, flat, drainage-sensitive areas and exposed buildings or road segments.

Outputs:

- Flood susceptibility grid
- Exposed buildings
- Exposed road segments

This is not a hydrodynamic model. It is intended for planning support, classroom analysis, and prioritization.

### Coastal / Sea-Level-Rise (SLR) Exposure Screening

Hydrologically connected bathtub flood-fill model (Poulter & Halpin, 2008; Gesch, 2009; IPCC AR6, 2021) combining DEM elevations, coastline proximity, tidal datums (MHHW), and asset exposures. A breadth-first search (BFS) flood-fill across 8-connected or 4-connected grid cells ensures that isolated inland depressions below sea level are not falsely flagged as coastal flooding.

Outputs:

- Coastal SLR exposure grid (`elev_m`, `water_lvl_m`, `inund_m`, `freeboard_m`, `sink_depth`, `connected`, `slr_score`, `risk_class`)
- Hydrologically connected inundation priority zones
- Exposed coastal structures

### Social Vulnerability Index

Weighted screening model for neighborhood, census, or planning-unit polygons. It can combine population density, elderly population, children, disability or care needs, and low-income/deprivation indicators into a normalized 0-100 `svi_score`.

Outputs:

- Social vulnerability polygons
- `svi_score`
- `svi_class`
- `pop_density`
- `data_flags` for missing optional indicators

### Emergency Accessibility and Shelter Coverage

Grid-based accessibility deficit model for shelters, safe assembly areas, or emergency service points. It identifies places beyond a target service distance and optionally flags underserved buildings, facilities, or population assets.

Outputs:

- Emergency accessibility grid
- `access_score`
- `access_class`
- Underserved assets

### Network Emergency Accessibility

Road-network screening model that estimates access distance and travel time from origins such as buildings, facilities or population points to shelters or safe assembly areas. It builds an offline graph from road line vertices and uses multi-source shortest paths from destinations.

Outputs:

- Network accessibility origins
- `net_dist_m`
- `time_min`
- `access_cls`
- `qa_flag`
- Network underserved origins

### Evacuation Time Simulation

Greedy, capacity-constrained shelter assignment on the road network. Road segments carry a capacity (numeric field or class-based lookup: arterial / collector / local). Set **timestep minutes** to 0 for instant assignment, or > 0 to defer departures when per-interval road flow is exceeded.

Outputs:

- Evacuation origins (`evac_shelter`, `travel_min`, `evac_delay_min`, `evac_min`, `evac_timestep`, `evac_class`, `qa_flag`)
- Shelter utilization (`cap_used`, `cap_pct`, `assign_count`)
- Edge load (`trip_count`, `load_pop`, `congestion_pct`, `bottleneck_score`)
- P50/P95 evacuation times in the Processing log

Macro screening only — not a microsimulation with signals or directional traffic.

### Evacuation Shelter Arrival Summary

Builds per-shelter arrival timelines from evacuation origin outputs (`evac_shelter`, `evac_pop`, `evac_timestep` or binned `evac_min`).

Outputs:

- Table layer (`shelter`, `step_index`, `arrivals`, `cumulative`, `pct_total`)
- Optional HTML summary

### Air Quality / Urban Exposure

Planning-support exposure model that combines major road proximity, optional industrial or emission-source proximity, sensitive receptors, and green buffer mitigation.

Outputs:

- Air exposure grid
- `air_score`
- `risk_class`
- Exposed sensitive receptors

### Drought and Green Infrastructure Stress

Green infrastructure stress model for parks, canopy patches, and ecological open spaces. It combines impervious context, distance to water or blue infrastructure, patch size, and optional tree density.

Outputs:

- Green infrastructure stress polygons
- `stress_score`
- `stress_class`
- High-priority patches

### Wildfire / WUI Exposure Screening

Screens urban and suburban planning areas for Wildland-Urban Interface (WUI) wildfire vulnerability by integrating wildland fuel proximity and coverage (Radeloff et al., 2005), building-to-vegetation interface density within the radiant heat and ember zone (Cohen, 2000), topographic slope rate-of-spread amplification (Rothermel, 1972), and emergency road egress deficits (Cova, 2005).

Outputs:

- WUI exposure screening grid (`fuel_share`, `fuel_dist_m`, `wui_bldg_n`, `slope_pct`, `egress_m`, `wui_score`, `risk_class`)
- Priority WUI intervention zones
- Exposed interface structures

### Climate Adaptation Priority Synthesis

Weighted synthesis model for joined planning units. After spatially joining outputs from other modules into one polygon layer, this tool creates a single `adapt_score`, `adapt_class`, top-driver summary, and missing-data flags.

Outputs:

- Climate adaptation priority layer
- `adapt_score`
- `adapt_class`
- `drivers`
- `missing`

### Scenario Comparison / Delta Map

Compares baseline and proposed scenario score fields in the same layer. Lower scores are treated as better, so negative deltas indicate improvement.

Outputs:

- Scenario comparison layer
- `delta`
- `pct_change`
- `change_cls`
- `action_hint`

### Scenario Planning Template

Creates an editable scenario worksheet from planning units or scored resilience layers. It adds baseline and proposed score fields, a scenario name, intervention type, expected reduction, draft status, and notes.

Outputs:

- Scenario planning template layer
- `base_score`
- `scen_score`
- `interv_type`
- `edit_status`

### Resilience Score HTML Report

Exports a compact standalone HTML summary from any scored resilience layer. It summarizes feature count, score range, average score, high-priority feature count, class distribution, and top driver labels.

Outputs:

- HTML report file

### Resilience Studio Brief (Markdown)

Generates a first-draft Markdown brief for planning studio or stakeholder communication. It summarizes key metrics, class distribution, dominant drivers, limitations, and recommended next actions.

Outputs:

- Markdown brief file

### Apply Resilience Symbology

Applies consistent PlanX visual presets to scored or classified output layers. Presets are available for 0-100 risk scores, access classes, scenario change classes, and adaptation priority classes.

Outputs:

- In-place QGIS layer styling
- Optional QML style export

### Recovery Capacity Index

Scores how well a planning unit can recover after a shock (complement to hazard/exposure modules). Combines land-use diversity, road-access redundancy, green coverage and a social-cohesion proxy.

### Join Hazard Scores to Planning Units

Attaches up to five hazard score fields from other layers onto planning-unit polygons (maximum intersecting value). Use before Multi-Hazard Composite or Adaptation Priority when scores live on separate layers.

### Risk-Recovery Priority Matrix

Combines a hazard or adaptation priority score with recovery capacity. Surfaces units that are both **high-risk** and **low-recovery** — the highest intervention priority.

Outputs:

- `rr_hazard`, `rr_recovery`, `rr_deficit`, `rr_factor`
- `rr_priority_score` (0-100)
- `rr_priority_class` (Immediate / High / Medium / Monitor)

Outputs:

- `rc_diversity`, `rc_redundancy`, `rc_green`, `rc_cohesion`
- `rc_score`, `rc_class`, `rc_data_gap`

### Scenario Sensitivity Analysis

Stress-tests composite scores by varying component weights with Latin Hypercube Sampling. High `ss_stability` means the unit's priority rank is robust to reasonable weight choices.

Outputs:

- `ss_baseline`, `ss_mean`, `ss_std`, `ss_p05`, `ss_p95`, `ss_range`
- `ss_stability` (0-100)
- `ss_samples`

### Resilience Time-Series Tracker

Joins two snapshots of the same scored layer on a stable unit ID and reports progress between dates.

Outputs:

- `ts_earlier_score`, `ts_later_score`, `ts_delta`, `ts_delta_pct`
- `ts_trend` (Improved / Stable / Worsened)
- Optional `ts_target_gap`

### Resilience PDF Atlas

Builds a printable atlas from any scored resilience layer using QgsLayout. Presets: **A3 Standard**, **A4 Compact**, or **A3 Studio HQ** (300 dpi).

Outputs:

- Multi-page PDF (cover, overview map + statistics, optional per-class map pages)

## QGIS 4 support

The dock is dark-theme-safe: all text, background and tooltip colours are explicitly pinned so the panel reads identically under the light host palette of QGIS 3 and the dark host palette of QGIS 4. Verified via an automated GUI smoke test that simulates the QGIS 4 dark theme, offscreen-grabs the dock, and asserts WCAG contrast ≥ 3.0 on every visible widget and every group-header colour, on both 3.44 LTR and 4.2.0.

## Docked Processing panel

The plugin adds a `PlanX Urban Resilience` toolbar/menu action that opens (or raises) a dock — also reachable via **View → Panels → PlanX Urban Resilience**. It replaces the old dashboard dialog with a QGIS-native panel:

- A searchable tree of all 43 tools, one entry per algorithm, grouped by hazard/report domain.
- Each of the 10 groups (Demo and QA, Seismic, Heat, Flood, Social, Emergency, Air, Drought, Synthesis, Report and QA) has its own colour.
- Every tool has its own icon.
- Double-click a tool to open its Processing dialog; right-click for documentation (opens the matching page of the [reference manual](https://geophilo.com/planx_urban_resilience/)).
- The search box filters the tree live by tool name.

## Important Limitations

These modules are screening and prioritization tools. They are designed for planning studios, early feasibility studies, and comparative spatial analysis. They do not replace engineering-grade seismic, hydrodynamic, microclimate, public-health, or evacuation-network models.

## Future Roadmap

- GEE-backed historical climate and land-cover connectors
- Optional map-book presets

See [ROADMAP.md](ROADMAP.md) for the full candidate list and release history.

## Install

Use QGIS Plugin Manager or install the release ZIP from QGIS Plugin Hub / GitHub Releases. For development, add the parent directory of this plugin folder to `QGIS_PLUGINPATH`.

## 🧩 Part of the PlanX ecosystem

This plugin is one of 15 open-source QGIS plugins for urban planning by the same author:

| Planning & analysis | CAD & production | 3D & visualization |
|---|---|---|
| [PlanX](https://gitlab.com/geophilo1/planx_urban_resilience) — spatial-planning suite | [PlanX CAD Toolset](https://gitlab.com/geophilo1/planx_urban_resilience) — drafting-grade CAD | [PlanX 3D City](https://gitlab.com/geophilo1/planx_urban_resilience) — Three.js city viewer |
| [GeoStats Lab](https://gitlab.com/geophilo1/planx_urban_resilience) — spatial statistics | [EasyFillet](https://gitlab.com/geophilo1/planx_urban_resilience) — tangent-arc fillet | [3D OSM Model](https://gitlab.com/geophilo1/planx_urban_resilience) — OSM → 3D city in browser |
| [Suitability Lab](https://gitlab.com/geophilo1/planx_urban_resilience) — raster MCDA | [Settlement Toolset](https://gitlab.com/geophilo1/planx_urban_resilience) — 9-stage settlement plans | [OSM Quick 3D](https://gitlab.com/geophilo1/planx_urban_resilience) — OSM → native QGIS 3D |
| [DataCube Lab](https://gitlab.com/geophilo1/planx_urban_resilience) — spatiotemporal cubes | [UIP Toolset](https://gitlab.com/geophilo1/planx_urban_resilience) — Turkish master-plan automation | [Urban Procedural 3D](https://gitlab.com/geophilo1/planx_urban_resilience) — parametric zoning lab |
| [Urban Resilience](https://gitlab.com/geophilo1/planx_urban_resilience) — 43 resilience tools | [ParcelFlux](https://gitlab.com/geophilo1/planx_urban_resilience) — parcel subdivision | [CartoLab](https://gitlab.com/geophilo1/planx_urban_resilience) — publication cartography |

## 📜 License & author

GPL-3.0-or-later © [Yusuf Eminoğlu](https://github.com/YusufEminoglu) — bug reports and feature requests welcome in [Issues](https://gitlab.com/geophilo1/planx_urban_resilience/-/issues). See [LICENSE](LICENSE).
