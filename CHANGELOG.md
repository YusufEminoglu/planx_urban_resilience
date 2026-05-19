# Changelog

All notable changes to **PlanX: Urban Resilience** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning: [SemVer](https://semver.org/).

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
