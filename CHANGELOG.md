# Changelog

## [2.1.1] - 2026-08-13

Help-text formatting fix, new main plugin icon, and manual visual polish.

### Fixed

- `shortHelpString()` for all 43 algorithms reformatted so no sentence is broken by a hard line-wrap in the source — every paragraph is now a single continuous logical run built from implicit string concatenation (matching the sibling PlanX plugin's own convention), with content unchanged byte-for-byte after whitespace normalisation.
- The Phase 7 manual design-polish pass's "See also" cross-links silently rendered empty for every one of the 43 tools: the script read a tool's title from `h3.childNodes[0]`, which became the new icon `<img>` (below) instead of the title text node. Fixed to read `h3.textContent` directly.

### Changed

- New main plugin icon (`icons/plugin.svg`): a shield outline framing a small city skyline with a recovery arc. Fully transparent background — replaces the old solid teal-gradient rounded-square tile — with bolder strokes for legibility down to 16px toolbar size.
- The reference manual now shows each tool's own dock icon next to its heading, visually tying the manual to the in-app panel.

## [2.1.0] - 2026-08-13

Documentation-only release: the online reference manual and every algorithm's in-GUI help text are rewritten to the same elite-academic register as the sibling PlanX plugin. No algorithm logic, parameters, or output fields changed.

### Changed

- Every one of the 43 algorithms' manual entry (`docs/URBAN_RESILIENCE_REFERENCE_MANUAL.html`) now has an **Academic lineage** paragraph (historical narrative, real citations, verified DOIs where available), an itemised **Key assumptions** list, and an explicit **When to use vs. when NOT to use** section cross-linking to the better-fit sibling tool. Several entries that were missing whole sections (Theoretical Background, Mathematical Formulation, or the Input Data Requirements table) had them written from scratch, cross-checked against the actual algorithm source. Manual grew from 26,439 to over 40,000 words.
- Every algorithm's `shortHelpString()` rewritten to match: a compact methodology paragraph with inline citation, practical usage notes, a "How to read the results" field-by-field breakdown, and a "Using the results" closing paragraph with concrete planning actions.
- Manual design polish: an on-page mini jump-nav per tool (auto-built from its subsections), a copy-anchor-link button on every tool heading, "See also" cross-link chips between related tools (derived from the when-NOT-to-use notes), and performance/complexity badges on the tools with genuine documented O(n) cost (seismic Monte Carlo, heat grid, network criticality, evacuation simulation, join-to-planning-units, Pareto selector).
- The sidebar's "currently reading" highlight now tracks the specific tool being read, not just its hazard group.

### Fixed

- The manual had no per-algorithm HTML anchors — every tool `<h3>` lacked an `id`, so the dock's right-click "View Documentation" (which opens `helpUrl()` = manual URL + `#<algorithm name>`) landed on the manual but never scrolled to the right entry. Every tool now has a stable, code-name-matching anchor.
- Six stale Processing-ID references in the Reporting section that no longer matched their algorithms' actual `name()` after a past rename.

## [2.0.0] - 2026-08-13

Major GUI rewrite. Mirrors the sibling PlanX plugin: a docked Processing panel replaces the modal dashboard.

### Changed

- The modal `UrbanResilienceDashboard` dialog is replaced by `UrbanResilienceDock`, a `QDockWidget` opened via **View -> Panels -> PlanX Urban Resilience** (or the toolbar/menu action). It shows a searchable tree of all 43 tools grouped by hazard/report domain; double-click a tool to open its Processing dialog, right-click for documentation.
- Every one of the 10 groups (Demo and QA, Seismic, Heat, Flood, Social, Emergency, Air, Drought, Synthesis, Report and QA) now renders with its own colour in the tree.
- Every one of the 43 tools now has its own icon (previously all tools shared the single plugin icon).

### Fixed

- The Emergency group was split across two toolbox labels ("5 - Emergency" vs "5 - Emergency: accessibility and coverage") and Synthesis likewise ("8 - Synthesis" vs "8 - Synthesis: adaptation priorities") - same `groupId`, inconsistent `group()` text. Unified to one label per domain via a shared `GroupMixin`.

### Removed

- The dashboard's Data/Report/Beta pages and their developer-facing tooling: issue-template copy, runtime diagnostics, smoke-test-plan copy, release-notes-draft copy, Hub-changelog-draft copy, and the Beta HTML export.
- The hand-maintained `MODULES` catalog the dashboard used to mirror the Processing registry (a second list that could drift out of sync); the dock now reads `QgsApplication.processingRegistry()` directly.

## [1.26.5] - 2026-08-07

- Added online user manual link (https://yusufeminoglu.github.io/planx_urban_resilience/) and GitHub repository star call-to-action.

## [1.26.4] - 2026-08-07

- Add floating Save as PDF button to reference manual

## [1.26.2] - 2026-07-29

Packaging and security-scan hygiene. No functional or algorithmic change.

### Fixed
- **Plugin Hub security scan is clean without any skip file.** The three remaining
  Bandit findings are resolved in code rather than suppressed: `try/except: pass`
  in the bivariate symbology renderer (B110) and `try/except: continue` in the
  dashboard readiness scan (B112) are now `contextlib.suppress`, keeping the same
  best-effort behaviour without hiding a real error path; the seismic Monte Carlo
  collapse draw uses a new shared `SeededRng` helper instead of `random.Random`
  (B311).
- **Removed the `.bandit` skip file.** It was untracked, so it never shipped in the
  Hub archive and CI never saw it — it only made the local scan look clean while
  the real findings remained. Deleted rather than committed.
- Excluded `.pytest_cache` from the release archive and from git, so cache
  artifacts can no longer enter a Hub upload.
- Cleared the seven Hub-reported W503 quality findings by reformatting arithmetic,
  HTML assembly, attribute-list construction and the LISA variance code. Behaviour
  is unchanged.

### Changed
- `SeededRng` (in `processing/_helpers.py`) is a self-contained 64-bit LCG exposing
  the `random` / `uniform` / `randint` / `shuffle` subset the simulation algorithms
  use. Randomness here is not security sensitive, but reproducibility matters: the
  same seed still yields the same result. Verified on QGIS 3.44.12 and 4.2.0 that
  the Latin hypercube stays deterministic and each dimension remains a full
  permuted stratification.

### Verified
- End-to-end suite passes all algorithms and assertions on QGIS 3.44.12 LTR and
  QGIS 4.2.0; GUI smoke passes on both; `compileall`, Flake8 and Bandit clean.

## [1.26.1] - 2026-07-10

### Fixed
- **Seismic Debris & Logistics module fully translated to English.** `seismic_debris_monte_carlo` (was `sismik_risk_dinamik_analizor_v2`) had a Turkish `displayName`, `group`, `shortHelpString`, parameter labels, output field names (`Yukseklik_m` etc. → `height_m`, `setback_dist_m`, `collapse_prob`, `collapsed`, `debris_radius_m`, `debris_vol_m3`, `blocked_area_m2`) and log message — all converted to English. Group renamed `"1 — Deprem: enkaz ve lojistik"` → `"1 — Seismic: Debris & Logistics"`. Algorithm id, dashboard entry, and e2e reference updated in lockstep.
- **Synthetic demo dataset field names translated**: `katadedi` → `floor_count`, `uipfonksiyon` → `land_use` (`processing/demo/synthetic_dataset.py`), with the e2e harness updated to match.
- **Bivariate Choropleth Symbology help text**: removed a stray Turkish sentence fragment ("kartografya için manuel olarak yerleştirin") left in an otherwise-English `shortHelpString`.

### Added
- **Seismic debris Monte Carlo is now reproducible**: new `SEED` parameter (default 42) drives a per-run `random.Random(seed)` instance instead of the shared global `random` module, so a given scenario (inputs + seed) always produces an identical collapse draw; changing the seed samples a different stochastic realization.

## [1.26.0] - 2026-07-10

### Fixed
- **Dashboard palette fixed for QGIS 4 dark theme.** The stylesheet gave widgets white backgrounds without pinning text colours, so under QGIS 4's dark host palette the inherited near-white text was unreadable (white-on-white buttons, ghost labels, dark dropdown popups). Following the 02viz reference pattern, every text and input colour is now explicitly pinned — QLabel, QPushButton (+`:hover`, `:disabled`, `#primaryButton`), QGroupBox + `::title`, QCheckBox, QLineEdit, QComboBox + `QAbstractItemView`, QSpinBox/QDoubleSpinBox, QListWidget items, QTextBrowser, QScrollArea, QToolTip. One palette-independent stylesheet serves both QGIS 3 and QGIS 4.
- **QAction import normalised** to the ecosystem-standard dual `QtWidgets`/`QtGui` try/except (02viz pattern).

### Added
- **GUI verification harness** (`tests/gui_smoke_qgis.py`): simulated QGIS 4 dark QPalette, offscreen grabs of every dashboard page, programmatic WCAG contrast assertions (≥3.0) on all visible labels, buttons, checkboxes and text browsers. Verified 472 checks, 0 failures on both 3.44 LTR and 4.0.2.
- **helpUrl() for all 43 algorithms** via `HelpUrlMixin`, returning the plugin's GitHub repository URL.
- **In-repo test suite**: `tests/e2e_qgis_full.py` (ported from `scratch/urbres_e2e_qgis.py`), `tests/test_stats_logic.py` (19 pure-logic unit tests for BH-FDR, LISA moments, min-max scoring, WCAG contrast), `tests/README.md`.

### Changed
- **qgisMinimumVersion** raised from 3.10 to 3.28 (oldest version actually exercised).
- **README** updated with QGIS 4 support section, badge, compatibility text, ecosystem table count (28→43).

## [1.25.1] - 2026-06-18

- docs: add CITATION.cff for Zenodo DOI integration

## [1.25.0] - 2026-06-10

Quality release: every one of the 43 algorithms now verified end-to-end on real QGIS (3.44 LTR and 4.0.2) via a headless harness with numeric assertions.

### Fixed
- **QGIS 4: all 43 Processing tools re-enabled.** The v1.24.5 "panel-only" gate hid the whole provider on QGIS 4; the full suite now registers and passes end-to-end on QGIS 4.0.2.
- **PDF Atlas crashed on modern QGIS** (`QgsGraduatedSymbolRenderer.createRenderer: not enough arguments` and `setFrameStrokeWidth` expecting `QgsLayoutMeasurement`). Classification is now pure Python (equal interval / quantile / Jenks via 1D k-means) with explicit YlOrRd graduated ranges, and the memory-layer URI uses `QgsWkbTypes.displayString` (QGIS 3.10-safe).
- **LISA significance was broken**: the variance approximation `(n-1-n*m2)/(n-1)` is always negative for z-standardised data (m2=1), so every feature was flagged significant. Replaced with the proper Anselin (1995) randomization moments (per-feature E[I], Var[I] from row-standardised weights and sample kurtosis).
- **Flood screening read pixels outside the DEM** at study-area edges (GDAL "Access window out of range" spam, lost edge cells); sampling is now clamped into the raster extent with a half-pixel inset.
- **Flood exposed buildings/roads carried a constant score** (the threshold) instead of the real susceptibility; they now get the maximum intersecting cell score and its risk class.

### Added
- **FDR-adjusted significance** (Benjamini-Hochberg) for the multiple-testing problem in local spatial statistics: Gi* hot-spot gains `gi_p_fdr` + `gi_class_fdr`, LISA gains `lisa_p_fdr` + `lisa_quad_fdr`. Prefer the FDR fields when reporting.

### Changed
- Metadata and README tool count corrected from 28 to 43; README module blurb refreshed.
- Removed stale `ROADMAP.md` and the outdated `tests/smoke_pipeline.py` duplicate (wrong parameter names); `tools/qgis_synthetic_smoke.py` remains the QGIS-console helper.
- Added `.zipignore` so dev-only files stay out of the Hub package.

## [1.24.10] - 2026-05-30

- Revised plugin icon

## [1.24.9] - 2026-05-29

- Fixed spatial index instantiation compatibility, CP1252 encoding audit, and test parameters in smoke pipeline.

## [1.24.8] - 2026-05-27

- Code quality and QGIS 4 dashboard polish.
  - Fixed 14 flake8 issues across 12 processing modules: unused imports, dead code, f-strings without placeholders, ambiguous variable name, over-indented continuation, missing EOF newline.
  - Dashboard: QGIS 4 Qt6 responsive font/layout sizing, mojibake text normalization for special characters.

## [1.24.7] - 2026-05-26

- Qt5/Qt6 compatibility maintenance, dashboard runtime hardening, and QGIS 4 processing-provider gate behavior.

## [1.24.6] - 2026-05-26

- Maintenance release: refreshed Plugin Hub package with QGIS 4 panel-only dashboard mode.

## [1.24.5] - 2026-05-26

- Keep QGIS 4 dashboard panel-only by hiding the Processing provider.

## [1.24.4] - 2026-05-26

- Fix QGIS 4 / Qt6 dashboard enum compatibility.

## [1.24.1] - 2026-05-23

- Fix metadata changelog percent escaping for QGIS Hub parser

## [1.24.0] - 2026-05-23

- Beta completion release: dashboard beta control center, readiness audit, diagnostics, smoke plan, hub changelog and html export

All notable changes to **PlanX: Urban Resilience** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning: [SemVer](https://semver.org/).

## [1.26.3] - 2026-08-07

### Added
- Dashboard **Beta** page with release-gate snapshot (`READY` / `NOT READY`) based on loaded layers, vector/raster balance, CRS spread and module-catalog presence.
- Dashboard **Copy Issue Template** action (Report + Beta pages) that copies a structured bug-report template with current layer list and CRS values.
- Dashboard **Copy Diagnostics** action with timestamped runtime profile (layers, vectors/rasters, CRS spread, module count, processing-registry availability/missing list).
- Dashboard **Copy Smoke Plan** action with a 10-step acceptance checklist for repeatable QGIS smoke testing.
- Dashboard quick-launch buttons for core beta flow (`Synthetic Dataset`, `Urban Heat`, `Network Emergency Accessibility`).
- Dashboard **Core module readiness** heuristics (Heat/Flood/Social/Emergency/Synthesis) with explicit `OK/WARN` evidence rows.
- Dashboard **Copy Release Notes Draft** action for rapid publication-note preparation (runtime summary + module readiness digest).
- Dashboard **Copy Hub Changelog Draft** action producing publication-ready changelog text from live runtime checks.
- Dashboard **Export Beta HTML** action to persist readiness snapshots for audit/review workflows.

### Changed
- Dashboard navigation extended with a dedicated Beta tab for QA and acceptance workflow.
- Beta snapshot now audits Processing registry coverage against the full dashboard module catalog and surfaces missing algorithm IDs.

## [1.23.0] - 2026-05-21

Four advanced modules — cross-hazard correlation, temporal × spatial fusion, facility location, lifecycle economics.

### Added
- **Multi-Hazard Correlation Matrix** — `multi_hazard_correlation_matrix` (Report and QA):
  - Pure-Python Pearson + Spearman correlation between N numeric score fields on the same layer (2-12 fields).
  - Standalone HTML report with colour-coded heatmaps (diverging blue/red), top-10 correlations table with strength interpretation, and per-pair n_pairs counts.
  - Also returns a long-format QGIS table sink (field_a, field_b, pearson_r, spearman_r, n_pairs) for further joining/styling.
- **Risk Trend Hot-Spot (Gi\* × Δ score)** — `risk_trend_hotspot` (Synthesis):
  - Fuses temporal trend (delta between two snapshots) with spatial clustering (local Getis-Ord Gi\* on the later snapshot).
  - Per-unit `trh_gi_z`, `trh_gi_significant`, `trh_delta`, `trh_label` (Rising / Stable / Cooling hot spot, Rising / Stable / Cooling cold spot, Hot/Cold no cluster, or Not significant).
  - Direct pair with `resilience_time_series` outputs (`ts_later_score`, `ts_delta`).
- **Optimal Shelter Siting** — `optimal_shelter_siting` (Emergency):
  - Greedy maximal-coverage facility-location problem. Picks K candidate sites that cover the most uncovered population within a max distance.
  - Optional existing-shelter layer pre-covers some demand so the K new picks fill gaps.
  - Per-candidate `oss_selected`, `oss_rank` (1..K), `oss_pop_added`, `oss_pop_total_cum`; per-step coverage curve and uncovered top-10 list in the processing log.
- **Lifecycle Cost Calculator (25-year NPV)** — `lifecycle_cost_calculator` (Synthesis):
  - Discounts capex + annual opex + periodic maintenance + replacement events over a configurable horizon (default 25 years) and discount rate (default 4 % per year).
  - Per-feature `lc_capex_npv`, `lc_opex_npv`, `lc_maintenance_npv`, `lc_replacement_npv`, `lc_total_npv`, `lc_annualised` (equivalent flat annual cost via annuity factor).
  - Optional area scaling for per-m² cost inputs.

### Changed
- Provider registers all four new algorithms. **Suite total: 43 algorithms.**
- Dashboard module catalog updated.

## [1.22.0] - 2026-05-20

Four advanced modules — 3D City bridge, multi-objective optimisation, temporal aggregation, point-to-surface interpolation.

### Added
- **3D Risk Volume Export** — `risk_3d_volume_export` (Report and QA):
  - Scored polygon → GeoJSON in EPSG:4326 with `extrusion_height` (= score × max_height_m) and `color_hex` per feature.
  - Three colour ramps: Yellow-Red (sequential), Blue-Red (diverging), Greys.
  - Optional base-height field is additive (handy when buildings already carry a roof height).
  - In-QGIS sink in the source CRS too so the attributes can be inspected/edited.
  - Result drops straight into the PlanX 3D City Viewer or any Three.js / deck.gl / Cesium scene.
- **Pareto-Optimal Intervention Selector** — `pareto_optimal_selector` (Synthesis):
  - Non-dominated sorting (NSGA-II-style peeling) on a cost field (lower = better) and a benefit field (higher = better). Pair with the Cost-Benefit Analyzer outputs.
  - Per-feature `pareto_rank`, `pareto_dominated`, `pareto_dominates`.
  - `pareto_rank == 1` is the budget-bounded best pick: no other intervention is objectively better.
- **Multi-Period Hazard Frequency Aggregation** — `hazard_frequency_aggregation` (Synthesis):
  - Collapses 2-8 source hazard layers (temporal snapshots, magnitude bins, climate scenarios) into ONE composite per planning unit.
  - Per-unit `hf_frequency`, `hf_mean`, `hf_max`, `hf_min`, `hf_composite` (Mean / Max / Frequency-weighted mean), `hf_class`.
  - Frequency-weighted mean = `mean × (freq / N)` — units that score high in BOTH many periods AND high intensity rise to the top.
- **Vulnerability Surface (IDW)** — `vulnerability_surface_idw` (Synthesis):
  - Pure-Python inverse-distance-weighted interpolation from a point layer into a polygon grid clipped to the study area.
  - Configurable cell size, IDW power, search radius, and maximum-neighbours cap for bounded runtime.
  - Per-cell `vs_value`, `vs_class`, `vs_n_points`.

### Changed
- Provider registers all four new algorithms. **Suite total: 39 algorithms.**
- Dashboard module catalog updated.

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
