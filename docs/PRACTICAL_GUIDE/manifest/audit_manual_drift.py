# -*- coding: utf-8 -*-
"""Audit the reference manual against the LIVE provider.

The Practical Guide's parameter tables are generated from the provider, so any
drift between the manual and the provider shows up as two companion documents
disagreeing about the same parameter. This script finds that drift.

It understands the manual's three documentation styles:

* a plain table row          ``<tr><td><code>NAME</code></td>...``
* a range row                ``<code>SOURCE1</code>–<code>SOURCE5</code>``
* a prose mention            ``<code>NAME</code>, <code>OTHER</code>``

and it compares the manual's *output* section against the output **fields**
(which is what the manual documents) rather than the output sink name.

    C:\\OSGeo4W\\bin\\python-qgis-ltr.bat manifest\\audit_manual_drift.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MANUAL = Path(r"C:\Users\YE\PyCharmMiscProject\geophilo_project\_manual_sources\planx_urban_resilience\URBAN_RESILIENCE_REFERENCE_MANUAL.html")
GUIDE = Path(r"C:\Users\YE\PyCharmMiscProject\qgis_plugins\planx_urban_resilience\docs\PRACTICAL_GUIDE")

html = MANUAL.read_text(encoding="utf-8")
reg = json.loads((GUIDE / "manifest" / "algorithms_detailed.json").read_text(encoding="utf-8"))
details = reg["algo_details"]

sections = re.split(r'<h3 id="([a-z0-9_]+)"', html)
by_id = {sections[i]: sections[i + 1] for i in range(1, len(sections) - 1, 2)}


def documented_names(block: str) -> set[str]:
    """Every parameter name the manual mentions, in any of its three styles."""
    names = set(re.findall(r"<code>([A-Z][A-Z0-9_]*)</code>", block))
    # a range row "SOURCE1-SOURCE5" only spells out the first and last member
    for first, last in re.findall(r"<code>([A-Z][A-Z0-9_]*)</code>\s*[\u2013\u2014-]\s*"
                                  r"<code>([A-Z][A-Z0-9_]*)</code>", block):
        head, tail = first.rstrip("0123456789"), last.rstrip("0123456789")
        if head and tail and head == tail and first[-1].isdigit() and last[-1].isdigit():
            for i in range(int(first[len(head):]), int(last[len(tail):]) + 1):
                names.add(f"{head}{i}")
        else:
            names.add(first)
            names.add(last)
    # a prose list "HEAT_FIELD, FLOOD_FIELD, ... COASTAL_FIELD"
    for lo, hi in re.findall(r"<code>([A-Z][A-Z0-9_]*)</code>\s*\u2026\s*"
                             r"<code>([A-Z][A-Z0-9_]*)</code>", block):
        names.add(lo)
        names.add(hi)
    return names


def section_of(body: str, number: int, title: str) -> str:
    m = re.search(rf"<h4>{number}\. {title}</h4>(.*?)(<h4>\d+\.|$)", body, re.S)
    return m.group(1) if m else ""


problems = []
checked = 0

for aid, det in details.items():
    body = by_id.get(aid)
    if body is None:
        problems.append(f"{aid}: the provider has this tool but the manual has no section")
        continue
    checked += 1

    params_block = section_of(body, 5, "Parameters")
    if not params_block:
        params_block = section_of(body, 3, "Parameters &amp; Usage")
    if not params_block:
        problems.append(f"{aid}: the manual has no parameters section")
        continue
    documented = documented_names(params_block)
    live = {p["name"] for p in det["parameters"]}
    sink_names = {o["name"] for o in det["outputs"]}
    missing = sorted(live - documented)
    # the parameters section may legitimately name the tool's own outputs
    ghost = sorted(documented - live - sink_names)
    if missing:
        problems.append(f"{aid}: manual OMITS live parameters {missing}")
    if ghost:
        problems.append(f"{aid}: manual documents NON-EXISTENT parameters {ghost}")

    out_block = section_of(body, 6, "Output Description")
    if not out_block:
        out_block = section_of(body, 4, "Output Layers")
    if out_block:
        fields = {f["name"] for f in det["outputs"]}
        sink_names = {o["name"] for o in det["outputs"]}
        mentioned = documented_names(out_block)
        # the manual documents output FIELDS; the sink name may or may not
        # appear, and a missing sink name is not drift
        unknown = sorted(mentioned - fields - sink_names)
        if unknown:
            problems.append(f"{aid}: manual documents NON-EXISTENT output fields {unknown}")

# tools in the manual that the provider does not have
for aid in by_id:
    if aid not in details and not aid.startswith("g"):
        problems.append(f"{aid}: the manual has a section but the provider has no such tool")

print(f"audited {checked} algorithm sections against the live provider")
if problems:
    print(f"\n{len(problems)} DRIFT ITEM(S):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("no parameter/output drift between the manual and the live provider")
