# -*- coding: utf-8 -*-
"""Resilience PDF Atlas.

Builds a multi-page A3 PDF atlas from a scored resilience layer:
  - Cover page (title, subtitle, project metadata, generation timestamp)
  - Overview page (map of full extent + legend + summary stats table)
  - Class pages (one map per risk class, zoomed to that class's extent)
  - Optional driver pages (one page per dominant-hazard field, if provided)

The atlas is built with QgsLayout so it is fully QGIS-native — no external
PDF library. Output is a single .pdf file written to the user-chosen path.

Inputs:
  - scored layer (with a 0-100 score field and an optional class field)
  - title, subtitle (free strings)
  - project / author metadata (free strings)
  - optional dominant-hazard field (one page per unique value)
  - cell-quantile style: equal_interval / quantile / natural_breaks

Outputs:
  - file path of the generated PDF
"""
from __future__ import annotations

import datetime as _dt
import os

from qgis.PyQt.QtCore import QSizeF
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsClassificationEqualInterval,
    QgsClassificationJenks,
    QgsClassificationQuantile,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLayout,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterString,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
    QgsVectorLayer,
)


CLASSIFY_METHODS = ("Equal interval", "Quantile", "Natural breaks (Jenks)")

ATLAS_PRESETS = (
    {"label": "A3 Standard (200 dpi)", "width": 420, "height": 297, "dpi": 200, "map_w": 260, "map_h": 230},
    {"label": "A4 Compact (150 dpi)", "width": 297, "height": 210, "dpi": 150, "map_w": 180, "map_h": 160},
    {"label": "A3 Studio HQ (300 dpi)", "width": 420, "height": 297, "dpi": 300, "map_w": 260, "map_h": 230},
)


def _statistics(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None, "median": None,
                "p25": None, "p75": None}
    sv = sorted(values)
    n = len(sv)

    def pct(p):
        if n == 1:
            return sv[0]
        idx = (p / 100.0) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        frac = idx - lo
        return sv[lo] + (sv[hi] - sv[lo]) * frac

    return {
        "n": n,
        "mean": sum(sv) / n,
        "min": sv[0],
        "max": sv[-1],
        "median": pct(50),
        "p25": pct(25),
        "p75": pct(75),
    }


def _apply_classified_renderer(layer: QgsVectorLayer, field: str, method_idx: int):
    base = QgsFillSymbol.createSimple({"color": "230,236,242,180", "outline_color": "30,40,60,200"})
    method_map = {
        0: QgsClassificationEqualInterval(),
        1: QgsClassificationQuantile(),
        2: QgsClassificationJenks(),
    }
    classifier = method_map.get(method_idx, QgsClassificationEqualInterval())
    renderer = QgsGraduatedSymbolRenderer.createRenderer(
        layer, field, 5, QgsGraduatedSymbolRenderer.Custom, base
    )
    if renderer is None:
        # Fallback — create empty renderer; QGIS will still render geometry.
        renderer = QgsGraduatedSymbolRenderer(field, [])
    try:
        renderer.setClassificationMethod(classifier)
        renderer.updateClasses(layer, 5)
        # Color ramp: yellow -> orange -> red (resilience risk convention)
        from qgis.core import QgsColorRampShader, QgsStyle
        ramp = QgsStyle.defaultStyle().colorRamp("Reds")
        if ramp is not None:
            renderer.updateColorRamp(ramp)
    except Exception:
        pass
    layer.setRenderer(renderer)


class ResiliencePdfAtlasAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    SCORE_FIELD = "SCORE_FIELD"
    CLASS_FIELD = "CLASS_FIELD"
    TITLE = "TITLE"
    SUBTITLE = "SUBTITLE"
    AUTHOR = "AUTHOR"
    PROJECT = "PROJECT"
    METHOD = "METHOD"
    ATLAS_PRESET = "ATLAS_PRESET"
    OUTPUT = "OUTPUT"

    def tr(self, string):
        return string

    def createInstance(self):
        return ResiliencePdfAtlasAlgorithm()

    def name(self):
        return "resilience_pdf_atlas"

    def displayName(self):
        return self.tr("Resilience PDF Atlas")

    def group(self):
        return self.tr("9 - Report and QA")

    def groupId(self):
        return "planx_urban_resilience_reporting"

    def shortHelpString(self):
        return self.tr(
            """
            <h3>Resilience PDF Atlas</h3>
            <p>Builds a multi-page atlas (cover + overview + per-class map pages)
            from a scored resilience layer. Choose a map-book preset (A3 standard,
            A4 compact, or A3 high-DPI studio). QGIS-native via QgsLayout.</p>
            <p>Pair with any algorithm in this suite that produces a 0-100
            score (Adaptation Priority, Multi-Hazard Composite, Recovery
            Capacity, Equity-Adjusted Priority, Climate Projection Overlay).
            The optional class field is used to drive separate pages.</p>
            """
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, self.tr("Scored layer (with 0-100 field)"),
            [QgsProcessing.TypeVectorPolygon, QgsProcessing.TypeVectorPoint],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SCORE_FIELD, self.tr("Score field (0-100)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CLASS_FIELD, self.tr("Class field (optional, e.g. mh_class)"),
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.String, optional=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.TITLE, self.tr("Atlas title"),
            defaultValue="PlanX Urban Resilience — Atlas",
        ))
        self.addParameter(QgsProcessingParameterString(
            self.SUBTITLE, self.tr("Subtitle"),
            defaultValue="Screening atlas (not engineering-grade simulation)",
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.AUTHOR, self.tr("Author / institution"),
            defaultValue="", optional=True,
        ))
        self.addParameter(QgsProcessingParameterString(
            self.PROJECT, self.tr("Project / study area name"),
            defaultValue="", optional=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, self.tr("Classification method (cartography)"),
            options=list(CLASSIFY_METHODS), defaultValue=1,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.ATLAS_PRESET,
            self.tr("Map-book preset"),
            options=[p["label"] for p in ATLAS_PRESETS],
            defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, self.tr("Output PDF"),
            fileFilter="PDF files (*.pdf)",
        ))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Input layer is required.")
        score_field = self.parameterAsString(parameters, self.SCORE_FIELD, context)
        class_field = self.parameterAsString(parameters, self.CLASS_FIELD, context) or ""
        title = self.parameterAsString(parameters, self.TITLE, context) or "Atlas"
        subtitle = self.parameterAsString(parameters, self.SUBTITLE, context) or ""
        author = self.parameterAsString(parameters, self.AUTHOR, context) or ""
        project_name = self.parameterAsString(parameters, self.PROJECT, context) or ""
        method_idx = self.parameterAsEnum(parameters, self.METHOD, context)
        preset_idx = self.parameterAsEnum(parameters, self.ATLAS_PRESET, context)
        layout_spec = ATLAS_PRESETS[preset_idx]
        out_pdf = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        if not out_pdf:
            raise QgsProcessingException("Output PDF path is required.")

        # Materialise the input as a temporary in-memory layer so that
        # renderer + classification settings stick.
        wkb = source.wkbType()
        layer = QgsVectorLayer(f"{Qgis.WkbType(wkb).name}?crs={source.sourceCrs().authid()}", "atlas_input", "memory")
        layer.dataProvider().addAttributes(source.fields())
        layer.updateFields()
        layer.startEditing()
        values: list[float] = []
        for feat in source.getFeatures():
            layer.addFeature(feat)
            try:
                v = float(feat.attribute(score_field))
                values.append(v)
            except (TypeError, ValueError):
                pass
        layer.commitChanges()

        _apply_classified_renderer(layer, score_field, method_idx)
        stats = _statistics(values)

        # ── Build layout ────────────────────────────────────────────────
        project = QgsProject.instance()
        layout = QgsLayout(project)
        layout.initializeDefaults()
        page = layout.pageCollection().pages()[0]
        page.setPageSize(self._page_size(layout_spec))

        feedback.pushInfo(f"Layout preset: {layout_spec['label']}")
        feedback.pushInfo("Cover page...")
        self._add_cover(layout, title, subtitle, author, project_name, stats)

        feedback.pushInfo("Overview page...")
        self._add_page(layout, layout_spec)
        self._add_map_page(
            layout, layout_spec, page_index=1, layer=layer, extent=layer.extent(),
            heading=f"Overview — {score_field}",
        )
        self._add_stats_block(layout, layout_spec, page_index=1, stats=stats, score_field=score_field)

        # Per-class pages (if class field provided)
        if class_field:
            classes_seen: dict[str, QgsRectangle] = {}
            for feat in layer.getFeatures():
                cls = feat.attribute(class_field)
                if cls is None or cls == "":
                    continue
                key = str(cls)
                rect = feat.geometry().boundingBox() if feat.hasGeometry() else None
                if rect is None or rect.isEmpty():
                    continue
                if key not in classes_seen:
                    classes_seen[key] = QgsRectangle(rect)
                else:
                    classes_seen[key].combineExtentWith(rect)
            for cls_name, rect in classes_seen.items():
                if feedback.isCanceled():
                    break
                feedback.pushInfo(f"Class page: {cls_name}")
                self._add_page(layout, layout_spec)
                page_idx = len(layout.pageCollection().pages()) - 1
                rect.scale(1.10)  # 10% margin
                self._add_map_page(
                    layout, layout_spec, page_index=page_idx, layer=layer,
                    extent=rect, heading=f"Class — {cls_name}",
                )

        # ── Export ──────────────────────────────────────────────────────
        feedback.pushInfo(f"Exporting PDF: {out_pdf}")
        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = layout_spec["dpi"]
        result = exporter.exportToPdf(out_pdf, settings)
        if result != QgsLayoutExporter.Success:
            raise QgsProcessingException(f"PDF export failed (code {result}).")

        return {self.OUTPUT: out_pdf}

    # ───────────────────────── Layout helpers ─────────────────────────

    @staticmethod
    def _page_size(spec: dict) -> QgsLayoutSize:
        return QgsLayoutSize(spec["width"], spec["height"], QgsUnitTypes.LayoutMillimeters)

    def _add_page(self, layout: QgsLayout, spec: dict) -> None:
        page = QgsLayoutItemPage(layout)
        page.setPageSize(self._page_size(spec))
        layout.pageCollection().addPage(page)

    def _add_cover(self, layout, title, subtitle, author, project_name, stats):
        font_title = QFont("Helvetica", 36)
        font_title.setBold(True)
        title_lbl = QgsLayoutItemLabel(layout)
        title_lbl.setText(title)
        title_lbl.setFont(font_title)
        title_lbl.attemptMove(QgsLayoutPoint(30, 80, QgsUnitTypes.LayoutMillimeters))
        title_lbl.attemptResize(QgsLayoutSize(360, 40, QgsUnitTypes.LayoutMillimeters))
        layout.addItem(title_lbl)

        if subtitle:
            font_sub = QFont("Helvetica", 16)
            sub_lbl = QgsLayoutItemLabel(layout)
            sub_lbl.setText(subtitle)
            sub_lbl.setFont(font_sub)
            sub_lbl.setFontColor(QColor("#445"))
            sub_lbl.attemptMove(QgsLayoutPoint(30, 130, QgsUnitTypes.LayoutMillimeters))
            sub_lbl.attemptResize(QgsLayoutSize(360, 20, QgsUnitTypes.LayoutMillimeters))
            layout.addItem(sub_lbl)

        meta = []
        if project_name:
            meta.append(f"Project: {project_name}")
        if author:
            meta.append(f"Author: {author}")
        meta.append(f"Units: {stats.get('n', 0)}")
        meta.append(f"Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")

        font_meta = QFont("Helvetica", 12)
        meta_lbl = QgsLayoutItemLabel(layout)
        meta_lbl.setText("\n".join(meta))
        meta_lbl.setFont(font_meta)
        meta_lbl.attemptMove(QgsLayoutPoint(30, 200, QgsUnitTypes.LayoutMillimeters))
        meta_lbl.attemptResize(QgsLayoutSize(360, 60, QgsUnitTypes.LayoutMillimeters))
        layout.addItem(meta_lbl)

    def _add_map_page(self, layout, spec, page_index, layer, extent, heading):
        page_h = spec["height"]
        map_w = spec["map_w"]
        map_h = spec["map_h"]
        legend_x = 15 + map_w + 10

        font_h = QFont("Helvetica", 22)
        font_h.setBold(True)
        head_lbl = QgsLayoutItemLabel(layout)
        head_lbl.setText(heading)
        head_lbl.setFont(font_h)
        head_lbl.attemptMove(
            QgsLayoutPoint(15, page_h * page_index + 15, QgsUnitTypes.LayoutMillimeters)
        )
        head_lbl.attemptResize(QgsLayoutSize(spec["width"] - 30, 14, QgsUnitTypes.LayoutMillimeters))
        layout.addItem(head_lbl)

        map_item = QgsLayoutItemMap(layout)
        map_item.setLayers([layer])
        map_item.attemptMove(
            QgsLayoutPoint(15, page_h * page_index + 35, QgsUnitTypes.LayoutMillimeters)
        )
        map_item.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
        map_item.setExtent(extent)
        map_item.setFrameEnabled(True)
        map_item.setFrameStrokeWidth(QgsLayoutSize(0.3, 0, QgsUnitTypes.LayoutMillimeters))
        layout.addItem(map_item)

        legend = QgsLayoutItemLegend(layout)
        legend.setTitle("Legend")
        legend.setLinkedMap(map_item)
        legend.attemptMove(
            QgsLayoutPoint(legend_x, page_h * page_index + 35, QgsUnitTypes.LayoutMillimeters)
        )
        legend.attemptResize(QgsLayoutSize(spec["width"] - legend_x - 15, 120, QgsUnitTypes.LayoutMillimeters))
        layout.addItem(legend)

        bar = QgsLayoutItemScaleBar(layout)
        bar.setStyle("Single Box")
        bar.setLinkedMap(map_item)
        bar.applyDefaultSize()
        bar.attemptMove(
            QgsLayoutPoint(15, page_h * page_index + 35 + map_h + 5, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addItem(bar)

    def _add_stats_block(self, layout, spec, page_index, stats, score_field):
        lines = [
            f"<b>Statistics for '{score_field}'</b>",
            f"n = {stats['n']}",
        ]
        for k in ("mean", "min", "p25", "median", "p75", "max"):
            v = stats[k]
            lines.append(f"{k}: {v:.2f}" if v is not None else f"{k}: —")
        font = QFont("Helvetica", 11)
        lbl = QgsLayoutItemLabel(layout)
        lbl.setText("<br>".join(lines))
        lbl.setMarginX(2)
        lbl.setMarginY(2)
        lbl.setFont(font)
        legend_x = 15 + spec["map_w"] + 10
        lbl.attemptMove(
            QgsLayoutPoint(legend_x, spec["height"] * page_index + 165, QgsUnitTypes.LayoutMillimeters)
        )
        lbl.attemptResize(QgsLayoutSize(spec["width"] - legend_x - 15, 90, QgsUnitTypes.LayoutMillimeters))
        layout.addItem(lbl)
