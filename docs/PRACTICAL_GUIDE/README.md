# PlanX Urban Resilience — Practical Guide

**Companion to the [Comprehensive Academic Reference Manual](../URBAN_RESILIENCE_REFERENCE_MANUAL.html)**

A step-by-step, screenshot-driven guide to all **45** Urban Resilience Processing
tools. The reference manual covers theory, formulas and academic references; this
guide shows **exactly how to use each tool**, on real data, with the exact
parameters used in each run.

Every screenshot in the guide is a **genuine QGIS render of a genuine algorithm
run**. Nothing is drawn by hand and no number is illustrative.

---

## 🌐 Where it lives

| Artefact | Path | Purpose |
|----------|------|---------|
| Interactive guide | `practical_guide.html` | Self-contained SPA (registry + screenshots inlined). Opens from disk, needs no server and no network. |
| Print edition | `practical_guide_static.html` | Script-free, A4-oriented; export to PDF with `Ctrl+P`. |
| Live documentation | https://geophilo.com/planx_urban_resilience/ | Published through the platform portal builder. |

---

## 📁 Structure

```text
planx_urban_resilience/docs/
├── URBAN_RESILIENCE_REFERENCE_MANUAL.html   # academic reference (existing)
└── PRACTICAL_GUIDE/
    ├── practical_guide.html          # ← interactive guide (build_final.py)
    ├── practical_guide_static.html   # ← print / PDF edition (build_static.py)
    ├── template_en.html              # print skeleton with {{CONTENT}} / {{TOC}}
    ├── practical_guide_runner.py     # headless QGIS screenshot generator
    ├── run_practical_guide.bat       # Windows launcher
    ├── build_final.py                # interactive guide builder
    ├── build_static.py               # print edition builder
    ├── manifest/
    │   ├── build_registry.py         # live registry -> algorithms.json + algorithms_detailed.json
    │   ├── algorithms.json           # group -> ordered algorithm ids
    │   ├── algorithms_detailed.json  # ids, help text, every parameter and output
    │   ├── verify_signals.py         # asserts every key result field carries real signal
    │   └── screenshots_<algo>.json   # per-tool capture manifest
    ├── screenshots/
    │   └── <algo_id>/<algo_id>_4panel.png   # 1800 × 1270 px
    └── work/                         # scratch: generated inputs and outputs (wiped each run)
```

---

## 🎯 The four panels

Each screenshot is a 2 × 2 composite:

```
┌────────────────────┬────────────────────┐
│ 1 - INPUT DATA     │ 3 - OUTPUT (RAW)   │
│ source layers       │ geometry only,     │
│                    │ no thematic styling│
├────────────────────┼────────────────────┤
│ 4 - OUTPUT (STYLED)│ 2 - PARAMETERS     │
│ graduated /         │ the exact values  │
│ categorized         │ used in this run  │
└────────────────────┴────────────────────┘
```

The interactive guide adds three more tabs per tool:

| Tab | Content |
|-----|---------|
| 📸 **Screenshot** | The four-panel capture above, plus the parameter table of the run |
| 📖 **Theory** | The tool's own help text, split into *what it does* / *how to read the result* / *using the result*, with a deep link to the reference manual |
| 📃 **Parameters** | Every input parameter (name, label, type, default, enum options) and every output, extracted from the live provider |
| 🗓 **Step by step** | The working sequence for the tool's group, plus an algorithm-specific reading note |

---

## 🚀 Quick start (Windows + QGIS)

### Prerequisites
- **QGIS 3.44 LTR** or **4.2** installed via OSGeo4W
- The PlanX Urban Resilience plugin source in this repository

### Run everything
```cmd
cd C:\Users\YE\PyCharmMiscProject\qgis_plugins\planx_urban_resilience\docs\PRACTICAL_GUIDE
run_practical_guide.bat --all
```

### Run a single tool
```cmd
run_practical_guide.bat --algo urban_heat_comfort_risk
run_practical_guide.bat --algo seismic_debris_monte_carlo
```

### List the tools
```cmd
run_practical_guide.bat --list
```

### Verify the captured results
```cmd
run_practical_guide.bat --verify
```

---

## 🔧 How it works

### Headless runner (`practical_guide_runner.py`)
Runs inside the **QGIS Python environment** (`python-qgis-ltr.bat`), with a
`QgsApplication` in headless mode.

1. **Stage 0 — auxiliary data.** A coastal DEM (GDAL), a shoreline, a vegetation
   band, street trees, emission sources, shelter siting candidates, a 5 × 4
   planning-unit grid with planner-input fields, two hazard periods, and a
   12-point vulnerability sample layer.
2. **Stage 1 — the demo district.** The plugin's own
   `synthetic_resilience_demo_dataset` algorithm produces the nine layers the
   suite expects (study area, buildings, roads, impervious, green, water,
   shelters, social units, sensitive receptors) in EPSG:3857. On top of it the
   runner writes a **noded street network** (11 streets on a 25 m lattice) and
   **land parcels** (building plots).
