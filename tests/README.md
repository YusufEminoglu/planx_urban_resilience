# PlanX Urban Resilience — Test Suite

## Quick start

```powershell
# ── Pure-logic unit tests (no QGIS needed) ──
python -m pytest tests/test_stats_logic.py -q

# ── Full algorithm end-to-end (headless QGIS) ──
C:/OSGeo4W/bin/python-qgis-ltr.bat tests/e2e_qgis_full.py   # QGIS 3.44 LTR
C:/OSGeo4W/bin/python-qgis.bat tests/e2e_qgis_full.py        # QGIS 4.x

# ── GUI smoke test (dark-palette contrast assertions) ──
C:/OSGeo4W/bin/python-qgis-ltr.bat tests/gui_smoke_qgis.py   # QGIS 3.44 LTR
C:/OSGeo4W/bin/python-qgis.bat tests/gui_smoke_qgis.py        # QGIS 4.x
```

## Important rules

1. **Script files only.** The OSGeo4W `python-qgis*.bat` wrappers do not support
   multiline `python -c` — pass a `.py` file path.
2. **Flush before exit.** If your test calls `os._exit(0)`, call
   `sys.stdout.flush()` first — otherwise redirected output is truncated.
3. **QGIS teardown may segfault.** After offscreen rendering, QGIS may crash
   during `exitQgis()`.  This is harmless; the test result is printed before
   `os._exit(0)`.

## Test inventory

| File | Type | Runner | What it covers |
|------|------|--------|----------------|
| `test_stats_logic.py` | pure-logic unit | plain pytest | BH-FDR, norm CDF, two-sided p, min-max scoring, WCAG contrast ratio |
| `e2e_qgis_full.py` | headless QGIS e2e | `python-qgis*.bat` | All 43 algorithms on synthetic data; output sanity, FDR fields, LISA variance fix |
| `gui_smoke_qgis.py` | GUI smoke + contrast | `python-qgis*.bat` | Dashboard palette fix: simulated dark QPalette, offscreen grabs, WCAG >= 3.0 on every page |

## Output

- `tests/_gui_grabs/` — PNG screenshots from `gui_smoke_qgis.py`, organised by
  QGIS version and palette mode (dark / default).
