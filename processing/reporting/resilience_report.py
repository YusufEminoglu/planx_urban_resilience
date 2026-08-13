# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterString,
)


def _numeric(feature, field_name):
    if not field_name:
        return None
    try:
        value = feature[field_name]
        if value in (None, ""):
            return None
        return float(value)
    except (KeyError, TypeError, ValueError):
        return None


def _value(feature, field_name):
    if not field_name:
        return ""
    try:
        value = feature[field_name]
        return "" if value is None else str(value)
    except KeyError:
        return ""


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class ResilienceReportAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_resilience_score_html_report.png"
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    CLASS_FIELD = "CLASS_FIELD"
    DRIVER_FIELD = "DRIVER_FIELD"
    TITLE = "TITLE"
    OUTPUT_HTML = "OUTPUT_HTML"

    def tr(self, string):
        return string

    def createInstance(self):
        return ResilienceReportAlgorithm()

    def name(self):
        return "resilience_score_html_report"

    def displayName(self):
        return self.tr("Resilience Score HTML Report")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Resilience Score HTML Report</h3>
            <p>Exports a compact, self-contained HTML summary from any polygon or
            point layer with a 0-100 score field: summary cards (feature count,
            average, range, high-priority count), a class-distribution table, and
            a top-drivers table. Front-loads the headline numbers before any table,
            following standard technical-communication practice (Tufte, 1983) - a
            reader gets the essentials in the first few seconds.</p>
            <p>This is a mirror of the source layer's current field values, not an
            independent analysis - it re-runs no upstream algorithm, so any
            upstream error shows up here unchanged, and the file goes stale if the
            source layer is later edited. Driver/notes text is split on commas and
            semicolons; a different separator won't tally correctly. The
            high-priority threshold (&gt;=55) is hard-coded to this suite's
            standard risk-class convention.</p>
            <p>Using the results: a large "missing score values" count is itself a
            data-quality finding, not just a footnote. Use this for a quick,
            shareable, no-QGIS-required summary; where narrative prose is needed
            instead of cards and tables, use Resilience Studio Brief, which
            generates full sections around the same underlying statistics.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Scored layer"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(self.SCORE_FIELD, self.tr("Score field"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterField(self.CLASS_FIELD, self.tr("Class field (optional)"), parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterField(self.DRIVER_FIELD, self.tr("Driver / notes field (optional)"), parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterString(self.TITLE, self.tr("Report title"), defaultValue="PlanX Urban Resilience Report"))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_HTML, self.tr("HTML report"), fileFilter="HTML files (*.html)"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context)
        driver_field = self.parameterAsString(parameters, self.DRIVER_FIELD, context)
        title = self.parameterAsString(parameters, self.TITLE, context)
        output = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)

        scores = []
        classes = Counter()
        drivers = Counter()
        feature_count = 0
        missing_scores = 0
        for feature in source.getFeatures():
            feature_count += 1
            score = _numeric(feature, score_field)
            if score is None:
                missing_scores += 1
            else:
                scores.append(score)
            class_value = _value(feature, class_field)
            if class_value:
                classes[class_value] += 1
            driver_value = _value(feature, driver_field)
            if driver_value:
                for part in driver_value.replace(";", ",").split(","):
                    label = part.strip()
                    if label:
                        drivers[label] += 1

        average = sum(scores) / len(scores) if scores else 0.0
        minimum = min(scores) if scores else 0.0
        maximum = max(scores) if scores else 0.0
        high_count = sum(1 for score in scores if score >= 55.0)

        class_rows = "\n".join(
            f"<tr><td>{escape(str(label))}</td><td>{count}</td></tr>"
            for label, count in classes.most_common()
        ) or "<tr><td>No class field selected</td><td>0</td></tr>"
        driver_rows = "\n".join(
            f"<tr><td>{escape(str(label))}</td><td>{count}</td></tr>"
            for label, count in drivers.most_common(12)
        ) or "<tr><td>No driver field selected</td><td>0</td></tr>"

        html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #213547; }}
    h1 {{ margin-bottom: 4px; }}
    .muted {{ color: #667085; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin: 24px 0; }}
    .card {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 14px; background: #f8fafc; }}
    .value {{ font-size: 24px; font-weight: 700; color: #0f766e; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; text-align: left; padding: 8px; }}
    th {{ background: #f1f5f9; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="muted">Generated by PlanX Urban Resilience on {datetime.now().strftime('%Y-%m-%d %H:%M')}.</p>
  <div class="cards">
    <div class="card"><div class="value">{feature_count}</div><div>Features</div></div>
    <div class="card"><div class="value">{average:.1f}</div><div>Average score</div></div>
    <div class="card"><div class="value">{minimum:.1f}-{maximum:.1f}</div><div>Score range</div></div>
    <div class="card"><div class="value">{high_count}</div><div>High priority (>=55)</div></div>
  </div>
  <h2>Class Distribution</h2>
  <table><thead><tr><th>Class</th><th>Count</th></tr></thead><tbody>{class_rows}</tbody></table>
  <h2>Top Drivers / Notes</h2>
  <table><thead><tr><th>Driver</th><th>Count</th></tr></thead><tbody>{driver_rows}</tbody></table>
  <p class="muted">Missing score values: {missing_scores}. This report is a planning-support summary and should be reviewed with the source layer and local knowledge.</p>
</body>
</html>
"""
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(html)
        feedback.pushInfo(f"HTML report written to {output}")
        return {self.OUTPUT_HTML: output}
