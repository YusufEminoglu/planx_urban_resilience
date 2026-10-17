# -*- coding: utf-8 -*-
"""Recommended Actions Report.

Reads a scored layer (with optional class + dominant-hazard fields) and
produces a Markdown report grouping units by risk class, listing the top
units and pulling a standard intervention catalogue per hazard family.

The intervention catalogue is built-in (no external lookup), drawn from
common urban-resilience planning practice. Output is plain Markdown so
planners can paste it into reports, wikis, or the studio brief module.
"""
from __future__ import annotations

import datetime as _dt
import math

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)


# Hazard family → ordered list of common interventions. Keys are normalised
# (lowercased substring matches). Unknown hazards fall back to GENERIC.
INTERVENTION_CATALOG = {
    "heat": [
        "Increase tree-canopy cover (target 30%+ on streets and squares).",
        "Light-coloured / high-albedo pavement and rooftops in hot corridors.",
        "Cooling refuges within 300 m of every residential cluster.",
        "Operating hours adjustment for outdoor workers during heat alerts.",
    ],
    "flood": [
        "Permeable pavement and bio-swales along low-lying corridors.",
        "Detention / retention basins at upstream catchments.",
        "Building-floor elevation requirements for new permits.",
        "Drainage capacity upgrade where bottlenecks coincide with hot spots.",
    ],
    "seism": [
        "Structural retrofit programme for pre-2000 buildings.",
        "Emergency-access corridor protection (no debris-source frontages).",
        "Designated assembly areas + signed evacuation routes.",
        "Critical-facility seismic upgrade (schools, hospitals, fire stations).",
    ],
    "social": [
        "Community-resilience hubs with multilingual outreach.",
        "Targeted preparedness campaigns for elderly / disability / low-income.",
        "Local volunteer-network formalisation and training.",
        "Cash-transfer-readiness for post-disaster recovery acceleration.",
    ],
    "air": [
        "Low-emission zone or traffic calming in exposed corridors.",
        "Vegetative buffers between traffic and sensitive land uses.",
        "Indoor air-quality upgrades in schools, clinics, elderly homes.",
        "Real-time monitoring + neighbourhood-level advisory system.",
    ],
    "drought": [
        "Drought-tolerant plant palette + native species in greening projects.",
        "Greywater reuse for park irrigation.",
        "Permeable surfaces and rain-gardens to support local infiltration.",
        "Tree-canopy maintenance schedule prioritising vulnerable patches.",
    ],
    "emergency": [
        "Add or relocate a shelter / safe-assembly area within range.",
        "Upgrade road segments flagged as bottlenecks (Network Criticality).",
        "Establish redundant access corridors to underserved clusters.",
        "Procurement of mobile emergency assets for last-mile coverage.",
    ],
    "wildfire": [
        "Enforce 30-100 m defensible-space fuel breaks along WUI parcel boundaries.",
        "Mandate ember-resistant roofing, vents, and non-combustible siding in WUI zones.",
        "Establish secondary emergency egress roads for single-outlet hillside neighbourhoods.",
        "Thin high-slope brush and crown fuels upslope of residential clusters.",
    ],
    "coastal": [
        "Living shorelines, salt-marsh restoration, and dune nourishment buffers.",
        "Raise minimum finished-floor freeboard above projected SLR + 100-yr storm surge.",
        "Install tidal backflow preventers on coastal stormwater outfalls.",
        "Designate rolling-easement or managed-retreat corridors in connected low-lying zones.",
    ],
}

GENERIC_INTERVENTIONS = [
    "Engage the local stakeholder group and ground-truth the assessment.",
    "Commission detailed (engineering-grade) studies for top-priority units.",
    "Integrate findings into the next planning revision cycle.",
    "Set a measurable target and re-run the analysis after 1–2 years.",
]


def _normalise_hazard(label: str) -> str:
    if not label:
        return ""
    s = label.lower()
    if "wui" in s or "fire" in s:
        return "wildfire"
    if "slr" in s or "coast" in s or "surge" in s:
        return "coastal"
    # Map common variants to catalogue keys.
    for key in INTERVENTION_CATALOG:
        if key in s:
            return key
    return ""


def _class_emoji(cls: str) -> str:
    cls = (cls or "").lower()
    if "very high" in cls:
        return "🟥"
    if "high" in cls:
        return "🟧"
    if "moderate" in cls:
        return "🟨"
    if "low" in cls:
        return "🟩"
    return "⬜"


from .._mixins import GROUP_REPORT, GroupMixin, HelpUrlMixin  # noqa: E402


