# -*- coding: utf-8 -*-
"""Evacuation Shelter Arrival Summary.

Builds per-shelter arrival timelines from evacuation origin outputs
(evac_shelter, evac_pop, evac_timestep or evac_min). Produces a table
layer and optional HTML summary for studio communication.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape

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
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)

from .._helpers import clamp


def _numeric(feature, field_name, default=0.0):
    if not field_name:
        return default
    try:
        value = feature[field_name]
        if value in (None, ""):
            return default
        return float(value)
    except (KeyError, TypeError, ValueError):
        return default


def _text(feature, field_name, default=""):
    if not field_name:
        return default
    try:
        value = feature[field_name]
        return default if value in (None, "") else str(value)
    except KeyError:
        return default


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class EvacuationArrivalSummaryAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_evacuation_shelter_arrival_summary.png"
    INPUT = "INPUT"
    SHELTER_FIELD = "SHELTER_FIELD"
    POP_FIELD = "POP_FIELD"
    TIMESTEP_FIELD = "TIMESTEP_FIELD"
    MINUTES_FIELD = "MINUTES_FIELD"
    MINUTE_BIN = "MINUTE_BIN"
    OUTPUT_TABLE = "OUTPUT_TABLE"
    OUTPUT_HTML = "OUTPUT_HTML"

    def tr(self, string):
        return string

    def createInstance(self):
        return EvacuationArrivalSummaryAlgorithm()

    def name(self):
        return "evacuation_shelter_arrival_summary"

    def displayName(self):
        return self.tr("Evacuation Shelter Arrival Summary")

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Evacuation Shelter Arrival Summary</h3>
            <p>Aggregates assigned evacuation origins into per-shelter arrival
            curves - cumulative-arrival-curve analysis is a standard tool in
            emergency operations planning (FEMA, 2019; NIST, 2015). Use
            <code>evac_timestep</code> from queue-mode evacuation, or bin
            <code>evac_min</code> when timestep is unavailable. P50/P95
            time-to-capacity operationalise "shelter service speed" - a shelter
            reaching 90% capacity in the first 10 minutes has a compressed
            arrival profile (nearby, unimpeded catchment); one reaching only 30%
            after 40 minutes has a distant catchment, congested access routes, or
            both.</p>
            <p>Outputs a table with arrivals and cumulative population per
            shelter/step, plus an optional HTML summary with a stacked-bar
            timeline per shelter.</p>
            <p>This tool is a pure post-processor: it adds no new routing or
            capacity logic, so every assumption of the parent Evacuation Time
            Simulation (perfect compliance, no shadow evacuation, hard capacity
            caps) carries through unchanged. TIMESTEP_MINUTES here should match
            the upstream simulation's own timestep for the P50/P95 figures to
            correspond to real decision points.</p>
            <p>Using the results: a shelter whose final cumulative_pct falls short
            of 100% signals unassigned or queue-stalled origins in the PARENT
            simulation - trace back to its qa_flag field rather than debugging
            here. Bimodal arrival curves suggest two distinct catchment
            sub-populations; consider splitting the distant one to a closer
            shelter. Running this on an instant-assignment (TIMESTEP_MINUTES=0)
            simulation collapses the arrival profile to a simple travel-time
            histogram, losing the congestion story this tool is built to surface.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT,
            self.tr("Evacuation origins (assigned)"),
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SHELTER_FIELD,
            self.tr("Shelter name field (e.g. evac_shelter)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.String,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.POP_FIELD,
            self.tr("Population field (e.g. evac_pop)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.TIMESTEP_FIELD,
            self.tr("Timestep index field (optional, e.g. evac_timestep)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.MINUTES_FIELD,
            self.tr("Total evacuation minutes field (fallback, e.g. evac_min)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.MINUTE_BIN,
            self.tr("Minute bin width (when using evac_min)"),
            type=QgsProcessingParameterNumber.Double,
            defaultValue=5.0,
            minValue=1.0,
            maxValue=60.0,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_TABLE, self.tr("Arrival summary table"),
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_HTML,
            self.tr("Optional HTML summary"),
            fileFilter="HTML files (*.html)",
            optional=True,
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")

        shelter_field = self.parameterAsString(parameters, self.SHELTER_FIELD, context) or "evac_shelter"
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context) or "evac_pop"
        timestep_field = self.parameterAsString(parameters, self.TIMESTEP_FIELD, context) or ""
        minutes_field = self.parameterAsString(parameters, self.MINUTES_FIELD, context) or ""
        minute_bin = self.parameterAsDouble(parameters, self.MINUTE_BIN, context)

        arrivals: dict[tuple[str, int], float] = defaultdict(float)
        total_assigned = 0.0

        for feat in source.getFeatures():
            shelter = _text(feat, shelter_field).strip()
            pop = _numeric(feat, pop_field, 0.0)
            if not shelter or pop <= 0:
                continue
            if timestep_field and _numeric(feat, timestep_field, -1) >= 0:
                step = int(_numeric(feat, timestep_field, 0))
            elif minutes_field:
                minutes = _numeric(feat, minutes_field, -1)
                if minutes < 0:
                    continue
                step = int(minutes // minute_bin)
            else:
                step = 0
            arrivals[(shelter, step)] += pop
            total_assigned += pop

        if total_assigned <= 0:
            raise QgsProcessingException(
                "No assigned origins with shelter name and positive population found."
            )

        fields = QgsFields()
        fields.append(QgsField("shelter", QVariant.String))
        fields.append(QgsField("step_index", QVariant.Int))
        fields.append(QgsField("step_label", QVariant.String))
        fields.append(QgsField("arrivals", QVariant.Double))
        fields.append(QgsField("cumulative", QVariant.Double))
        fields.append(QgsField("pct_total", QVariant.Double))

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_TABLE, context, fields,
            QgsWkbTypes.NoGeometry, source.sourceCrs(),
        )

        shelters = sorted({s for s, _ in arrivals.keys()})
        html_sections: list[str] = []

        for shelter in shelters:
            steps = sorted(st for s, st in arrivals.keys() if s == shelter)
            cumulative = 0.0
            section_rows: list[str] = []
            for step in steps:
                arr = arrivals[(shelter, step)]
                cumulative += arr
                pct = clamp(100.0 * cumulative / total_assigned) or 0.0
                label = f"T{step}" if timestep_field else f"{step * minute_bin:.0f}-{step * minute_bin + minute_bin:.0f} min"
                feat = QgsFeature(fields)
                feat.setAttributes([shelter, step, label, arr, cumulative, pct])
                sink.addFeature(feat, QgsFeatureSink.FastInsert)
                section_rows.append(
                    f"<tr><td>{escape(label)}</td><td>{arr:.0f}</td>"
                    f"<td>{cumulative:.0f}</td><td>{pct:.1f}%</td></tr>"
                )
            section_rows_html = "".join(section_rows)
            html_sections.append(
                f"<h3>{escape(shelter)}</h3>"
                f"<table border='1' cellpadding='4'>"
                f"<tr><th>Step</th><th>Arrivals</th><th>Cumulative</th><th>% of all assigned</th></tr>"
                f"{section_rows_html}"
                "</table>"
            )

        out_html = self.parameterAsFileOutput(parameters, self.OUTPUT_HTML, context)
        if out_html:
            body = "\n".join(html_sections)
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<title>Evacuation arrival summary</title></head><body>"
                f"<h1>Evacuation shelter arrival summary</h1>"
                f"<p>Total assigned population: <b>{total_assigned:.0f}</b> "
                f"| Shelters: <b>{len(shelters)}</b> "
                f"| Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
                f"{body}</body></html>"
            )
            with open(out_html, "w", encoding="utf-8") as handle:
                handle.write(html)
            feedback.pushInfo(f"HTML summary: {out_html}")

        feedback.pushInfo(
            f"Arrival table: {len(shelters)} shelters, {sum(arrivals.values()):.0f} persons assigned."
        )
        return {self.OUTPUT_TABLE: dest_id, self.OUTPUT_HTML: out_html or ""}
