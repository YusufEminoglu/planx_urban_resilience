# Changelog

All notable changes to **PlanX: Urban Resilience** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning: [SemVer](https://semver.org/).

## [1.21.0] - 2026-05-20

Four advanced modules — spatial-statistics outliers, hazard cascading, planning economics, criticality overlay.

### Added
- **LISA Local Moran's I** (`lisa_local_moran`, Synthesis): companion to Gi\*. Outputs `lisa_z`, `lisa_lag`, `lisa_I`, `lisa_pvalue`, `lisa_quadrant` (HH / LL / HL / LH / Not significant). The HL and LH outlier classes are the under-served pockets next to thriving neighbourhoods that Gi\* cannot expose.
- **Seismic Cascade — Debris → Network Degradation** (`seismic_cascade_accessibility`, Emergency): pipes seismic debris polygons into the road graph, drops blocked edges, re-runs a multi-source Dijkstra on the degraded network. Per origin: `cas_pre_dist`, `cas_post_dist`, `cas_delta_dist`, `cas_pre_reachable`, `cas_post_reachable`, `cas_status` (Newly cut off / Always cut off / Worse / Same / Recovered). Genuine cross-domain hazard chain modelling.
- **Cost-Benefit Analyzer** (`cost_benefit_analyzer`, Synthesis): `cost = unit_cost × area`; `benefit = score × reduction_factor × population_weight`. Outputs `cb_cost`, `cb_benefit`, `cb_ratio`, 1-N `cb_priority_rank`. Log prints the cumulative-benefit curve (10/25/50/75/90 % breakpoints).
- **Critical Infrastructure Exposure** (`critical_infrastructure_exposure`, Synthesis): combines hazard score and facility criticality into one 0-100 `ci_combined` score per facility. Top-10 list and mean-by-class breakdown in the log.

### Changed
- Provider registers all four new algorithms.
- Dashboard module catalog updated.

## [1.20.0] - 2026-05-20

Four new algorithms pushing the suite to elite scientific + planning-actionable level.

### Added
- **Hot-Spot Cluster Analysis (Getis-Ord Gi\*)** — `hotspot_analysis_getis_ord` (Synthesis):
  - For each feature i, computes the Gi\* statistic over a configurable distance band using either inverse-distance row-standardised weights or a fixed-distance binary band.
  - Pure-Python; `QgsSpatialIndex`-prefiltered neighbour lookup keeps it interactive on 5 000+ feature layers.
  - Output fields: `gi_zscore`, `gi_pvalue`, `gi_class` (Hot-99 / Hot-95 / Hot-90 / Not significant / Cold-90 / Cold-95 / Cold-99). Self included (Gi\*, not Gi).
- **Population-Weighted Exposure** — `population_weighted_exposure` (Synthesis):
  - Translates a 0-100 hazard score into per-unit `pop_exposed = score/100 × pop`. Population comes from a field on the same layer or from a separate point/polygon layer summed by `QgsSpatialIndex`-prefiltered intersection.
  - Logs a study-area summary: total population, breakdown by risk class, top 10 exposed units.
- **Bivariate Choropleth Symbology** — `bivariate_choropleth_symbology` (Report and QA):
  - Tertile-classifies units on a risk axis and a vulnerability axis, then applies a Stevens-style 9-colour categorised renderer.
  - Adds `bv_class` (e.g. `R-H_V-M`), `bv_risk_bin`, `bv_vuln_bin` so the symbology travels with the layer.
- **Recommended Actions Report (Markdown)** — `recommended_actions_report` (Report and QA):
  - Turns a scored layer with optional class and dominant-hazard fields into a structured Markdown report (class distribution, top-N units table, curated intervention checklists per detected hazard family).
  - Built-in catalogue covers heat, flood, seismic, social, air, drought, and emergency-access families plus a generic cross-cutting list.
- Provider and dashboard module catalog updated.

## [1.19.1] - 2026-05-20

Hub-scan hygiene patch (response to the 1.19.0 plugins.qgis.org security scan).

### Fixed
- Removed `build_local_zip.ps1` from the plugin folder. It was a local-dev wrapper that should never have shipped; the Hub security scan flagged it as a "suspicious file" in 1.19.0.
- Hardened `packaging/zip_hub.py` to skip `.ps1`, `.bat`, `.cmd`, `.exe`, `.dll`, `.lnk`, `.pyc`, `.pyo`, `.pyd` and OS clutter (`.DS_Store`, `Thumbs.db`, etc.) by default. No future Hub upload from this monorepo can accidentally ship a local executable.
- Cleared the 32 flake8 issues from the Hub Code Quality report:
  - Unused imports: `Qt` (dashboard.py), `QgsPointXY` (heat/urban_heat_comfort.py), `QgsWkbTypes` (reporting/scenario_comparison.py), `os`/`QSizeF`/`QgsProcessingOutputFile`/`QgsColorRampShader` (reporting/pdf_atlas.py).
  - Dead variable `ys` in `flood/pluvial_flood_susceptibility.py` (only `xs` was used).
  - `seismic/monte_carlo_debris.py`: E302 fixed (two blank lines before class), W293 fixed (no whitespace on blank lines), E701 fixed (one statement per line for the year tier branch).

### Added
- `setup.cfg` disabling W503 (modern PEP 8 prefers line-break-before-operator) and E203 (Black-style slicing). Centralises flake8 config so future scans stay quiet about stylistic-only flags.

## [1.19.0] - 2026-05-20

Join scores to planning units + helpers rollout across hazard modules.

### Added
- **Join Hazard Scores to Planning Units** (`join_scores_to_planning_units`): up to five score layers joined by max intersecting value.
- **`build_local_zip.ps1`**: local Hub zip without git push.

### Changed
- All scored modules (hazard, synthesis, reporting) use `processing/_helpers.py` for clamp and class labels.
- `_helpers`: `accessibility_deficit_class`, `recovery_capacity_class`.

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