3. **Stage 2 — the tools.** Each of the 45 algorithms is executed with
   `processing.run()` using a per-tool parameter table, its outputs are
   captured, styled and composited into a four-panel PNG, and a manifest is
   written.

### Why the network and the parcels are prepared

Two preparation steps are not cosmetic — without them the tools report
"unreachable" or empty results on a perfectly reasonable fixture:

- **The road network is noded and densified.** The emergency tools build their
  graph from line *vertices*. The demo dataset ships four two-vertex roads, so
  streets that cross without a shared vertex become four disconnected graph
  components and most origins read as `Unreachable`. The runner's network puts
  a vertex every 25 m and at every crossing, which is what a real (OSM-derived)
  network looks like. Because every vertex sits on the 25 m lattice and
  `SNAP_TOLERANCE` is set to 25, the node quantisation is exact and the
  reported distances are true distances.
- **Land parcels are plot-sized.** The seismic debris model subtracts parcels
  *and* buildings from the study envelope to obtain the open network, then
  intersects the debris envelope with what is left. Plot-sized parcels leave
  the debris spread visible in the open-space network instead of swallowing it.

### Verification (`manifest/verify_signals.py`)
A guide that shows empty layers is worse than no guide. The verifier opens every
key output and asserts that the score field actually **varies** — a heat grid
whose `heat_score` is constant, an SLR priority layer with no rows, or a
shelter siting result where nothing was selected are all failures. The runner
is expected to end with `DONE: 45 ok / 0 failed / 0 no-setup / 45 total` **and**
the verifier to print `All key result fields carry real signal.`

---

## 📋 Tool coverage (45 total)

| Group | Tools |
|-------|-------|
| 0 - Demo and QA | 1 |
| 1 - Seismic: Debris and Logistics | 1 |
| 2 - Heat: Comfort and Exposure | 1 |
| 3 - Flood & Coastal: Pluvial and SLR Susceptibility | 2 |
| 4 - Social: Vulnerability and Equity | 1 |
| 5 - Emergency: Accessibility and Coverage | 6 |
| 6 - Air: Exposure Screening | 1 |
| 7 - Drought & Wildfire: Green and WUI Stress | 2 |
| 8 - Synthesis: Adaptation Priorities | 18 |
| 9 - Report and QA | 12 |
| **Total** | **45** |

---

## 🛠️ Extending the guide

### Add a workflow note for one tool
Edit `EXTRA_NOTES` in `build_final.py` — the key is the algorithm id.

### Add a group workflow
Edit `GROUP_STEPS` in `build_final.py` — the key is the group label, exactly as
the provider reports it (`0 - Demo and QA`, `8 - Synthesis: Adaptation
Priorities`, …).

### Change the parameters of a capture
Edit `build_setup()` in `practical_guide_runner.py`. The table is explicit per
tool; `resolve_params()` then repairs it against the live
`parameterDefinitions()`, so a renamed parameter degrades to the algorithm's own
default instead of failing the run.

### Regenerate the registry
```cmd
C:\OSGeo4W\bin\python-qgis-ltr.bat manifest\build_registry.py
```

The registry is built by **introspecting the live provider**, not by scraping
source with regex — so the ids, parameter names, defaults and enum options in
the guide are the ones QGIS itself uses.

---

## 🔗 Relationship to the reference manual

The two documents are parallel companions and neither embeds the other:

- The **reference manual** is the theory: derivation, assumptions, literature,
  per-algorithm anchors (`#<algo_id>`).
- The **practical guide** is the practice: screenshots, parameters, workflows.

The guide deep-links into the manual for every tool
(`../URBAN_RESILIENCE_REFERENCE_MANUAL.html#<algo_id>`), and the ids match
because both sides use the algorithm's real `name()`.

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `QGIS Python not found` | Install OSGeo4W; ensure `python-qgis-ltr.bat` is reachable |
| `Could not find the provider` | Run from the repository root so `planx_urban_resilience` is importable, or set `PYTHONPATH` |
| `Algorithm failed` | Check `work/` for the produced output and the runner log for the exact message |
| Empty layers in a screenshot | Run `run_practical_guide.bat --verify` — it names the field that carries no signal |
| Screenshots look stale | `work/` is wiped on every run; re-run `--all` |

---

## 📄 License

Same as the plugin: **GPL-3.0** © Yusuf Eminoğlu

---

## 🤝 Contributing

1. Run `run_practical_guide.bat --algo <your_algo>` to regenerate one capture
2. Run `run_practical_guide.bat --verify` — the verifier must stay green
3. Review `practical_guide.html` in a browser
4. Add workflow notes to `build_final.py` if the tool deserves them
5. Submit a PR — screenshots are committed under `docs/PRACTICAL_GUIDE/screenshots/`

---

> **Note:** this guide is generated *from* the code — parameter tables, help text
> and algorithm metadata are extracted from the live provider. The screenshots
> are the only manual component, and they are captured by running the real
> algorithms on the real demo district.
