# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter
from datetime import datetime

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


def _text(feature, field_name):
    if not field_name:
        return ""
    try:
        value = feature[field_name]
        return "" if value is None else str(value)
    except KeyError:
        return ""


class StudioBriefAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    CLASS_FIELD = "CLASS_FIELD"
    DRIVER_FIELD = "DRIVER_FIELD"
    TITLE = "TITLE"
    STUDY_CONTEXT = "STUDY_CONTEXT"
    OUTPUT_MD = "OUTPUT_MD"

    def tr(self, string):
        return string

    def createInstance(self):
        return StudioBriefAlgorithm()

    def name(self):
        return "resilience_studio_brief_markdown"

    def displayName(self):
        return self.tr("Resilience Studio Brief (Markdown)")

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Resilience Studio Brief</h3>
            <p>Creates a Markdown brief from a scored resilience layer. The output is designed as a first draft for studio submissions, internal notes, or stakeholder memos.</p>
            <p>It summarizes key score metrics, class distribution, dominant drivers, limitations, and recommended next actions.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr("Scored layer"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(self.SCORE_FIELD, self.tr("Score field"), parentLayerParameterName=self.INPUT, type=QgsProcessingParameterField.Numeric))
        self.addParameter(QgsProcessingParameterField(self.CLASS_FIELD, self.tr("Class field (optional)"), parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterField(self.DRIVER_FIELD, self.tr("Driver / notes field (optional)"), parentLayerParameterName=self.INPUT, optional=True))
        self.addParameter(QgsProcessingParameterString(self.TITLE, self.tr("Brief title"), defaultValue="PlanX Urban Resilience Studio Brief"))
        self.addParameter(QgsProcessingParameterString(self.STUDY_CONTEXT, self.tr("Study context"), defaultValue="Planning-support screening based on QGIS layers and PlanX Urban Resilience outputs.", multiLine=True))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_MD, self.tr("Markdown brief"), fileFilter="Markdown files (*.md)"))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context)
        driver_field = self.parameterAsString(parameters, self.DRIVER_FIELD, context)
        title = self.parameterAsString(parameters, self.TITLE, context)
        study_context = self.parameterAsString(parameters, self.STUDY_CONTEXT, context)
        output = self.parameterAsFileOutput(parameters, self.OUTPUT_MD, context)

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
            cls = _text(feature, class_field)
            if cls:
                classes[cls] += 1
            driver_text = _text(feature, driver_field)
            if driver_text:
                for part in driver_text.replace(";", ",").split(","):
                    label = part.strip()
                    if label:
                        drivers[label] += 1

        average = sum(scores) / len(scores) if scores else 0.0
        minimum = min(scores) if scores else 0.0
        maximum = max(scores) if scores else 0.0
        high_count = sum(1 for score in scores if score >= 55.0)
        high_share = (high_count / len(scores) * 100.0) if scores else 0.0

        class_lines = "\n".join(f"- {label}: {count}" for label, count in classes.most_common()) or "- No class field selected."
        driver_lines = "\n".join(f"- {label}: {count}" for label, count in drivers.most_common(10)) or "- No driver field selected."
        action_lines = []
        if average >= 55:
            action_lines.append("- Prioritize the highest scoring areas for near-term adaptation or mitigation design.")
        else:
            action_lines.append("- Maintain monitoring and focus detailed design on local high-score clusters.")
        if high_count:
            action_lines.append("- Review high-priority features against land ownership, vulnerable users, and implementation feasibility.")
        if drivers:
            action_lines.append("- Use the dominant driver list to frame intervention packages and stakeholder discussion.")
        action_lines.append("- Validate results with field observation, local data owners, and discipline-specific analysis where needed.")

        markdown = f"""# {title}

Generated by PlanX Urban Resilience on {datetime.now().strftime('%Y-%m-%d %H:%M')}.

## Study Context

{study_context}

## Executive Summary

The analysis layer contains **{feature_count}** features. The selected score field is `{score_field}`. The average score is **{average:.1f}** on a 0-100 scale, with values ranging from **{minimum:.1f}** to **{maximum:.1f}**. A total of **{high_count}** scored features (**{high_share:.1f}%**) are at or above the high-priority threshold of 55.

## Key Metrics

| Metric | Value |
| --- | ---: |
| Features | {feature_count} |
| Valid scores | {len(scores)} |
| Missing scores | {missing_scores} |
| Average score | {average:.1f} |
| Minimum score | {minimum:.1f} |
| Maximum score | {maximum:.1f} |
| High-priority features (>=55) | {high_count} |

## Class Distribution

{class_lines}

## Dominant Drivers / Notes

{driver_lines}

## Suggested Next Actions

{chr(10).join(action_lines)}

## Limitations

- This brief is generated from a screening layer and should not be read as an engineering-grade model output.
- Scores depend on input data quality, CRS consistency, layer completeness, and field definitions.
- Local knowledge, field checks, and discipline-specific models should be used before final decisions.
- The brief is a first draft for planning communication; edit the narrative before publication.
"""
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(markdown)
        feedback.pushInfo(f"Markdown brief written to {output}")
        return {self.OUTPUT_MD: output}
