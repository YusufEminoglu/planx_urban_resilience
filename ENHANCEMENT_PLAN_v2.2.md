# PlanX Urban Resilience — Enhancement Plan v2.2.0 (Wildfire/WUI + Coastal Exposure Screening)

**Audience:** an external implementation agent. Work through the phases IN ORDER.
**Repository:** `planx_urban_resilience/` inside the `qgis_plugins` monorepo.
**Current version:** 2.1.2 → **Target version:** 2.2.0 (single release at the end).
**Note on the previous plan:** `ENHANCEMENT_PLAN_v1.26.md` targeted QGIS 4 GUI
parity; that headline goal was superseded by the v2.0.0 major GUI rewrite
(docked Processing panel) and the plugin has since reached v2.1.2 through a
documentation-quality arc (v2.1.0/2.1.1). This plan does not continue that
backlog — it starts fresh from the real v2.1.2 baseline below.

**One paragraph:** Two new hazard-screening algorithms fill the plugin's most
conspicuous coverage gap. Of the 43 existing algorithms spanning seismic,
heat, pluvial flood, social vulnerability, emergency access, air quality and
drought, **none address wildfire/wildland-urban-interface (WUI) exposure or
coastal/sea-level-rise exposure** — two hazard categories central to urban
resilience planning practice that this plugin, despite its breadth, does not
screen for at all. Both new tools follow the plugin's own established
methodology exactly: a land-cover/DEM-based proxy screening grid for
planning triage, explicitly not a physical fire-spread or hydrodynamic
inundation simulation — the same honest scope boundary already stated for
the existing heat and flood tools.

---

## 0. Ground rules (hard requirements — read before touching anything)

1. **Read the monorepo docs first:** `qgis_plugins/AGENTS.md` and
   `qgis_plugins/RELEASING.md`. LICENSE present, `experimental=False`,
   release via `release.ps1` are mandatory conventions.
2. **No literal single `%` in `metadata.txt`** — breaks the QGIS Hub upload.
   One escaped `%%` already exists on the Cost-Benefit changelog line and
   **must stay as `%%`**. Gate: `grep -nE "(^|[^%])%($|[^%])" metadata.txt`
   must be empty at the end.
3. **No self-praise wording** in user-facing copy: never "elite", "best",
   "ultimate", "world-class" — this includes the manual, which the v2.1.0
   changelog itself describes as written to an "academic register"; match
   that register, not marketing language.
4. **No AI attribution** in commits (no `Co-Authored-By:` trailers of any
   kind).
5. **Never weaken an existing test, assertion, or count pin.** The
   43-algorithm count pin in the GUI harness and the 44 e2e cases in
   `tests/e2e_qgis_full.py` (ported from `scratch/urbres_e2e_qgis.py`) may
   only grow. Any changed expectation must be justified in the report —
   silent loosening invalidates the delivery.
6. **Algorithm IDs are frozen** once shipped. The two new algorithms in this
   plan get their `name()` chosen carefully up front (see Phase 1/2) since
   it can never be renamed later without breaking saved user models.
7. **Security scan:** run `bandit -r . -x tests,__pycache__` before
   finishing; the QGIS Hub hard-blocks Critical findings. Note the known
   Windows-terminal Bandit encoding issue from `REPORT_v1.26.md` (`-f txt`
   crashes on a Unicode `→` in an existing description) — use `-f csv` or
   `-f json` instead, not a workaround that touches the offending file.
8. **Manual entry structure is a hard requirement, not a nice-to-have.**
   Every algorithm's `docs/URBAN_RESILIENCE_REFERENCE_MANUAL.html` entry
   follows a fixed structure established in v2.1.0 and used for all 43
   existing tools: **Academic lineage** (historical narrative with real,
   verified citations/DOIs), **Mathematical Formulation**, **Input Data
   Requirements**, **Output Description**, **Interpretation Guide**, and an
   explicit **When to use vs. when NOT to use** section. Both new
   algorithms' manual entries must match this structure exactly, including
   a stable per-tool HTML anchor (the v2.1.0 changelog documents a real bug
   from tools missing this) and appropriate "See also" cross-links to the
   existing heat/flood tools.
9. **Do not bump the version or write the changelog until Phase 3. Never
   tag, run `release.ps1`, or upload** — the maintainer releases manually
   after reviewing the report.
10. One commit per completed phase, messages like
    `phase-1: add Wildfire/WUI Exposure Screening algorithm`.
11. All text you write (code, help, docs, report) is English.

---

