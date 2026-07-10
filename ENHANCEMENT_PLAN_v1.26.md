# PlanX Urban Resilience — Enhancement Plan v1.26.0 ("QGIS 4 GUI Parity, Tested & Documented")

**Audience:** an external implementation agent (DeepSeek). Work through the phases IN ORDER.
**Repository:** `planx_urban_resilience/` inside the `qgis_plugins` monorepo.
**Current version:** 1.25.1 → **Target version:** 1.26.0 (single release at the end).
**Baseline facts (verified 2026-07-10 on real QGIS 4.0.x / Qt 6.11 and QGIS 3.44):**
- 43 Processing algorithms, all registered by `processing/urban_resilience_provider.py` (verified: `len(provider.algorithms()) == 43` on QGIS 4).
- The plugin module **imports cleanly on QGIS 4** — `qgis.PyQt.QtWidgets` shims `QAction`, so `urban_resilience_plugin.py:6` does not crash (verified by running the import under `python-qgis.bat`). Do not "fix" a Qt6 import crash that does not exist; the QtWidgets→QtGui QAction move is still worth normalizing (Phase 1.4) but it is NOT the bug.
- `UrbanResilienceDashboard` instantiates and `show()`s headlessly on QGIS 4 without exceptions.
- **Therefore the known QGIS 4 GUI problems are visual/palette-level, not load-level.** They cannot be caught by exception-based headless tests. Phase 1 explains the root cause; Phase 2 builds the harness that proves the fix.
- Other verified gaps: `helpUrl()` count in `processing/` = **0**; the in-repo `tests/` directory is **empty** (only `__pycache__`); the real e2e lives outside the plugin at `qgis_plugins/scratch/urbres_e2e_qgis.py`; `qgisMinimumVersion=3.10` is almost certainly untrue for the current codebase.

---

## 0. Non-negotiable ground rules (read before touching anything)

1. **Read the monorepo docs first:** `qgis_plugins/AGENTS.md` and `qgis_plugins/RELEASING.md`. LICENSE present, `experimental=False`, release via `release.ps1` are mandatory conventions.
2. **No literal single `%` in `metadata.txt`** — breaks the QGIS Hub upload (configparser interpolation). One escaped `%%` already exists on the Cost-Benefit changelog line (line ~52) and **must stay as `%%`**. Gate: `grep -nE "(^|[^%])%($|[^%])" metadata.txt` must be empty at the end (bare `%` forbidden, `%%` allowed).
3. **No self-praise wording** in user-facing copy: never "elite", "best", "ultimate", "world-class".
4. **No AI attribution** in commits (no `Co-Authored-By:` AI trailers of any kind).
5. **Never weaken an existing test, assertion, or count pin.** Counts only go up. If a gate blocks you, fix the code. Any changed expectation must be justified in the report Section 6 — silent loosening invalidates the delivery.
6. **Algorithm IDs are frozen.** e.g. `sismik_risk_dinamik_analizor_v2` is a legacy Turkish id — saved user models/scripts reference it. Never rename an algorithm `name()`; only `displayName()`/help text may be edited.
7. **Security scan:** run `bandit -r . -x tests,__pycache__` before finishing; the QGIS Hub hard-blocks Critical findings (SHA-1/MD5, B303/B324).
8. **Do not bump the version or write the changelog until Phase 6. Never tag, run release.ps1, or upload** — the maintainer releases manually after review.
9. One commit per completed sub-phase, messages like `phase-1: pin dashboard palette for Qt6 dark theme`.
10. All text you write (code comments, help, docs, report) is English.

---

## Phase 1 — QGIS 4 GUI parity (THE headline requirement)

### 1.1 Root cause (already diagnosed — read carefully, then verify yourself)

`dashboard.py` `_build_ui()` (~line 383) sets a stylesheet that gives widgets **backgrounds without pinning text colors**, and leaves several widget classes entirely unstyled:

- `QPushButton { background: white; ... }` — **no `color:`**. On QGIS 3 the host palette is light, so button text is dark by accident. On QGIS 4 the host palette is typically **dark**: button text inherits a near-white palette color → **white text on white buttons** (invisible).
- Generic `QLabel`, `QCheckBox`, `QLineEdit`, `QComboBox`, `QSpinBox`, `QScrollArea` contents, `QFileDialog`-adjacent inline widgets: not styled at all → they inherit the dark host palette → dark popup surfaces, ghost labels on white `QGroupBox` cards.
- `QGroupBox { background: white }` — no `color:` for its child text.
- `QTextBrowser { background: white }` — no `color:`; on a dark palette its default text color can be light → unreadable report panel.