class RecommendedActionsAlgorithm(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
    GROUP = GROUP_REPORT
    ICON = "tool_recommended_actions_report.png"
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    CLASS_FIELD = "CLASS_FIELD"
    HAZARD_FIELD = "HAZARD_FIELD"
    UNIT_NAME_FIELD = "UNIT_NAME_FIELD"
    TOP_N = "TOP_N"
    PROJECT = "PROJECT"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return RecommendedActionsAlgorithm()

    def name(self):
        return "recommended_actions_report"

    def displayName(self):
        return self.tr("Recommended Actions Report (Markdown)")

    def shortHelpString(self):
        return self.tr(
            "<h3>Recommended Actions Report</h3> <p>Reads a scored layer with optional class and "
            "dominant-hazard fields, then produces a Markdown report that:</p> <ul> <li>summarises "
            "score distribution per class,</li> <li>lists the top N highest-scored units,</li> "
            "<li>pulls a curated intervention list per detected hazard family from a built-in "
            "catalogue.</li> </ul> <p>Catalogue currently covers heat, flood, seismic, social, air, "
            "drought and emergency-access. Unknown hazards fall back to a generic checklist.</p> "
            "<p>Hazard-family detection is a transparent, auditable case-insensitive substring match "
            'against the dominant-hazard field (e.g. any value containing "flood" maps to the flood '
            "catalogue) - not a fuzzy classifier. A field using unexpected terminology (e.g. "
            '"inundation" instead of "flood") will not match and falls back to generic. Only ONE '
            "dominant hazard per unit drives the checklist, even for units facing several comparably "
            "severe hazards.</p> <p>The catalogue is fixed and identical for every project - it has "
            "no awareness of local context, budget, or regulatory environment; every item "
            '("structural retrofit programme", "bioswales along low-lying corridors") is a generic '
            "category needing local design and feasibility work, not a costed proposal.</p> <p>Using "
            "the results: if every unit falls back to the generic checklist, check the "
            "dominant-hazard field's actual text values against the catalogue keys (heat, flood, "
            "seism, social, air, drought, emergency) - a terminology mismatch is the most common "
            "cause. Use the checklists to facilitate a stakeholder workshop discussion, not as a "
            "ranked or prioritised recommendation.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored layer"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SCORE_FIELD, self.tr("Score field (0-100, numeric)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CLASS_FIELD, self.tr("Class field (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.String, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.HAZARD_FIELD, self.tr("Dominant-hazard field (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.String, optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.UNIT_NAME_FIELD, self.tr("Unit name / label field (optional)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Any, optional=True,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.TOP_N, self.tr("Top N units to list"),
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=10, minValue=1, maxValue=200,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PROJECT, self.tr("Project / study area name (optional)"),
            defaultValue="", optional=True,
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, self.tr("Output Markdown file"),
            fileFilter="Markdown (*.md)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context) or ""
        hazard_field = self.parameterAsString(parameters, self.HAZARD_FIELD, context) or ""
        unit_name_field = self.parameterAsString(parameters, self.UNIT_NAME_FIELD, context) or ""
        top_n = self.parameterAsInt(parameters, self.TOP_N, context)
        project_name = self.parameterAsString(parameters, self.PROJECT, context) or ""
        out_path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        if not out_path:
            raise QgsProcessingException("Output Markdown path is required.")

        rows: list = []
        class_counts: dict = {}
        hazard_counts: dict = {}
        for feat in source.getFeatures():
            try:
                score = float(feat.attribute(score_field))
            except (TypeError, ValueError):
                continue
            if math.isnan(score):
                continue
            cls = feat.attribute(class_field) if class_field else ""
            haz = feat.attribute(hazard_field) if hazard_field else ""
            name = feat.attribute(unit_name_field) if unit_name_field else f"fid={feat.id()}"
            rows.append((score, str(name), str(cls or ""), str(haz or "")))
            if cls:
                class_counts[str(cls)] = class_counts.get(str(cls), 0) + 1
            if haz:
                hazard_counts[str(haz)] = hazard_counts.get(str(haz), 0) + 1

        if not rows:
            raise QgsProcessingException(
                "No numeric scores found in the chosen field."
            )

        rows.sort(key=lambda r: -r[0])
        top = rows[:top_n]
        timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

        lines: list[str] = []
        lines.append("# Recommended Actions Report")
        if project_name:
            lines.append(f"**Project:** {project_name}")
        lines.append(f"**Score field:** `{score_field}`  ")
        lines.append(f"**Units analysed:** {len(rows)}  ")
        lines.append(f"**Generated:** {timestamp}")
        lines.append("")

        # Class distribution.
        if class_counts:
            lines.append("## Distribution by class")
            lines.append("")
            lines.append("| Class | Units | Share |")
            lines.append("|-------|------:|------:|")
            total = sum(class_counts.values())
            for cls, count in sorted(class_counts.items(), key=lambda x: -x[1]):
                pct = (100.0 * count / total) if total > 0 else 0.0
                lines.append(f"| {_class_emoji(cls)} {cls} | {count} | {pct:.1f}% |")
            lines.append("")

        # Top units.
        lines.append(f"## Top {len(top)} units by score")
        lines.append("")
        header = ["#", "Unit", "Score"]
        if class_field:
            header.append("Class")
        if hazard_field:
            header.append("Dominant hazard")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for i, (score, name, cls, haz) in enumerate(top, start=1):
            row = [str(i), name, f"{score:.2f}"]
            if class_field:
                row.append(f"{_class_emoji(cls)} {cls}")
            if hazard_field:
                row.append(haz or "—")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

        # Per-hazard interventions.
        lines.append("## Recommended interventions")
        lines.append("")
        seen_keys: set = set()
        if hazard_counts:
            ordered = sorted(hazard_counts.items(), key=lambda x: -x[1])
            for haz_label, _count in ordered:
                key = _normalise_hazard(haz_label)
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                lines.append(f"### {haz_label.title()} → {key} catalogue")
                lines.append("")
                for item in INTERVENTION_CATALOG[key]:
                    lines.append(f"- {item}")
                lines.append("")
        # If no hazard field, or no matches at all, fall back to generic.
        if not seen_keys:
            lines.append("### Generic catalogue (no hazard field matched)")
            lines.append("")
            for item in GENERIC_INTERVENTIONS:
                lines.append(f"- {item}")
            lines.append("")
        else:
            lines.append("### Cross-cutting actions")
            lines.append("")
            for item in GENERIC_INTERVENTIONS:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by PlanX Urban Resilience — Recommended Actions Report module.*")
        lines.append("")

        with open(out_path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write("\n".join(lines))

        feedback.pushInfo(f"Wrote Markdown report: {out_path}")
        return {self.OUTPUT: out_path}
