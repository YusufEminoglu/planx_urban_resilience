# PlanX: Urban Resilience

QGIS **3.10-3.99** - Processing - **GPL-3**

PlanX Urban Resilience is a modular QGIS suite for early-stage city-scale resilience screening. Version **1.18.0** ships **27 Processing algorithms**: synthetic QA data, seismic debris, heat, flood, social vulnerability, Euclidean and network emergency access, network criticality, air and drought screening, adaptation/multi-hazard/equity/climate/recovery/sensitivity synthesis, time-series tracking, scenario templates and comparison, HTML/Markdown/PDF reporting, and QGIS style presets — plus a dashboard for module discovery and data readiness review.

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

## Dashboard

The plugin adds a `PlanX Urban Resilience` toolbar/menu action. The dashboard includes:

- Overview of available modules
- Data readiness report for loaded QGIS layers
- Module cards with required and optional inputs
- Processing launch shortcuts
- Summary guidance and limitations

## Important Limitations

These modules are screening and prioritization tools. They are designed for planning studios, early feasibility studies, and comparative spatial analysis. They do not replace engineering-grade seismic, hydrodynamic, microclimate, public-health, or evacuation-network models.

## Future Roadmap

- GEE-backed historical climate and land-cover connectors
- Optional map-book presets

See [ROADMAP.md](ROADMAP.md) for the full candidate list and release history.

## Install

Use QGIS Plugin Manager or install the release ZIP from QGIS Plugin Hub / GitHub Releases. For development, add the parent directory of this plugin folder to `QGIS_PLUGINPATH`.

## License

See [LICENSE](LICENSE).
