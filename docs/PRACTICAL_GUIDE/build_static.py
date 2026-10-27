#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the print / PDF edition of the Urban Resilience Practical Guide.

Reads the same registry and screenshot manifests as ``build_final.py`` but
writes a static, script-free document: one section per tool, with the 4-panel
screenshot inlined so the file prints (and exports to PDF) without a server.

    python build_static.py
"""
from __future__ import annotations

import base64
import html
import json
from datetime import date
import os
from pathlib import Path

GUIDE = Path(__file__).resolve().parent
# The public manual lives in the portal repository (geophilo_project), not
# in this plugin repository or its Hub zip. GEOPHILO_MANUALS overrides it.
MANUALS = Path(os.environ.get("GEOPHILO_MANUALS") or GUIDE.parents[1].parents[1] / "geophilo_project" / "_manual_sources") / "planx_urban_resilience" / "PRACTICAL_GUIDE"
SHOT = GUIDE / "screenshots"
MAN = GUIDE / "manifest"

with open(MAN / "algorithms_detailed.json", encoding="utf-8") as f:
    registry = json.load(f)
with open(MAN / "screenshots_all.json", encoding="utf-8") as f:
    run_summary = json.load(f)

results = run_summary.get("results", {})
details = registry.get("algo_details", {})
groups_map = registry.get("groups", {})

E = html.escape


def b64(path: Path):
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return None


def clean(text: str) -> str:
    import re
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|table)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'"))
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def param_table(params, kind):
    if not params:
        return "<p><em>None.</em></p>"
    head = ("Output", "Label", "Type", "Format") if kind == "out" else \
           ("Parameter", "Label", "Type", "Default")
    h = ("<table class='param-table'><thead><tr>"
         + "".join(f"<th>{E(c)}</th>" for c in head)
         + "</tr></thead><tbody>")
    for p in params:
        default = p.get("default")
        default = "" if default is None else str(default)
        extra = p.get("extension", "") if kind == "out" else ""
        h += (f"<tr><td><code>{E(p['name'])}</code></td>"
              f"<td>{E(p.get('label', ''))}</td>"
              f"<td>{E(p.get('type', ''))}</td>"
              f"<td>{E(default)}{E(' · ' + extra if extra else '')}</td></tr>")
    return h + "</tbody></table>"


def build():
    toc = []
    body = []
    for order, (gname, ids) in enumerate(groups_map.items()):
        toc.append(f"<li><a href='#group-{order + 1}'>{E(gname)} ({len(ids)})</a></li>")
        body.append(f"<h2 id='group-{order + 1}'>{E(gname)} ({len(ids)})</h2>")
        for aid in ids:
            det = details.get(aid)
            if not det:
                continue
            run = results.get(aid, {})
            png = SHOT / aid / f"{aid}_4panel.png"
            payload = b64(png)
            block = ["<div class='algo-block'>"]
            block.append(f"<div class='algo-title'>{E(det.get('display_name', aid))} "
                         f"<code>({E(aid)})</code></div>")
            block.append(f"<div class='algo-meta'>Group: {E(det.get('group', ''))} · "
                         f"Processing ID: <code>{E(det.get('group_id', ''))}:"
                         f"{E(aid)}</code>")
            if run.get("seconds") is not None:
                block.append(f" · run time {E(str(run['seconds']))} s")
            block.append("</div>")

            if payload:
                block.append(
                    "<figure class='shot'>"
                    f"<img src='data:image/png;base64,{payload}' alt='"
                    f"{E(det.get('display_name', aid))} four panel screenshot'>"
                    "<figcaption>Four-panel view: top left input data · top right raw "
                    "output · bottom left styled output · bottom right the parameter "
                    "values used in the captured run.</figcaption></figure>")

            block.append("<div class='section'><div class='section-title'>"
                         "Help summary</div><div class='help-text'>"
                         + E(clean(det.get("help_summary", ""))) + "</div></div>")

            block.append("<div class='section'><div class='section-title'>"
                         "Input parameters</div>" + param_table(det.get("parameters", []), "in")
                         + "</div>")
            block.append("<div class='section'><div class='section-title'>"
                         "Outputs</div>" + param_table(det.get("outputs", []), "out")
                         + "</div>")

            rp = run.get("params", {})
            if rp:
                rows = "".join(
                    f"<tr><td><code>{E(k)}</code></td><td>{E(str(v))}</td></tr>"
                    for k, v in rp.items())
                block.append("<div class='section'><div class='section-title'>"
                             "Values used in the captured run</div><table><tbody>"
                             + rows + "</tbody></table></div>")
            body.append("".join(block) + "</div>")

    template = (MANUALS / "template_en.html").read_text(encoding="utf-8")
    out = (template
           .replace("{{CONTENT}}", "\n".join(body))
           .replace("{{TOC}}", "\n".join(toc))
           .replace("{{EDITION}}", date.today().isoformat())
           .replace("{{ALGO_COUNT}}", str(len(details)))
           .replace("{{GROUP_COUNT}}", str(len(groups_map))))

    MANUALS.mkdir(parents=True, exist_ok=True)
    target = MANUALS / "practical_guide_static.html"
    target.write_text(out, encoding="utf-8")
    print(f"[OK] {target.name}: {target.stat().st_size / 1024:.0f} kB, "
          f"{len(details)} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