## 1. Baseline facts (verified against the current tree)

- 43 Processing algorithms across 10 modules
  (`processing/{seismic,heat,flood,social,accessibility,air,drought,
  synthesis,reporting,demo}/`), registered by
  `processing/urban_resilience_provider.py`.
- Shared base pattern (see `processing/heat/urban_heat_comfort.py` as the
  concrete model for both new tools): `HelpUrlMixin, GroupMixin,
  QgsProcessingAlgorithm`, a `GROUP_<HAZARD>` constant from `_mixins.py`, a
  weighted additive grid score built from `QgsProcessingParameterNumber`
  weights (each summing toward 1.0 by convention, not enforced in code),
  and a **three-output convention**: a scored grid
  (`OUTPUT_GRID`/`QgsWkbTypes.Polygon`), a priority-zone subset
  (`OUTPUT_PRIORITY`), and an exposed-assets layer
  (`OUTPUT_EXPOSED`/`QgsWkbTypes.Point`).
- No wildfire, WUI, coastal, or sea-level-rise algorithm exists anywhere in
  the current 43. Flood coverage is pluvial (rainfall-driven) only —
  `pluvial_flood_susceptibility` — with no coastal/riverine or SLR
  counterpart.
- Deferred from the last plan, still outstanding: a `DeprecationWarning`
  from the QGIS-4 `QgsField` constructor across many processing files
  (verified non-crashing, cosmetic per `REPORT_v1.26.md` — this plan
  revisits it as low-priority cleanup in Phase 3, not a blocker).

---

## Phase 1 — Wildfire / Wildland-Urban Interface (WUI) Exposure Screening

**What.** A new algorithm, `processing/wildfire/wui_exposure.py`
(`name()`: `wui_exposure_screening`), scoring a study-area grid for wildfire
exposure risk from land-cover proxies: **vegetation/fuel proximity**
(distance to forest/scrub/grassland polygons), **building-to-vegetation
interface density** (buildings within a configurable WUI buffer of
vegetation, the defining characteristic of wildland-urban interface risk),
**slope** (if a DEM is supplied — fire spreads faster upslope; optional
input, degrades gracefully without it exactly like the heat tool's optional
inputs), and **access/egress constraint** (reuse the existing network
layer/accessibility conventions from `processing/accessibility/` rather than
reimplementing road-network logic). Outputs follow the established
three-output convention: a WUI exposure grid, a priority-mitigation-zone
subset, and an exposed-structures point layer.

**API note.** Pure `QgsGeometry` buffer/distance operations and the
project's own established weighted-grid-scoring pattern — no new QGIS API
surface, no external dependency. Slope (if a DEM is supplied) via the same
`QgsRasterLayer` sampling idiom already used by the heat tool's optional
raster inputs.

