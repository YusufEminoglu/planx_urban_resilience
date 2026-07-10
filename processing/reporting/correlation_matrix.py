# -*- coding: utf-8 -*-
"""Multi-Hazard Correlation Matrix.

Computes pairwise Pearson and Spearman correlations between N numeric
score fields on the same layer (typically multiple hazard outputs already
joined to a planning-unit polygon). Output is a standalone HTML report
with a colour-coded heatmap, top correlations table, and per-pair
diagnostics — useful for spotting redundancy ("seismic and flood scores
move together in this city; pick one for the composite") or surprise
divergences.

Outputs:
  - HTML file on disk with the heatmap and tables.
  - In-QGIS sink (long-format table) so the matrix can be styled/joined
    later: rows are field_a / field_b / pearson_r / spearman_r / n.

Pure Python: no numpy / scipy dependency.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import math

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterString,
    QgsWkbTypes,
)


def _safe_float(value):
    try:
        v = float(value)
        if math.isnan(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho via Pearson on the rank vectors. Ties get average rank."""
    n = len(xs)
    if n < 3:
        return None

    def _ranks(arr):
        idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and arr[idx[j + 1]] == arr[idx[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0  # 1-based ranks
            for k in range(i, j + 1):
                ranks[idx[k]] = avg
            i = j + 1
        return ranks

    return _pearson(_ranks(xs), _ranks(ys))


def _r_color(r: float | None) -> str:
    if r is None:
        return "#f0f0f0"
    # diverging red (positive) / blue (negative)
    r = max(-1.0, min(1.0, r))
    if r >= 0:
        t = r
        rr = int(255 - t * (255 - 178))
        gg = int(255 - t * (255 - 24))
        bb = int(255 - t * (255 - 43))
    else:
        t = -r
        rr = int(255 - t * (255 - 33))
        gg = int(255 - t * (255 - 102))
        bb = int(255 - t * (255 - 172))
    return f"#{rr:02x}{gg:02x}{bb:02x}"


def _interpret(r: float | None) -> str:
    if r is None:
        return "—"
    a = abs(r)
    sign = "+" if r >= 0 else "−"
    if a >= 0.7:
        strength = "strong"
    elif a >= 0.4:
        strength = "moderate"
    elif a >= 0.2:
        strength = "weak"
    else:
        strength = "negligible"
    return f"{sign} {strength}"


from .._mixins import HelpUrlMixin  # noqa: E402


class CorrelationMatrixAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    INPUT = "INPUT"
    FIELDS = "FIELDS"
    PROJECT = "PROJECT"
    OUTPUT_HTML = "OUTPUT_HTML"
    OUTPUT_TABLE = "OUTPUT_TABLE"

    def tr(self, string):
        return string

    def createInstance(self):
        return CorrelationMatrixAlgorithm()

    def name(self):
        return "multi_hazard_correlation_matrix"

    def displayName(self):
        return self.tr("Multi-Hazard Correlation Matrix (HTML + table)")

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Multi-Hazard Correlation Matrix</h3>
            <p>Pairwise Pearson and Spearman correlations between N
            numeric score fields on the same layer. Output is a
            standalone HTML report with a colour-coded heatmap, top
            correlations table, and per-pair diagnostics.</p>
            <p>Use case: spot redundancy in a composite ("seismic and
            flood already move together in this city") or surprise
            divergences ("heat is uncorrelated with everything else").</p>
            <p>Also returns a long-format table (field_a / field_b /
            pearson_r / spearman_r / n_pairs) for further joining or
            styling.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Layer with multiple numeric score fields"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.FIELDS, self.tr("Numeric score fields (pick 2-12)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            allowMultiple=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PROJECT, self.tr("Project / study name (optional)"),
            defaultValue="", optional=True,
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_HTML, self.tr("Output HTML report"),
            fileFilter="HTML (*.html *.htm)",
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_TABLE, self.tr("Long-format correlation table")
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        fields = self.parameterAsFields(parameters, self.FIELDS, context) or []
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        if len(fields) < 2:
            raise QgsProcessingException("Pick at least two numeric fields.")
        if len(fields) > 12:
            raise QgsProcessingException("Pick at most 12 fields (the heatmap stops being readable).")
        project_name = self.parameterAsString(parameters, self.PROJECT, context) or ""
        out_html = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)

        # Collect values column-by-column with per-feature index, so we can
        # pair-wise drop missing values cleanly (different pairs may have
        # different valid-N counts).
        columns: dict[str, list[float | None]] = {f: [] for f in fields}
        n_features = 0
        for feat in source.getFeatures():
            n_features += 1
            for f in fields:
                columns[f].append(_safe_float(feat.attribute(f)))
        feedback.pushInfo(f"Loaded {n_features} features for {len(fields)} fields.")

        # Build long-format table sink.
        table_fields = QgsFields()
        table_fields.append(QgsField("field_a", QVariant.String))
        table_fields.append(QgsField("field_b", QVariant.String))
        table_fields.append(QgsField("pearson_r", QVariant.Double))
        table_fields.append(QgsField("spearman_r", QVariant.Double))
        table_fields.append(QgsField("n_pairs", QVariant.Int))
        (table_sink, table_id) = self.parameterAsSink(
            parameters, self.OUTPUT_TABLE, context, table_fields,
            QgsWkbTypes.NoGeometry, source.sourceCrs(),
        )

        pearson_mat: dict[tuple[str, str], float | None] = {}
        spearman_mat: dict[tuple[str, str], float | None] = {}
        n_pairs: dict[tuple[str, str], int] = {}
        pair_list: list[tuple[str, str, float | None, float | None, int]] = []

        for i, fa in enumerate(fields):
            for j, fb in enumerate(fields):
                xs: list[float] = []
                ys: list[float] = []
                for k in range(n_features):
                    va = columns[fa][k]
                    vb = columns[fb][k]
                    if va is not None and vb is not None:
                        xs.append(va)
                        ys.append(vb)
                if fa == fb:
                    p = 1.0
                    s = 1.0
                else:
                    p = _pearson(xs, ys)
                    s = _spearman(xs, ys)
                pearson_mat[(fa, fb)] = p
                spearman_mat[(fa, fb)] = s
                n_pairs[(fa, fb)] = len(xs)
                if j > i:  # store upper triangle only in the long table
                    pair_list.append((fa, fb, p, s, len(xs)))
                    new_feat = QgsFeature(table_fields)
                    new_feat.setAttributes([
                        fa, fb,
                        None if p is None else round(p, 6),
                        None if s is None else round(s, 6),
                        len(xs),
                    ])
                    table_sink.addFeature(new_feat, QgsFeatureSink.FastInsert)

        # Top correlations (by |Pearson r|).
        ranked = sorted(
            (p for p in pair_list if p[2] is not None),
            key=lambda r: -abs(r[2]),
        )[:10]

        # ── HTML render ────────────────────────────────────────────────
        rows: list[str] = []
        rows.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
        rows.append("<title>Multi-Hazard Correlation Matrix</title>")
        rows.append(
            "<style>"
            "body{font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#243044;"
            "max-width:1100px;margin:24px auto;padding:0 20px;}"
            "h1{color:#0f766e;margin-bottom:4px;}"
            ".meta{color:#64748b;margin-bottom:18px;}"
            "table.cm{border-collapse:collapse;margin:14px 0;}"
            "table.cm th,table.cm td{padding:8px 12px;border:1px solid #d8e0ea;text-align:center;"
            "font-variant-numeric:tabular-nums;}"
            "table.cm th{background:#eef6f4;font-weight:600;}"
            "table.top{border-collapse:collapse;margin:14px 0;}"
            "table.top th,table.top td{padding:6px 12px;border-bottom:1px solid #d8e0ea;text-align:left;}"
            "table.top th{background:#eef6f4;}"
            ".legend{display:flex;align-items:center;gap:6px;font-size:13px;color:#445;}"
            ".swatch{display:inline-block;width:16px;height:16px;border:1px solid #999;}"
            "</style></head><body>"
        )
        rows.append("<h1>Multi-Hazard Correlation Matrix</h1>")
        meta_parts = []
        if project_name:
            meta_parts.append(f"<b>Project:</b> {_html.escape(project_name)}")
        meta_parts.append(f"<b>Features:</b> {n_features}")
        meta_parts.append(f"<b>Fields:</b> {len(fields)}")
        meta_parts.append(f"<b>Generated:</b> {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        rows.append(f"<p class='meta'>{' &nbsp;|&nbsp; '.join(meta_parts)}</p>")

        rows.append(
            "<p class='legend'>Heatmap: "
            "<span class='swatch' style='background:#2166ac;'></span> strong −1  "
            "<span class='swatch' style='background:#ffffff;'></span> 0  "
            "<span class='swatch' style='background:#b2182b;'></span> strong +1"
            "</p>"
        )

        # Pearson heatmap.
        rows.append("<h2>Pearson r</h2><table class='cm'><tr><th></th>")
        for f in fields:
            rows.append(f"<th>{_html.escape(f)}</th>")
        rows.append("</tr>")
        for fa in fields:
            rows.append(f"<tr><th>{_html.escape(fa)}</th>")
            for fb in fields:
                r = pearson_mat[(fa, fb)]
                bg = _r_color(r)
                txt = "—" if r is None else f"{r:.2f}"
                rows.append(f"<td style='background:{bg};'>{txt}</td>")
            rows.append("</tr>")
        rows.append("</table>")

        # Spearman heatmap.
        rows.append("<h2>Spearman ρ (rank)</h2><table class='cm'><tr><th></th>")
        for f in fields:
            rows.append(f"<th>{_html.escape(f)}</th>")
        rows.append("</tr>")
        for fa in fields:
            rows.append(f"<tr><th>{_html.escape(fa)}</th>")
            for fb in fields:
                r = spearman_mat[(fa, fb)]
                bg = _r_color(r)
                txt = "—" if r is None else f"{r:.2f}"
                rows.append(f"<td style='background:{bg};'>{txt}</td>")
            rows.append("</tr>")
        rows.append("</table>")

        # Top correlations.
        rows.append("<h2>Top correlations (by |Pearson r|)</h2>")
        rows.append("<table class='top'><tr><th>#</th><th>A</th><th>B</th>"
                    "<th>Pearson r</th><th>Spearman ρ</th><th>n</th><th>Strength</th></tr>")
        for i, (a, b, p, s, n) in enumerate(ranked, start=1):
            rows.append(
                f"<tr><td>{i}</td><td>{_html.escape(a)}</td><td>{_html.escape(b)}</td>"
                f"<td>{'—' if p is None else f'{p:.3f}'}</td>"
                f"<td>{'—' if s is None else f'{s:.3f}'}</td>"
                f"<td>{n}</td><td>{_interpret(p)}</td></tr>"
            )
        rows.append("</table>")

        rows.append("<hr><p style='color:#64748b;font-size:12px;'>"
                    "Generated by PlanX Urban Resilience — Multi-Hazard Correlation Matrix module."
                    "</p>")
        rows.append("</body></html>")

        with open(out_html, "w", encoding="utf-8", newline="\n") as fp:
            fp.write("\n".join(rows))
        feedback.pushInfo(f"Wrote HTML report: {out_html}")
        return {self.OUTPUT_HTML: out_html, self.OUTPUT_TABLE: table_id}
