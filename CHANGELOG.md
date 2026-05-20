# Changelog

## [1.18.0] - 2026-05-20

- Release v1.18.0: evacuation suite, risk-recovery matrix, reporting and network graph refactor (27 algorithms).

All notable changes to **PlanX: Urban Resilience** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning: [SemVer](https://semver.org/).

## [1.18.0] - 2026-05-20

Risk-recovery matrix, directional road graph, helper rollout.

### Added
- **Risk-Recovery Priority Matrix** (`risk_recovery_priority_matrix`): `priority = hazard * (1 + w * (100 - recovery) / 100)` with `rr_priority_score` and intervention class.
- **Directional roads** in `_network_graph`: optional `direction_field` values `both` / `ft` / `bt` (digitized direction) for evacuation and network criticality.

### Changed
- Synthetic demo roads include a `direction` attribute.
- **Equity-Adjusted Priority** and **Scenario Sensitivity** use `processing/_helpers.py`.

## [1.17.0] - 2026-05-20

Arrival summary, PDF map-book presets, architecture cleanup.

### Added
- **Evacuation Shelter Arrival Summary** (`evacuation_shelter_arrival_summary`): aggregate assigned origins into per-shelter arrival curves; table + optional HTML.
- **PDF Atlas map-book presets**: A3 Standard (200 dpi), A4 Compact (150 dpi), A3 Studio HQ (300 dpi).
- **`processing/_helpers.py`**: shared `clamp`, `composite_risk_class`, `access_risk_class`, `parse_weights_csv`.

### Changed
- **Network Emergency Accessibility** refactored onto `_network_graph` (`build_simple_road_graph`, `multi_source_dijkstra`, `travel_time_minutes`).
- **Multi-Hazard Composite** uses shared helpers.

## [1.16.0] - 2026-05-20

Evacuation v2: per-edge road capacity and optional timestep queue.

### Added
- **`build_road_graph`** returns `edge_capacity` (persons/hour) from `capacity_ph`-style numeric fields or road-class lookup (`ROAD_CLASS_CAPACITY_PH` defaults).
- **Evacuation** parameters: `ROAD_CLASS_FIELD`, `TIMESTEP_MINUTES` (0 = instant greedy), `MAX_TIMESTEPS`.
- Origin outputs: `travel_min`, `evac_delay_min`, `evac_timestep` (queue mode).
- Edge outputs: `trip_count`, `load_pop`, `road_capacity_ph`, `congestion_pct`, `bottleneck_score`.
- Synthetic roads: `capacity_ph` field on demo network segments.

### Changed
- Timestep queue processes origins in waves when road segments exceed per-interval flow capacity.

## [1.15.0] - 2026-05-20

Evacuation simulation + shared road-network graph module.

### Added
- **`processing/accessibility/_network_graph.py`** — shared graph build, snap, multi-target Dijkstra, path reconstruction, travel-time and percentile helpers.
- **Evacuation Time Simulation** (`evacuation_time_simulation`) under Emergency:
  - Greedy capacity-constrained assignment (Farthest-first or Largest-population-first order).
  - Outputs: origins with `evac_shelter`, `evac_min`, `evac_class`, `qa_flag`; shelters with `cap_used` / `cap_pct`; edges with `load_count` / `bottleneck_score`.
  - Processing log reports assigned vs unassigned population and P50/P95 evacuation times.
- Synthetic demo buildings include **`population`** for smoke-test evacuation workflows.

### Changed
- **`network_criticality.py`** refactored to import from `_network_graph` (behaviour unchanged).

## [1.14.0] - 2026-05-20

PDF atlas release + scenario sensitivity + dashboard catch-up.

### Added
- **Resilience PDF Atlas** (`resilience_pdf_atlas`) under Report and QA: A3 multi-page PDF via QgsLayout (cover, overview with legend/stats, optional per-class map pages). Algorithm existed in source but was not registered until this release.
- **Scenario Sensitivity Analysis** (`scenario_sensitivity`) under Synthesis: Latin Hypercube Sampling over component weights within a perturbation band. Outputs `ss_baseline`, `ss_mean`, `ss_std`, `ss_p05`, `ss_p95`, `ss_range`, `ss_stability`, `ss_samples`.

### Fixed
- **Dashboard** module catalog now lists Recovery Capacity Index, Resilience Time-Series Tracker and Resilience PDF Atlas (added in v1.13 but omitted from `MODULES`).
- Overview text and future-modules hint refreshed to match the current roadmap.

## [1.13.0] - 2026-05-20

Recovery capacity + time-series tracker. (v1.11/1.12 git tags were pushed but their metadata version bump did not land; this release packages all four new synthesis algorithms plus Network Criticality and the time-series tracker under one version.)

### Added
- **Recovery Capacity Index** (`recovery_capacity_index`) under Synthesis: composite of four offline-derivable proxies (HHI land-use diversity, road-access redundancy, green coverage, social cohesion). Outputs `rc_diversity`, `rc_redundancy`, `rc_green`, `rc_cohesion`, `rc_score`, `rc_class`, `rc_data_gap`. Pair with Adaptation Priority to surface units that are both high-risk AND low-recovery.
- **Resilience Time-Series Tracker** (`resilience_time_series`) under Report and QA: join two snapshots of the same scored layer on a stable unit ID; per-unit `ts_earlier_score`, `ts_later_score`, `ts_delta`, `ts_delta_pct`, `ts_trend`, optional `ts_target_gap`. Geometry from the later snapshot.

### Already shipped on main (re-packaged into this metadata bump)
- **Multi-Hazard Composite Index** (`multi_hazard_composite_index`): weighted composite + dominant hazard + Shannon diversity + top drivers + data-gap count.
- **Equity-Adjusted Adaptation Priority** (`equity_adjusted_priority`): equity factor from SVI, normalized 0-100 priority + class.
- **Network Criticality** (`network_criticality`): edge betweenness proxy via origin → nearest-destination shortest paths, `usage_count` + `criticality_score`.
- **Climate Projection Overlay** (`climate_projection_overlay`): built-in +1.5°C / +2°C / +3°C scenarios or custom amplification factor; today / projected / delta / class.

## [1.12.0] - 2026-05-20

Network criticality + climate projection overlay.

### Added
- **Network Criticality** (`network_criticality`) under the Emergency group:
  - Builds a graph from the road network, runs an origin→nearest-destination multi-target Dijkstra per origin, and counts edge usage.
  - Output line layer per edge with `edge_id`, `length_m`, `usage_count`, `criticality_score` (0-100).
  - High-score edges are bottlenecks: closing them forces the most reroutes. Pair with Network Emergency Accessibility to see where demand concentrates.
- **Climate Projection Overlay** (`climate_projection_overlay`) under the Synthesis group:
  - Applies a literature-based amplification factor (built-in +1.5°C / +2°C / +3°C scenarios or custom) to a today's score field.
  - Outputs `cp_today`, `cp_scenario`, `cp_factor`, `cp_projected`, `cp_delta`, `cp_delta_class` (Improved / Stable / Slight / Notable / Major increase).
  - Offline-first: no CMIP/downscaled rasters required.
- Both algorithms registered in the Processing provider and the dashboard module catalog.

## [1.11.0] - 2026-05-20

Two new synthesis algorithms from the roadmap.

### Added
- **Multi-Hazard Composite Index** (`multi_hazard_composite_index`): combine N hazard score fields per planning unit. Outputs:
  - `mh_score` weighted composite (0-100)
  - `mh_class` Very High / High / Moderate / Low
  - `mh_dominant` field name with largest weighted contribution
  - `mh_diversity` Shannon entropy 0-100 (single-stress -> multi-stress)
  - `mh_drivers` top 3 contributing field names (CSV)
  - `mh_data_gap` number of missing/non-numeric hazard fields
- **Equity-Adjusted Adaptation Priority** (`equity_adjusted_priority`): multiplies a hazard/composite score by an equity factor `1 + w * (SVI/100)`. Outputs `eq_factor`, `eq_adjusted_raw`, `eq_adjusted_score` (0-100 normalized), and `eq_priority_class`. Surfaces units that are simultaneously high-hazard and high-vulnerability.
- Both algorithms registered in the Processing provider and dashboard MODULES list under group "8 - Synthesis".

## [1.10.0] - 2026-05-19

New icon, dashboard UX overhaul, correctness pass, roadmap.

### Added
- **New plugin icon** representing the full suite: stratified city skyline + sweeping renewal arc + cycle dots on a soft teal-green base. Replaces the seismic-only mark that no longer reflected scope.
- Dashboard **search bar** on Modules and Run pages — real-time filter across title, category, inputs and outputs.
- Dashboard **category grouping** — modules organised by Seismic / Heat / Flood / Social / Emergency / Air / Drought / Synthesis / Report instead of a flat 2-column grid.
- Dashboard **scroll areas** on Overview, Modules and Run pages so content never overflows the dialog on small/narrow screens.
- `ROADMAP.md` — next 9 algorithm candidates (multi-hazard composite, network criticality, evacuation simulation, climate projection overlay, recovery capacity index, PDF atlas, time-series tracker, equity-adjusted priority, scenario sensitivity) with suggested release schedule.
- `tests/smoke_pipeline.py` — one-shot QGIS-console smoke run across 7 modules using synthetic inputs.

### Fixed
- **Seismic / Monte Carlo Debris**: replaced hard-coded `from PyQt5.QtCore import QVariant` with `qgis.PyQt.QtCore` (forward-compatible with Qt6 QGIS builds).
- **Seismic**: empty-input guard on `featureCount()` prevents division-by-zero when no buildings are provided.
- **Seismic**: narrowed bare `except:` to `except (TypeError, ValueError):` so genuine errors (KeyboardInterrupt, SystemExit) propagate instead of being silently swallowed.
- **Seismic**: defensive `idx_f >= 0` check guards against missing floor/year fields.

## [1.9.0] - 2026

Added Markdown studio brief generation for planning communication.
- Added Resilience Studio Brief to create first-draft executive summaries, key metrics, class distributions, dominant drivers, limitations, and suggested next actions.
- Updated dashboard module cards, README, metadata, and Plugin Hub changelog for HTML/Markdown reporting workflows.

## [1.8.0]

Added scenario planning template generation.
- Added Scenario Planning Template to create editable baseline/proposed score worksheets from any planning unit or scored layer.
- Added intervention labels, scenario metadata, expected reduction, draft status, and notes fields for studio workflows.
- Updated dashboard guidance, README, metadata, and Plugin Hub changelog.

## [1.7.0]

Added QGIS style preset tooling for scored and classified resilience outputs.
- Added Apply Resilience Symbology for 0–100 risk scores, access classes, scenario change classes, and adaptation priority classes.
- Added optional QML style export for reusable cartographic presets.
- Updated dashboard cards, README, metadata, and Plugin Hub changelog.

## [1.6.0]

Added network-based emergency accessibility screening.
- Added Network Emergency Accessibility to compute approximate road-network distance and travel time from origins to shelters or safe assembly areas.
- Added underserved origin outputs, access classes, snap-distance QA flags, and graph-build feedback.
- Updated dashboard guidance, README, metadata, and Plugin Hub changelog for the new network workflow.

## [1.5.0]

Added reporting and scenario comparison tools for studio-ready outputs.
- Added Scenario Comparison / Delta Map to compare baseline and proposed 0–100 score fields.
- Added Resilience Score HTML Report for standalone score summaries, class distributions, and top drivers.
- Updated dashboard module cards, data readiness guidance, README, metadata, and roadmap.

## [1.4.0]

Added synthetic demo data generation and dashboard smoke-test guidance.
- Added Synthetic Resilience Demo Dataset Processing algorithm for artificial study area, buildings, roads, impervious surfaces, green infrastructure, water, shelters, social units, and sensitive receptors.
- Added a dashboard Test page that opens the synthetic dataset generator and explains the smoke-test workflow.
- Updated README, metadata, provider registration, and data readiness guidance for classroom and QA workflows.

## [1.3.0]

Added the remaining roadmap modules as offline-first Processing tools.
- Added Air Quality / Urban Exposure screening for road, source, sensitive receptor, and green buffer inputs.
- Added Drought and Green Infrastructure Stress screening for parks, canopy patches, impervious context, water access, and tree density.
- Added Climate Adaptation Priority Synthesis to combine joined 0–100 risk fields into one priority layer.
- Updated the dashboard, data readiness guidance, README, and Plugin Hub metadata for the expanded eight-module suite.