**Explicit scope boundary (write this into the manual's "When to use vs.
NOT" section, matching the heat tool's own honesty precedent):** this is a
land-cover-proxy screening tool for comparative, first-pass WUI risk
ranking across a study area — it is NOT a fire-behavior or spread-rate
simulation (no wind, fuel moisture, or fire-weather modeling) and must not
be presented as one.

---

## Phase 2 — Coastal / Sea-Level-Rise Exposure Screening

**What.** A new algorithm, `processing/coastal/slr_exposure.py`
(`name()`: `coastal_slr_exposure`), a DEM-based "bathtub model" screening
tool: given a DEM and a coastline/water-body boundary, floods every cell
below a user-specified water level (current mean higher high water plus a
configurable sea-level-rise scenario offset in meters — expose 2–3 common
scenario presets such as +0.5m/+1.0m/+2.0m alongside a free-entry field,
not just a single hard-coded number) and connected to the water body (a
simple flood-fill/connectivity check so a low-lying inland depression with
no hydraulic connection to the coast is not falsely flagged — this
connectivity constraint is the one genuinely necessary piece of spatial
logic beyond a flat elevation threshold, and must be implemented, not
skipped, since an unconnected-cell bathtub model is a well-known and easily
avoided error in this technique). Same three-output convention: an exposure
grid classed by inundation depth, a priority zone subset (e.g., critical
infrastructure or vulnerable population within the exposed area — reuse
`processing/social/` and the existing "critical infrastructure exposure"
tool's input conventions rather than reinventing them), and an exposed-
assets point layer.

**API note.** DEM raster sampling + a connected-component flood-fill from
the coastline seed (`QgsRasterBlock` neighbour traversal, or a documented
lower-effort approximation if full raster connectivity proves too costly at
typical DEM resolutions — state which was implemented and why in the
report, per ground rule 8's honesty requirement). Pure API, no external
dependency.

**Explicit scope boundary:** a static bathtub model ignores wave run-up,
storm surge dynamics, tidal timing, and land subsidence — state this
plainly, matching the WUI tool's equivalent boundary statement.

---

## Phase 3 — Multi-hazard integration, documentation, cleanup, version bump

Only after Phases 1–2 are done and tested:
- Register both new algorithms so they participate in the existing
  **multi-hazard composite index** and **multi-hazard correlation matrix**
  tools (`processing/synthesis/`) — these tools presumably enumerate the
  hazard layers they combine; wire the two new hazards in rather than
  leaving them siloed, since "multi-hazard" synthesis that excludes two of
  the plugin's own hazard types would be a real, avoidable inconsistency.
- Add both to `resilience_pdf_atlas` / `resilience_score_html_report` /
  `resilience_studio_brief` reporting tools' hazard coverage the same way.
- Write both manual entries per ground rule 8's required structure,
  including real, verified citations (WUI risk mapping and coastal bathtub
  modeling both have an established academic literature — do not fabricate
  a citation; if a claimed citation cannot be verified, omit it and say so
  in the report rather than inventing a DOI).
- Low-priority cleanup carried over from the last plan: address the QGIS-4
  `QgsField` constructor `DeprecationWarning` across processing files if
  time permits within this phase; if not, explicitly re-defer it in the
  report with the same justification, not silently.
- Update `README.md`'s algorithm count (43 → 45) and hazard-category list,
  and `CHANGELOG.md` with a new `## [2.2.0]` entry.
- Bump `metadata.txt`'s `version=2.2.0`; confirm the `%%` gate is still
  clean.
- Do **not** tag, run `release.ps1`, or upload.

---

## Known shortcomings register (fix or explicitly defer with reason)

| # | Shortcoming | Severity | Phase |
|---|---|---|---|
| S1 | WUI tool's slope input is optional — confirm the manual states plainly that omitting a DEM degrades ranking quality rather than silently treating flat terrain as equivalent to steep terrain | Medium | 1 |
| S2 | Coastal tool's flood-connectivity check is the one piece of real algorithmic complexity in this plan — do not ship a naive "elevation < threshold" version without connectivity and call it done; if connectivity truly cannot be implemented within scope, this is a DONE-blocking gap, not a footnote | High | 2 |
| S3 | Both new tools' weight parameters should sum-to-1.0 by convention (matching existing tools) but the codebase does not appear to enforce this programmatically anywhere — confirm whether existing tools validate this and match whatever the real convention is, rather than assuming | Low | 1, 2 |
| S4 | Multi-hazard synthesis tools may hard-code their input hazard list rather than reading it dynamically — if so, wiring in two new hazards is a real code change there, not just parameter passing; investigate before assuming Phase 3's integration step is trivial | Medium | 3 |
| S5 | QGIS-4 `QgsField` DeprecationWarning cleanup, carried over from `ENHANCEMENT_PLAN_v1.26.md`/`REPORT_v1.26.md` — re-defer explicitly if not addressed, per ground rule 5 (never silently drop a known, previously-reported item) | Low | 3 |

---

## R. Required response format

Deliver a single file `REPORT_v2.2.md` in the plugin root:

```markdown
# Implementation Report v2.2.0
## 1. Phase status
Phase 1: DONE|PARTIAL — <one line>
Phase 2: DONE|PARTIAL — <one line>
Phase 3: DONE|PARTIAL — <one line>
## 2. Shortcomings register outcomes
S1–S5, plus any NEW shortcomings discovered, numbered S6+
## 3. New algorithm summary
| algorithm id | displayName | inputs | outputs | manual anchor present |
(2 rows)
## 4. Citation verification
(for every citation added to either new manual entry: full reference +
how it was verified, e.g. a resolvable DOI — or explicit note that a claim
was left uncited because it could not be verified)
## 5. Test evidence
### 5.1 pure test output (verbatim, complete)
### 5.2 e2e QGIS 3.44 LTR output (verbatim, complete)
### 5.3 e2e QGIS 4.x output (verbatim, complete)
## 6. Gate outputs
bandit (csv/json format) / `%`-in-metadata grep (verbatim)
## 7. Deviations from this plan
## 8. Commit list
(hash + message, one per line)
```

**Honesty over completeness:** a PARTIAL with truthful evidence is
acceptable; a DONE that the reviewer's re-run contradicts invalidates the
delivery.