**The proven remedy is in this monorepo:** `zero2viz/dialogs/dock.py` lines ~67–170 (`_DOCK_QSS` + the comment block above it). 02viz had the identical bug on QGIS 4 ("black dropdown + unreadable text") and fixed it by **pinning every text and input color** in the panel stylesheet so it reads identically under any host theme, light or dark. Study that stylesheet before writing yours — it is the reference implementation for this phase, including: explicit `QComboBox QAbstractItemView` styling for the popup list, `:disabled` states, `selection-background-color`, checkbox text color, and tooltips.

### 1.2 Fix `dashboard.py`
- Extend the dashboard stylesheet so that EVERY widget class used in the dialog has both background AND text color pinned, following the 02viz pattern (adapt 02viz's structure, keep Urban Resilience's own colors: `#f4f7fb` shell, `#102027` nav, `#0f766e` accent).
- Mandatory coverage: `QLabel` (generic), `QPushButton` (+`:hover`, `:disabled`, `#primaryButton`), `QGroupBox` + `::title`, `QCheckBox`, `QLineEdit`, `QComboBox` + `QComboBox QAbstractItemView` (the popup), `QSpinBox`/`QDoubleSpinBox` if used, `QListWidget` items, `QTextBrowser` text color, `QScrollArea`/viewport background, `QToolTip`.
- Audit inline HTML in `QTextBrowser` content (e.g. `_refresh_report`, module cards ~line 746): hardcoded `color:#64748b` spans on an unpinned background — ensure the browser's base background+color are pinned so inline colors stay readable.
- The existing `IS_QGIS4` size tweaks (~lines 380–382) may stay, but sizes are not the fix — colors are. Do NOT fork the stylesheet per version; ONE palette-independent stylesheet must serve both QGIS 3.44 and QGIS 4.
- While in the file: check every `Qt.` enum access and signal/API for Qt6 deprecations (run with `-W always::DeprecationWarning` in the Phase 2 harness and fix what this plugin emits).

### 1.3 Sweep for other GUI surfaces
- `urban_resilience_plugin.py`: toolbar action + menu — verify icon (`icons/plugin.svg`) renders on Qt6 (SVG via QIcon is fine; confirm no raster fallback needed).
- Any `QMessageBox`/`QFileDialog`/`QDialog` created elsewhere (grep `QDialog(`, `QMessageBox`, `QFileDialog` across the plugin) — system dialogs are fine; custom-styled ones must obey 1.2.
- `processing.execAlgorithmDialog` calls: the Processing dialogs are QGIS-native — do not restyle them.

### 1.4 Normalize the QAction import
Even though the shim currently saves it, switch `urban_resilience_plugin.py` to the ecosystem-standard dual import (see `zero2viz/main_plugin.py:16–19`):
```python
try:  # Qt5: QtWidgets / Qt6: QtGui
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # QGIS 4 / Qt6 without shim
    from qgis.PyQt.QtGui import QAction
```

**Phase 1 exit criteria:** the Phase-2 harness (build it next) proves, with screenshots under a simulated dark palette, that every dashboard page is readable; no plugin-origin deprecation warnings on QGIS 4.

---

## Phase 2 — GUI verification harness (so this class of bug can never ship silently again)

The existing e2e (`scratch/urbres_e2e_qgis.py`) exercises algorithms only; it passed while the GUI was broken. Build `tests/gui_smoke_qgis.py` (in-repo this time) that runs under BOTH `C:/OSGeo4W/bin/python-qgis-ltr.bat` (QGIS 3.44) and `C:/OSGeo4W/bin/python-qgis.bat` (QGIS 4). **Script files only — multiline `python -c` silently fails.**

