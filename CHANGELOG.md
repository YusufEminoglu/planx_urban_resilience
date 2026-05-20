# Changelog

All notable changes to **PlanX: Urban Resilience** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning: [SemVer](https://semver.org/).

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
