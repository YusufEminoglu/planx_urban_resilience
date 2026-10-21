# -*- coding: utf-8 -*-
"""Verify the practical-guide run produced meaningful results, not empty layers."""
import json
import os
import sys
from pathlib import Path

GUIDE = Path(r"C:\Users\YE\PyCharmMiscProject\qgis_plugins\planx_urban_resilience\docs\PRACTICAL_GUIDE")
WORK = GUIDE / "work"
SHOT = GUIDE / "screenshots"

sys.path.append(r"C:\OSGeo4W\apps\qgis-ltr\python\plugins")
from qgis.core import QgsApplication, QgsVectorLayer, QgsRasterLayer  # noqa: E402

app = QgsApplication([], False)
app.initQgis()

summary = json.load(open(GUIDE / "manifest" / "screenshots_all.json", encoding="utf-8"))
print(f"total={summary['total']} ok={summary['ok']} failed={summary['failed']}\n")

problems = []
print(f"{'algo':<44} {'features':>9}  {'score range / sample field'}")
print("-" * 100)
for aid, r in summary["results"].items():
    png = SHOT / aid / f"{aid}_4panel.png"
    if not png.exists():
        problems.append(f"{aid}: MISSING SCREENSHOT")
        continue
    size = png.stat().st_size
    if size < 12000:
        problems.append(f"{aid}: screenshot suspiciously small ({size} B)")

    gpkg = WORK / f"{aid}__OUTPUT.gpkg"
    note = ""
    nfeat = "-"
    if gpkg.exists():
        lyr = QgsVectorLayer(str(gpkg), aid, "ogr")
        if not lyr.isValid():
            problems.append(f"{aid}: output gpkg invalid")
        else:
            nfeat = lyr.featureCount()
            if nfeat == 0:
                problems.append(f"{aid}: output has 0 features")
            # report the first numeric field range
            best = None
            for f in lyr.fields():
                if f.isNumeric() and f.name().lower() not in ("fid",):
                    vals = []
                    for feat in lyr.getFeatures():
                        try:
                            v = feat[f.name()]
                            if v is not None:
                                vals.append(float(v))
                        except (TypeError, ValueError):
                            pass
                    if vals:
                        lo, hi = min(vals), max(vals)
                        cand = (abs(hi - lo), f.name(), lo, hi)
                        if best is None or cand[0] > best[0]:
                            best = cand
            if best:
                note = f"{best[1]}: {best[2]:.2f} .. {best[3]:.2f}"
            else:
                note = "(no numeric field)"
    else:
        # report-style tools
        for ext in (".html", ".md", ".pdf", ".qml", ".geojson"):
            cand = WORK / f"{aid}__OUTPUT{ext}"
            if cand.exists():
                note = f"{cand.name} ({cand.stat().st_size} B)"
                if cand.stat().st_size < 200:
                    problems.append(f"{aid}: report file nearly empty")
                break
        else:
            for p in WORK.glob(f"{aid}__*"):
                note = f"{p.name} ({p.stat().st_size} B)"
                break
            else:
                problems.append(f"{aid}: no output file at all")
    flag = "  " if nfeat == "-" or (isinstance(nfeat, int) and nfeat > 0) else "!!"
    print(f"{flag}{aid:<42} {str(nfeat):>9}  {note}")

print("\n" + "=" * 100)
if problems:
    print("PROBLEMS:")
    for p in problems:
        print("  -", p)
else:
    print("No problems found.")