The harness must:
1. Set `QT_QPA_PLATFORM=offscreen`, init QGIS, register the provider, assert **exactly 43 algorithms** (pin).
2. **Simulate the QGIS 4 dark theme:** build a `QPalette` with dark Window/Base/Button and near-white WindowText/ButtonText/Text, apply it via `QApplication.setPalette(...)` BEFORE constructing the dashboard (02viz verified its fix the same way — see its 0.10.x changelog entry "grabbed under a simulated dark palette").
3. Instantiate `UrbanResilienceDashboard`, `show()`, iterate **all nav pages** (Overview, Data, Modules, Run, Report, Test, Beta), and for each page `widget.grab().save(...)` a PNG into `tests/_gui_grabs/<qgis_ver>/<page>.png`.
4. **Programmatic readability assertions** (not just screenshots): for every visible `QLabel`, `QPushButton`, `QCheckBox` and the `QTextBrowser`, resolve the *effective* text color and background (walk up parents for the first non-transparent background) and assert a minimum WCAG-ish contrast ratio ≥ 3.0. A helper that samples the grabbed pixmap under each widget's text rect and compares average luminance to the text color is acceptable and more robust than stylesheet parsing.
5. Also grab one `QComboBox` with its popup open if any combo exists in the dashboard (the popup was 02viz's worst offender).
6. Run with deprecation warnings escalated; fail on any warning originating from `planx_urban_resilience/*`.
7. Print a `PASS n_checks=<N>` summary line; end with `sys.stdout.flush(); os._exit(0)` (QGIS teardown may segfault after offscreen rendering — flush BEFORE `os._exit`, otherwise redirected output is lost).

**Phase 2 exit criteria:** harness passes on both QGIS versions under the simulated dark palette AND the default palette (4 runs total); the PNG grabs are committed (small, few hundred KB total) or attached in the report; contrast assertions count ≥ 40 checks.

---

## Phase 3 — Processing help completeness

- `shortHelpString`: coverage is good (most of the 43 algorithms have it) — **audit all 43**: each must state inputs (with units/ranges), outputs, method (2–4 sentences), and typical use, in English. Upgrade any that are one-liners. Algorithm-specific text only; boilerplate is rejected.
- `helpUrl()`: currently **0/43**. Add it for all 43 (repo URL `https://github.com/YusufEminoglu/planx_urban_resilience` is acceptable), via a mixin or per-algorithm — without touching `name()`, `group()`, or parameters.
- While in every file, log defects in your report: bare `except:`, prints instead of `feedback.pushInfo`, zero-division risks, nodata inconsistencies vs `processing/_helpers.py`. Fix trivial ones; list risky ones.

**Phase 3 exit criteria:** `grep -rln "helpUrl" processing --include="*.py" | wc -l` covers all 43 algorithm files; report contains a 43-row audit table.

---

## Phase 4 — Bring the test suite into the repo

**Finding:** `tests/` contains only `__pycache__`; the real gates live outside the plugin (`scratch/urbres_e2e_qgis.py`, `tools/qgis_synthetic_smoke.py`). A release should be reproducible from the repo alone.

- Create `tests/e2e_qgis_full.py` — port/adapt `qgis_plugins/scratch/urbres_e2e_qgis.py` (keep ALL of its numeric assertions; count may only grow). It must: register provider, pin 43, execute every algorithm at least once on synthetic data (the plugin ships `synthetic_resilience_demo_dataset` — use it), assert output sanity (score ranges, field presence, FDR fields on Gi*/LISA, LISA significance not all-significant — that regression is documented in the 1.25.0 changelog).
- Keep `tests/gui_smoke_qgis.py` from Phase 2.
- Add `tests/README.md` (how to run both harnesses on 3.44 LTR and 4.x via OSGeo4W wrappers, script-file rule, `os._exit` note).
- Pure-logic unit tests: extract at least the LISA randomization moments, Gi* + BH-FDR, and one synthesis scoring core into importable functions if they aren't already, and cover them with `tests/test_stats_logic.py` runnable by plain pytest (no QGIS). Known-value cases: BH-FDR on a textbook p-value vector; LISA moments vs Anselin (1995) formulas on a tiny weights matrix.

**Phase 4 exit criteria:** `python -m pytest tests/test_stats_logic.py -q` green; both QGIS harnesses green on 3.44 and 4.x; all four outputs pasted verbatim in the report.

---

## Phase 5 — Docs & metadata truthfulness

- `metadata.txt`: raise `qgisMinimumVersion` from 3.10 to the oldest version actually exercised (3.28 unless you verify older); keep `qgisMaximumVersion=4.99`; description/about proof-read; **no `%`**.
- `README.md`: add a short "QGIS 4 support" note (dark-theme-safe dashboard, verified on 3.44 LTR + 4.x); verify the 43 count everywhere; factual tone.
- `CHANGELOG.md`: 1.26.0 entry written in Phase 6 covering: dark-palette GUI fix (describe the symptom honestly), GUI verification harness, helpUrl for all algorithms, in-repo test suite, metadata minimum-version correction.
- Dashboard `MODULES` catalog (hardcoded list at the top of `dashboard.py`): assert programmatically (inside the Phase-2 harness) that every catalog `algorithm` id resolves in the provider and that no provider algorithm is missing from the catalog — report any mismatch and fix the catalog.

---

## Phase 6 — Version bump & final gate (only when Phases 1–5 are green)

1. Bump to `1.26.0` in `metadata.txt` + changelog entry (English, no `%`).
2. Full gate — paste ALL outputs verbatim in the report:
   - `python -m pytest tests/ -q`
   - `tests/e2e_qgis_full.py` on QGIS 3.44 and on QGIS 4.x
   - `tests/gui_smoke_qgis.py` on QGIS 3.44 and QGIS 4.x (dark + default palette)
   - `bandit -r . -x tests,__pycache__` — no Critical
   - `python -m flake8 --max-line-length=140 --extend-ignore=E203,W503 .` — report count; fix what you introduced
   - `grep -nE "(^|[^%])%($|[^%])" metadata.txt` — empty (the existing `%%` escape stays)
3. Commit. **Do not tag/release/upload.**

---

## Known shortcomings register (fix or explicitly defer with reason)

| # | Shortcoming | Severity | Phase |
|---|---|---|---|
| S1 | Dashboard stylesheet pins backgrounds but not text colors → unreadable widgets under QGIS 4 dark palette (02viz-class bug; QPushButton has no `color:`, QLabel/QCheckBox/QComboBox/QLineEdit/QTextBrowser text unstyled) | Critical | 1 |
| S2 | No GUI test of any kind — algorithm e2e passed while the GUI was visually broken on QGIS 4 | High | 2 |
| S3 | `tests/` directory empty; real e2e lives outside the repo (`scratch/urbres_e2e_qgis.py`) → release not reproducible from repo | High | 4 |
| S4 | `helpUrl()` 0/43 | Medium | 3 |
| S5 | `qgisMinimumVersion=3.10` almost certainly false for current code | Medium | 5 |
| S6 | Dashboard `MODULES` catalog is hardcoded with no consistency check against the provider | Medium | 2.7/5 |
| S7 | `QAction` imported from QtWidgets (works via shim today; fragile) | Low | 1.4 |
| S8 | No pure-logic unit tests for the statistical cores (LISA moments, BH-FDR) that already regressed once (pre-1.25 LISA bug) | Medium | 4 |
| S9 | 1013-line `dashboard.py` monolith; inline-HTML colors assume light background | Low/Medium | 1.2 |
| S10 | Legacy Turkish algorithm id `sismik_risk_dinamik_analizor_v2` (id FROZEN — document, don't rename) | Info | 0.6 |

---

## R. Required response format (your report back to the reviewer)

Deliver `REPORT_v1.26.md` in the plugin root, structured EXACTLY like this:

```markdown
# Implementation Report v1.26.0
## 1. Phase status
Phase 1: DONE|PARTIAL — <one line>
... (all 6 phases)
## 2. Shortcomings register outcomes
S1: FIXED|DEFERRED — <evidence>
... (S1–S10 + any NEW ones you found, numbered S11+)
## 3. GUI evidence
- before/after screenshot pairs per dashboard page under simulated dark palette (paths to PNGs)
- contrast-assertion summary: N checks, min ratio observed
## 4. Algorithm help table
| algorithm id | shortHelpString quality (ok/upgraded) | helpUrl | defects found | fixed |
(43 rows)
## 5. Test evidence (verbatim, complete outputs)
### 5.1 pytest  ### 5.2 e2e QGIS 3.44  ### 5.3 e2e QGIS 4.x
### 5.4 gui smoke QGIS 3.44 (dark+default)  ### 5.5 gui smoke QGIS 4.x (dark+default)
## 6. Changed-test justifications (empty if none)
## 7. Deviations from this plan / blockers
## 8. Commit list
```

**Honesty over completeness:** a truthful PARTIAL beats a DONE the reviewer's re-run contradicts — the reviewer WILL re-run the harnesses on both QGIS versions and inspect the screenshots.
