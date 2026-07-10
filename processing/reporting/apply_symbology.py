# -*- coding: utf-8 -*-
from __future__ import annotations

from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsGraduatedSymbolRenderer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterVectorLayer,
    QgsRendererCategory,
    QgsRendererRange,
    QgsSymbol,
)


RISK_COLORS = [
    (0.0, 35.0, "Low", "#2A9D8F"),
    (35.0, 55.0, "Moderate", "#E9C46A"),
    (55.0, 75.0, "High", "#F4A261"),
    (75.0, 100.0, "Very High", "#D62828"),
]

ACCESS_COLORS = [
    ("Covered", "#2A9D8F"),
    ("Watch", "#E9C46A"),
    ("Underserved", "#F4A261"),
    ("Critical", "#D62828"),
    ("Unreachable", "#6B7280"),
]

CHANGE_COLORS = [
    ("Improved", "#2A9D8F"),
    ("Stable", "#94A3B8"),
    ("Worsened", "#D62828"),
]

PRIORITY_COLORS = [
    ("Monitor", "#2A9D8F"),
    ("Medium", "#E9C46A"),
    ("High", "#F4A261"),
    ("Immediate", "#D62828"),
]


def _symbol(layer, color, opacity=0.78):
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(QColor(color))
    symbol.setOpacity(opacity)
    return symbol


def _category_renderer(layer, field_name, categories):
    renderer_categories = []
    for value, color in categories:
        renderer_categories.append(QgsRendererCategory(value, _symbol(layer, color), str(value)))
    return QgsCategorizedSymbolRenderer(field_name, renderer_categories)


def _graduated_renderer(layer, field_name):
    ranges = []
    for lower, upper, label, color in RISK_COLORS:
        ranges.append(QgsRendererRange(lower, upper, _symbol(layer, color), label))
    renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
    renderer.setMode(QgsGraduatedSymbolRenderer.Custom)
    return renderer


from .._mixins import HelpUrlMixin  # noqa: E402


class ApplyResilienceSymbologyAlgorithm(HelpUrlMixin, QgsProcessingAlgorithm):
    LAYER = "LAYER"
    FIELD = "FIELD"
    PRESET = "PRESET"
    REFRESH = "REFRESH"
    OUTPUT_QML = "OUTPUT_QML"

    PRESETS = [
        "Risk score 0-100",
        "Access class",
        "Scenario change class",
        "Adaptation priority class",
    ]

    def tr(self, string):
        return string

    def createInstance(self):
        return ApplyResilienceSymbologyAlgorithm()

    def name(self):
        return "apply_resilience_symbology"

    def displayName(self):
        return self.tr("Apply Resilience Symbology")

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Apply Resilience Symbology</h3>
            <p>Applies a consistent PlanX color preset to a scored or classified resilience layer. Use it after generating risk grids, accessibility outputs, scenario comparison layers, or adaptation priority synthesis outputs.</p>
            <p>The algorithm styles the selected layer in-place and can optionally save a QML style file.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(self.LAYER, self.tr("Layer to style"), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterField(self.FIELD, self.tr("Score or class field"), parentLayerParameterName=self.LAYER))
        self.addParameter(QgsProcessingParameterEnum(self.PRESET, self.tr("Style preset"), options=self.PRESETS, defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(self.REFRESH, self.tr("Refresh layer repaint"), defaultValue=True))
        self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT_QML, self.tr("Optional QML style export"), fileFilter="QGIS style (*.qml)", optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsVectorLayer(parameters, self.LAYER, context)
        field_name = self.parameterAsString(parameters, self.FIELD, context)
        preset = self.parameterAsEnum(parameters, self.PRESET, context)
        refresh = self.parameterAsBool(parameters, self.REFRESH, context)
        qml_path = self.parameterAsFileOutput(parameters, self.OUTPUT_QML, context)

        if layer is None:
            raise Exception("Layer could not be resolved.")

        if preset == 0:
            renderer = _graduated_renderer(layer, field_name)
        elif preset == 1:
            renderer = _category_renderer(layer, field_name, ACCESS_COLORS)
        elif preset == 2:
            renderer = _category_renderer(layer, field_name, CHANGE_COLORS)
        else:
            renderer = _category_renderer(layer, field_name, PRIORITY_COLORS)

        layer.setRenderer(renderer)
        if refresh:
            layer.triggerRepaint()

        if qml_path:
            layer.saveNamedStyle(qml_path)
            feedback.pushInfo(f"QML style saved to {qml_path}")

        feedback.pushInfo(f"Applied '{self.PRESETS[preset]}' style to {layer.name()} using field '{field_name}'.")
        return {self.OUTPUT_QML: qml_path or ""}
