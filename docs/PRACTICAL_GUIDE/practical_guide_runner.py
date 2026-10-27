r"""
PlanX Urban Resilience - Practical Guide screenshot generator (Windows / OSGeo4W).

Runs every one of the 45 Urban Resilience algorithms on a real, deterministic
dataset inside a headless QGIS session and captures a 4-panel screenshot for
each one:

    1 - INPUT DATA        the source layers the tool consumed
    2 - PARAMETERS        the exact values used in this run
    3 - OUTPUT (RAW)      the result as QGIS loaded it (no styling)
    4 - OUTPUT (STYLED)   the same result with a graduated / categorized ramp

Usage::

    C:\OSGeo4W\bin\python-qgis-ltr.bat practical_guide_runner.py --all
    C:\OSGeo4W\bin\python-qgis-ltr.bat practical_guide_runner.py --algo urban_heat_comfort_risk
    C:\OSGeo4W\bin\python-qgis-ltr.bat practical_guide_runner.py --list

The dataset is produced by the plugin's own ``synthetic_resilience_demo_dataset``
algorithm, so the guide is always in step with the shipped fixture. A coastal
DEM, a shoreline, a vegetation band, a tree layer, an emission-source layer and
a planning-unit grid are synthesised alongside it, and every downstream tool
chains off the real output of the tool before it.

Nothing here is mocked: every screenshot is a genuine QGIS render of a genuine
algorithm run.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

for _p in (r'C:\OSGeo4W\apps\qgis-ltr\python\plugins',
           r'C:\OSGeo4W\apps\qgis\python\plugins'):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)

from qgis.core import (  # noqa: E402
    QgsApplication, Qgis, QgsProject, QgsMapSettings, QgsMapRendererParallelJob,
    QgsRectangle, QgsVectorLayer, QgsRasterLayer, QgsGraduatedSymbolRenderer,
    QgsRendererRange, QgsSymbol, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSingleSymbolRenderer,
    QgsSingleBandPseudoColorRenderer, QgsColorRampShader, QgsRasterShader,
    QgsStyle, QgsProcessingFeedback, QgsProcessingContext, QgsField, QgsFields,
    QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterField,
    QgsProcessingParameterEnum, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessingParameterString,
    QgsProcessingParameterExtent, QgsProcessingParameterCrs,
    QgsProcessingParameterFile, QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterFeatureSource, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterRasterDestination,
    QgsProcessingParameterVectorDestination, QgsProcessingParameterFileDestination,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtGui import QImage, QPainter, QColor, QFont, QPen  # noqa: E402
from qgis.PyQt.QtCore import QSize, QRectF, Qt, QVariant  # noqa: E402

GUIDE_DIR = Path(__file__).resolve().parent
SHOT_DIR = GUIDE_DIR / "screenshots"
MANIFEST_DIR = GUIDE_DIR / "manifest"
WORK_DIR = GUIDE_DIR / "work"
PLUGIN_ROOT = GUIDE_DIR.parent.parent.parent          # -> qgis_plugins/
PROVIDER = "planx_urban_resilience"
CRS = "EPSG:3857"

for _d in (SHOT_DIR, MANIFEST_DIR):
    _d.mkdir(parents=True, exist_ok=True)
if WORK_DIR.exists():
    shutil.rmtree(WORK_DIR, ignore_errors=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PLUGIN_ROOT))

QGS_APP = QgsApplication([], False)
QgsApplication.initQgis()
print(f"[OK] QGIS {Qgis.QGIS_VERSION}", flush=True)

import processing  # noqa: E402
from planx_urban_resilience.processing.urban_resilience_provider import (  # noqa: E402
    PlanXUrbanResilienceProvider,
)

_provider = PlanXUrbanResilienceProvider()
QgsApplication.processingRegistry().addProvider(_provider)
ALGOS = {a.id().split(":")[-1]: a for a in _provider.algorithms()}
print(f"[OK] Urban Resilience provider: {len(ALGOS)} algorithms", flush=True)

try:
    from processing.core.Processing import Processing
    Processing.initialize()
    if "native" not in QgsApplication.processingRegistry().providers():
        from qgis.analysis import QgsNativeAlgorithms
        QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    print("[OK] native provider registered", flush=True)
except Exception:
    traceback.print_exc()

FEEDBACK = QgsProcessingFeedback()
CONTEXT = QgsProcessingContext()
PROJECT = QgsProject.instance()
PROJECT.setCrs(QgsCoordinateReferenceSystem(CRS))

#: logical name -> file path of every layer the guide uses
LAYERS: dict[str, str] = {}
#: algo_id -> {param: produced path}
PRODUCED: dict[str, dict[str, str]] = {}


def sh(p):
    return str(p).replace("/", "\\")


def run(algo_id, params, outs=None):
    p = dict(params)
    if outs:
        p.update(outs)
    try:
        return processing.run(f"{PROVIDER}:{algo_id}", p, context=CONTEXT,
                              feedback=FEEDBACK)
    except Exception as exc:  # noqa: BLE001 - the guide must survive one bad tool
        msg = str(exc).replace("\n", " ")[:220]
        print(f"      [FAIL] {algo_id}: {msg}", flush=True)
        return None


def load_layer(path, name):
    if not path or not os.path.exists(path):
        return None
    if str(path).lower().endswith(".tif"):
        lyr = QgsRasterLayer(path, name)
    else:
        lyr = QgsVectorLayer(path, name, "ogr")
    return lyr if lyr.isValid() else None


# ------------------------------------------------------------- style helpers
RAMP = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027",
        "#4575b4", "#74add1", "#7b3294", "#c51b7d", "#7b3294"]

#: the suite's own class vocabulary, reused so the guide and the plugin agree
CLASS_COLOURS = {
    "low": "#2A9D8F", "moderate": "#E9C46A", "high": "#F4A261", "very high": "#D62828",
    "covered": "#2A9D8F", "watch": "#E9C46A", "underserved": "#F4A261",
    "critical": "#D62828", "unreachable": "#6B7280",
    "improved": "#2A9D8F", "stable": "#94A3B8", "worsened": "#D62828",
    "monitor": "#2A9D8F", "medium": "#E9C46A", "immediate": "#D62828",
}

#: field names worth a graduated ramp, most specific first
SCORE_CANDIDATES = (
    "adapt_score", "mh_score", "eq_adjusted_score", "rr_priority_score",
    "flood_score", "heat_score", "air_score", "wui_score", "slr_score",
    "access_score", "svi_score", "stress_score", "rc_score", "vs_value",
    "cb_ratio", "ss_baseline", "ss_mean", "gi_zscore", "lisa_z",
    "criticality_score", "collapse_prob", "priority_score", "score",
)


def _mk_symbol(layer, color):
    try:
        t = layer.geometryType()
        if t == 0:
            return QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": color.name(), "outline_color": "#1a1a1a",
                 "outline_width": "0.2", "size": "2.4"})
        if t == 1:
            return QgsLineSymbol.createSimple(
                {"color": color.name(), "width": "0.7", "capstyle": "round"})
        return QgsFillSymbol.createSimple(
            {"color": color.name(), "outline_color": "#1a1a1a", "outline_width": "0.15"})
    except Exception:
        return QgsSymbol.defaultSymbol(layer.geometryType())


def _class_field(layer):
    """Find a string field carrying the suite's class vocabulary."""
    for feat in layer.getFeatures():
        vals = set()
        for fld in layer.fields():
            if fld.typeName().lower() in ("string", "text"):
                vals.add(str(feat[fld.name()]))
        if not vals:
            continue
        known = [v for v in vals if v.strip().lower() in CLASS_COLOURS]
        if len(known) >= 2:
            for fld in layer.fields():
                if fld.typeName().lower() not in ("string", "text"):
                    continue
                col = CLASS_COLOURS.get(str(feat[fld.name()]).strip().lower())
                if col:
                    return fld.name()
    return None


def _style_vector(layer):
    """Apply a sensible graduated / categorized renderer to a result layer."""
    if not isinstance(layer, QgsVectorLayer):
        return
    try:
        fields = [f for f in layer.fields()
                  if f.name().lower() not in ("fid", "geom", "geometry")]
        if not fields:
            layer.setRenderer(QgsSingleSymbolRenderer(_mk_symbol(layer, QColor("#4fc3f7"))))
            return

        cls_field = _class_field(layer)
        if cls_field:
            cats, seen = [], set()
            for feat in layer.getFeatures():
                val = str(feat[cls_field])
                if val in seen:
                    continue
                seen.add(val)
                col = CLASS_COLOURS.get(val.strip().lower(), "#4fc3f7")
                cats.append(QgsRendererCategory(
                    val, _mk_symbol(layer, QColor(col)), val))
            if cats:
                layer.setRenderer(QgsCategorizedSymbolRenderer(cls_field, cats))
                return

        num_field = None
        lowered = {f.name().lower(): f for f in fields}
        for cand in SCORE_CANDIDATES:
            if cand in lowered:
                num_field = lowered[cand]
                break
        if num_field is None:
            for f in fields:
                if f.isNumeric() and f.name().lower().endswith(("_score", "_index", "_r")):
                    num_field = f
                    break
        if num_field is None:
            for f in fields:
                if f.isNumeric():
                    num_field = f
                    break
        if num_field is None:
            for f in fields:
                if f.typeName().lower() in ("string", "text"):
                    vals = set()
                    for feat in layer.getFeatures():
                        vals.add(str(feat[f.name()]))
                        if len(vals) > 8:
                            break
                    if 1 < len(vals) <= 8:
                        cats = [QgsRendererCategory(
                            v, _mk_symbol(layer, QColor(RAMP[i % len(RAMP)])), v)
                            for i, v in enumerate(sorted(vals))]
                        layer.setRenderer(QgsCategorizedSymbolRenderer(f.name(), cats))
                    else:
                        layer.setRenderer(QgsSingleSymbolRenderer(
                            _mk_symbol(layer, QColor("#4fc3f7"))))
                    return
            layer.setRenderer(QgsSingleSymbolRenderer(_mk_symbol(layer, QColor("#4fc3f7"))))
            return

        vals = []
        for feat in layer.getFeatures():
            try:
                v = feat[num_field.name()]
                if v is not None and v != "":
                    vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if not vals:
            layer.setRenderer(QgsSingleSymbolRenderer(_mk_symbol(layer, QColor("#4fc3f7"))))
            return
        vmin, vmax = min(vals), max(vals)
        if vmax == vmin:
            vmax = vmin + 1.0
        ranges = []
        for i in range(5):
            lo = vmin + (vmax - vmin) * i / 5
            hi = vmin + (vmax - vmin) * (i + 1) / 5
            ranges.append(QgsRendererRange(
                lo, hi, _mk_symbol(layer, QColor(RAMP[i % len(RAMP)])),
                f"{lo:.2f} - {hi:.2f}"))
        layer.setRenderer(QgsGraduatedSymbolRenderer(num_field.name(), ranges))
    except Exception:
        pass


def _style_raster(layer):
    if not isinstance(layer, QgsRasterLayer):
        return
    try:
        prov = layer.dataProvider()
        st = prov.bandStatistics(1)
        if st.minimumValue == st.maximumValue:
            return
        fn = QgsColorRampShader()
        fn.setColorRampType(QgsColorRampShader.Interpolated)
        ramp = QgsStyle.defaultStyle().colorRamp("Viridis")
        items = []
        for i in range(10):
            t = i / 9.0
            val = st.minimumValue + (st.maximumValue - st.minimumValue) * t
            items.append(QgsColorRampShader.ColorRampItem(val, ramp.color(t), f"{val:.2f}"))
        fn.setColorRampItemList(items)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(fn)
        layer.setRenderer(QgsSingleBandPseudoColorRenderer(prov, 1, shader))
    except Exception:
        pass


#: neutral colours for the "raw" panel - the point is to show the geometry
#: without any thematic interpretation
RAW_FILL = "#c9d4d3"
RAW_LINE = "#5b6f6d"
RAW_POINT = "#2f6f68"


def _style_raw(layer):
    """Flat, deliberately uninformative styling for the raw-output panel."""
    if not isinstance(layer, QgsVectorLayer):
        return
    try:
        t = layer.geometryType()
        if t == 0:
            sym = QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": RAW_POINT, "outline_color": "#ffffff",
                 "outline_width": "0.3", "size": "2.6"})
        elif t == 1:
            sym = QgsLineSymbol.createSimple(
                {"color": RAW_LINE, "width": "0.9", "capstyle": "round"})
        else:
            sym = QgsFillSymbol.createSimple(
                {"color": RAW_FILL, "outline_color": RAW_LINE, "outline_width": "0.25"})
        sym.setOpacity(0.75)
        layer.setRenderer(QgsSingleSymbolRenderer(sym))
    except Exception:
        pass


#: muted, per-geometry-type styling for the input-data panel
INPUT_STYLE = {
    0: {"color": "#7a3e9d", "outline_color": "#ffffff", "outline_width": "0.3", "size": "3.0"},
    1: {"color": "#4a5f6d", "width": "0.9"},
    2: {"color": "#8fb8a8", "outline_color": "#4a5f6d", "outline_width": "0.3"},
}


def _style_input(layer):
    """Readable, muted styling so every input layer is distinguishable."""
    if not isinstance(layer, QgsVectorLayer):
        return
    try:
        t = layer.geometryType()
        props = dict(INPUT_STYLE.get(t, {}))
        if t == 0:
            sym = QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": props["color"],
                 "outline_color": props["outline_color"],
                 "outline_width": str(props["outline_width"]),
                 "size": str(props["size"])})
            sym.setOpacity(0.95)
        elif t == 1:
            sym = QgsLineSymbol.createSimple(
                {"color": props["color"], "width": str(props["width"]),
                 "capstyle": "round"})
            sym.setOpacity(0.9)
        else:
            sym = QgsFillSymbol.createSimple(
                {"color": props["color"], "outline_color": props["outline_color"],
                 "outline_width": str(props["outline_width"])})
            sym.setOpacity(0.55)
        layer.setRenderer(QgsSingleSymbolRenderer(sym))
    except Exception:
        pass


def _order_for_drawing(layers):
    """QGIS draws the first layer on top: polygons first, then lines, then points."""
    buckets = {2: [], 1: [], 0: []}
    for lay in layers:
        if lay is None or not lay.isValid():
            continue
        buckets.setdefault(lay.geometryType(), []).append(lay)
    return buckets.get(2, []) + buckets.get(1, []) + buckets.get(0, [])


def _render(layers, extent, size):
    settings = QgsMapSettings()
    settings.setLayers([ly for ly in layers if ly is not None and ly.isValid()])
    settings.setExtent(extent)
    settings.setOutputSize(size)
    settings.setBackgroundColor(QColor("#ffffff"))
    try:
        settings.setDestinationCrs(layers[0].crs())
    except Exception:
        pass
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    return job.renderedImage()


def _panel_label(painter, x, y, w, text, sub=""):
    painter.fillRect(QRectF(x, y, w, 34), QColor(13, 148, 136, 240))
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    painter.drawText(QRectF(x + 10, y + 4, w - 20, 26),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignVCenter, text)
    if sub:
        painter.setPen(QColor("#083c38"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.fillRect(QRectF(x, y + 34, w, 19), QColor(255, 255, 255, 228))
        painter.drawText(QRectF(x + 10, y + 34, w - 20, 19),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignVCenter, sub)


def _extent_of(layers):
    extent = None
    for lay in layers:
        if lay is None or not lay.isValid():
            continue
        ext = lay.extent()
        if ext.isEmpty():
            continue
        extent = QgsRectangle(ext) if extent is None else extent
        extent.combineExtentWith(ext)
    if extent is None or extent.isEmpty():
        extent = QgsRectangle(0, 0, 2000, 1400)
    else:
        extent.scale(1.08)
    return extent


def _text_panel(painter, x, y, w, h, title, sub, lines, mono_size=8):
    """A framed text panel (used for the parameter panel)."""
    painter.setBrush(QColor("#fbfcfc"))
    painter.fillRect(QRectF(x, y, w, h), QColor("#fbfcfc"))
    _panel_label(painter, x, y, w, title, sub)
    top = y + 58
    painter.setBrush(QColor(255, 255, 255, 246))
    painter.fillRect(QRectF(x + 26, top, w - 52, h - 92), QColor(255, 255, 255, 246))
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor("#0d9488"), 1.4))
    painter.drawRect(QRectF(x + 26, top, w - 52, h - 92))
    painter.setPen(QColor("#1a1a1a"))
    painter.setFont(QFont("Consolas", mono_size))
    y0 = top + 14
    max_lines = int((h - 110) // 11)
    for line in lines[:max_lines]:
        painter.drawText(int(x + 34), int(y0), line[:104])
        y0 += 11
    if len(lines) > max_lines:
        painter.setPen(QColor("#6b7d7b"))
        painter.setFont(QFont("Consolas", mono_size))
        painter.drawText(int(x + 34), int(y0 + 4),
                         f"... {len(lines) - max_lines} more parameter(s)")


def capture_4panel(algo_id, display_name, input_layers, output_layers, param_text,
                   out_png, header_right="Real QGIS run - PlanX Urban Resilience engine"):
    """The standard 4-panel composite.

    top-left  INPUT DATA     the source layers the tool consumed
    top-right OUTPUT (RAW)   the result, flat styling, no interpretation
    bottom-left  OUTPUT (STYLED)  the same result, graduated / categorized
    bottom-right PARAMETERS  the exact values used in this run
    """
    PW, PH, HDR = 900, 620, 30
    img = QImage(QSize(PW * 2, PH * 2 + HDR), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    extent = _extent_of([ly for ly in (input_layers + output_layers) if ly is not None])

    def draw_map(x, y, layers, label, sub):
        if not layers:
            p.fillRect(QRectF(x, y, PW, PH), QColor("#f4f6f6"))
            p.setPen(QColor("#99a5a5"))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(QRectF(x, y, PW, PH), Qt.AlignmentFlag.AlignCenter, "no layer for this panel")
        else:
            im = _render(layers, extent, QSize(PW, PH))
            if not im.isNull():
                p.drawImage(x, y, im)
        _panel_label(p, x, y, PW, label, sub)

    # ---- panel 1: inputs, styled so every layer stays readable ----------
    inputs = []
    for lay in input_layers:
        if lay is None or not lay.isValid():
            continue
        _style_input(lay)
        inputs.append(lay)
    draw_map(0, HDR, _order_for_drawing(inputs), "1 - INPUT DATA",
             "source layers used by the tool")

    # ---- panel 3: raw output (flat styling) -----------------------------
    raws = []
    for lay in output_layers:
        if lay is None or not lay.isValid():
            continue
        _style_raw(lay)
        raws.append(lay)
    draw_map(PW, HDR, _order_for_drawing(raws), "3 - OUTPUT (RAW)",
             "geometry only, no thematic styling")

    # ---- panel 4: styled output -----------------------------------------
    styled = []
    for lay in output_layers:
        if lay is None or not lay.isValid():
            continue
        if isinstance(lay, QgsVectorLayer):
            try:
                lay.renderer().setOpacity(0.9)
            except Exception:
                pass
            _style_vector(lay)
        else:
            _style_raster(lay)
        styled.append(lay)
    draw_map(0, HDR + PH, _order_for_drawing(styled), "4 - OUTPUT (STYLED)",
             "graduated / categorized on the result field")

    # ---- panel 2: parameters --------------------------------------------
    _text_panel(p, PW, HDR + PH, PW, PH, "2 - PARAMETERS",
                "values used in this run", param_text.splitlines())

    p.fillRect(QRectF(0, 0, PW * 2, HDR), QColor("#0b2b28"))
    p.setPen(QColor("#7fe3d6"))
    p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    p.drawText(12, 21, f"PlanX Urban Resilience - {display_name}  ({algo_id})")
    p.setPen(QColor("#9fd6c9"))
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(PW + 12, 21, header_right)

    p.end()
    img.save(out_png, "PNG")
    return os.path.exists(out_png)


def _report_text(path, max_chars=7000):
    """Readable text out of an HTML / Markdown / text report."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            raw = fh.read(max_chars + 40000)
        if path.lower().endswith((".html", ".htm")):
            import re
            raw = re.sub(r'(?is)<(script|style|svg)[^>]*>.*?</\1>', ' ', raw)
            raw = re.sub(r'(?s)<!--.*?-->', ' ', raw)
            raw = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</tr>|</h[1-6]>|</li>|</td>',
                         '\n', raw)
            raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
            raw = (raw.replace('&nbsp;', ' ').replace('&amp;', '&')
                   .replace('&lt;', '<').replace('&gt;', '>')
                   .replace('&quot;', '"').replace('&#39;', "'"))
        else:
            raw = raw.replace("#", "")
        lines = [ln.strip() for ln in raw.splitlines()]
        lines = [ln for ln in lines if ln]
        return "\n".join(lines)[:max_chars]
    except Exception:
        return ""


def capture_report_4panel(algo_id, display_name, input_layers, report_path,
                           param_text, out_png, report_title):
    """4-panel for tools whose result is a report file rather than a layer.

    top-left   INPUT DATA
    top-right  REPORT MAP
    bottom-left  REPORT CONTENT
    bottom-right PARAMETERS
    """
    PW, PH, HDR = 900, 620, 30
    img = QImage(QSize(PW * 2, PH * 2 + HDR), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    extent = _extent_of(input_layers)

    def map_panel(x, y, layers, label, sub):
        if not layers:
            p.fillRect(QRectF(x, y, PW, PH), QColor("#f4f6f6"))
            p.setPen(QColor("#99a5a5"))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(QRectF(x, y, PW, PH), Qt.AlignmentFlag.AlignCenter, "no layer for this panel")
        else:
            im = _render(layers, extent, QSize(PW, PH))
            if not im.isNull():
                p.drawImage(x, y, im)
        _panel_label(p, x, y, PW, label, sub)

    styled_inputs = []
    for lay in input_layers:
        if lay is None or not lay.isValid():
            continue
        _style_input(lay)
        styled_inputs.append(lay)
    ordered = _order_for_drawing(styled_inputs)

    map_panel(0, HDR, ordered, "1 - INPUT DATA", "layers the report reads")
    map_panel(PW, HDR, ordered, "3 - REPORT MAP", "study area shown in the report")

    body = _report_text(report_path)
    _text_panel(p, 0, HDR + PH, PW, PH, "4 - REPORT CONTENT", report_title,
                body.splitlines(), mono_size=7)

    _text_panel(p, PW, HDR + PH, PW, PH, "2 - PARAMETERS", "values used in this run",
                param_text.splitlines())

    p.fillRect(QRectF(0, 0, PW * 2, HDR), QColor("#0b2b28"))
    p.setPen(QColor("#7fe3d6"))
    p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    p.drawText(12, 21, f"PlanX Urban Resilience - {display_name}  ({algo_id})")
    p.setPen(QColor("#9fd6c9"))
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(PW + 12, 21, "Real QGIS run - PlanX Urban Resilience engine")
    p.end()
    img.save(out_png, "PNG")
    return os.path.exists(out_png)


def capture_symbology_4panel(algo_id, display_name, raw_layer, styled_layer,
                             param_text, out_png, qml_path, preset_name):
    """4-panel for Apply Resilience Symbology: the style IS the output."""
    PW, PH, HDR = 900, 620, 30
    img = QImage(QSize(PW * 2, PH * 2 + HDR), QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    extent = _extent_of([raw_layer, styled_layer])

    def map_panel(x, y, layers, label, sub):
        if not layers:
            p.fillRect(QRectF(x, y, PW, PH), QColor("#f4f6f6"))
            p.setPen(QColor("#99a5a5"))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(QRectF(x, y, PW, PH), Qt.AlignmentFlag.AlignCenter, "no layer for this panel")
        else:
            im = _render(layers, extent, QSize(PW, PH))
            if not im.isNull():
                p.drawImage(x, y, im)
        _panel_label(p, x, y, PW, label, sub)

    map_panel(0, HDR, [raw_layer], "1 - INPUT (RAW)", "layer before styling")
    map_panel(PW, HDR, [styled_layer], "3 - OUTPUT (STYLED)",
              f"preset: {preset_name}")

    # panel 4: the legend the preset produced
    p.setBrush(QColor("#fbfcfc"))
    p.fillRect(QRectF(0, HDR + PH, PW, PH), QColor("#fbfcfc"))
    p.setBrush(Qt.NoBrush)
    _panel_label(p, 0, HDR + PH, PW, "4 - LEGEND", "colour vocabulary applied")
    y = HDR + PH + 62
    try:
        renderer = styled_layer.renderer()
        # collect colours as plain strings: the renderer ranges are temporaries
        # and their symbols would dangle once the list is released
        entries = []
        if isinstance(renderer, QgsGraduatedSymbolRenderer):
            for rng in renderer.ranges():
                sym = rng.symbol()
                entries.append((str(rng.label()),
                                QColor(sym.color().name()).name() if sym else None))
        elif isinstance(renderer, QgsCategorizedSymbolRenderer):
            for cat in renderer.categories():
                sym = cat.symbol()
                entries.append((str(cat.label() or cat.value()),
                                QColor(sym.color().name()).name() if sym else None))
        if not entries:
            legend = renderer.legendNode()

            def _collect(node):
                for child in node.children():
                    label_text = child.data(Qt.DisplayRole)
                    sym = child.data(Qt.UserRole)
                    if sym is not None and hasattr(sym, "symbol"):
                        sym = sym.symbol()
                    if sym is not None and hasattr(sym, "color") and label_text:
                        entries.append((str(label_text), QColor(sym.color().name()).name()))
                    _collect(child)

            _collect(legend)
        for label_text, colour in entries:
            if colour:
                p.setBrush(QColor(colour))
                p.setPen(QPen(QColor("#1a1a1a"), 0.6))
                p.drawRect(QRectF(30, y - 13, 30, 18))
            p.setPen(QColor("#1a1a1a"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(70, y - 15, PW - 110, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignVCenter,
                       label_text)
            y += 28
            if y > HDR + PH + PH - 40:
                break
        if not entries:
            p.setPen(QColor("#1a1a1a"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(30, HDR + PH + 70, PW - 60, 40),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignVCenter, preset_name)
    except Exception:
        p.setPen(QColor("#1a1a1a"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(30, HDR + PH + 70, PW - 60, 40),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignVCenter, preset_name)

    # panel 2: parameters
    param_lines = param_text.splitlines()
    param_lines.append("")
    param_lines.append(f"QML STYLE EXPORT -> {Path(str(qml_path)).name}")
    _text_panel(p, PW, HDR + PH, PW, PH, "2 - PARAMETERS", "values used in this run",
                param_lines)

    p.fillRect(QRectF(0, 0, PW * 2, HDR), QColor("#0b2b28"))
    p.setPen(QColor("#7fe3d6"))
    p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    p.drawText(12, 21, f"PlanX Urban Resilience - {display_name}  ({algo_id})")
    p.setPen(QColor("#9fd6c9"))
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(PW + 12, 21, "Real QGIS run - PlanX Urban Resilience engine")
    p.end()
    img.save(out_png, "PNG")
    return os.path.exists(out_png)


def _fmt_params(params):
    """Human-readable parameter list: file paths are reduced to their name."""
    lines = []
    for k, v in params.items():
        if v is None or v == "":
            continue
        if isinstance(v, str):
            if len(v) > 3 and (":" in v[1:3] or "\\" in v or "/" in v):
                v = Path(v).name
            if len(v) > 92:
                v = v[:89] + "..."
        lines.append(f"{k} = {v}")
    return "\n".join(lines)


# ============================================================ dataset builders
def _write_gpkg(path, crs, wkb_type, fields, rows):
    """Write a small GeoPackage. rows = [(geometry, [values])]."""
    lyr = QgsVectorLayer(f"{wkb_type}?crs={crs}", "tmp", "memory")
    lyr.dataProvider().addAttributes(fields)
    lyr.updateFields()
    feats = []
    for geom, attrs in rows:
        f = QgsFeature(lyr.fields())
        f.setGeometry(geom)
        f.setAttributes(list(attrs))
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = Path(path).stem
    opts.fileEncoding = "UTF-8"
    err = QgsVectorFileWriter.writeAsVectorFormatV3(
        lyr, str(path), QgsProject.instance().transformContext(), opts)
    if err[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"cannot write {path}: {err}")
    return str(path)


def _poly(x1, y1, x2, y2):
    return QgsGeometry.fromPolygonXY([[
        QgsPointXY(x1, y1), QgsPointXY(x2, y1), QgsPointXY(x2, y2),
        QgsPointXY(x1, y2), QgsPointXY(x1, y1)]])


def _line(pts):
    return QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in pts])


def _pt(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


def _flds(*defs):
    f = QgsFields()
    for name, kind in defs:
        f.append(QgsField(name, kind))
    return f


def build_aux_data():
    """DEM, shoreline, vegetation, trees, emission sources, candidate sites,
    planning units and the two hazard periods the synthesis tools consume."""
    print("[..] building auxiliary layers", flush=True)

    # ---- coastal DEM ----------------------------------------------------
    # The raster deliberately reaches past the study envelope on every side,
    # so the sampling in the flood / coastal tools never falls off the edge.
    nx, ny, px = 110, 80, 20
    x0, y0 = -100.0, 1500.0
    dem_path = WORK_DIR / "dem.tif"
    try:
        import numpy as np
        from osgeo import gdal, osr
        xs = x0 + (np.arange(nx) + 0.5) * px
        ys = y0 - (np.arange(ny) + 0.5) * px
        xx, yy = np.meshgrid(xs, ys)
        # a coastal ramp: 14 m inland falling to 0 m at the shoreline
        elev = 14.0 * np.clip((1800.0 - xx) / 1800.0, 0.0, 1.0)
        # a bowl depression so the pluvial tool has somewhere to pond
        dist_bowl = np.sqrt((xx - 700.0) ** 2 + (yy - 500.0) ** 2)
        elev -= np.clip((300.0 - dist_bowl) / 60.0, 0.0, 5.0)
        # a low ridge in the north-west, fading out over 60 m
        dist_ridge = np.sqrt((xx - 300.0) ** 2 + (yy - 1100.0) ** 2)
        elev += np.clip((60.0 - dist_ridge) / 15.0, 0.0, 4.0)
        elev = elev.astype(np.float32)
        ds = gdal.GetDriverByName("GTiff").Create(
            str(dem_path), nx, ny, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((x0, px, 0, y0, 0, -px))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3857)
        ds.SetProjection(srs.ExportToWkt())
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999.0)
        band.WriteArray(elev)
        band.FlushCache()
        ds = None
        LAYERS["dem"] = str(dem_path)
    except Exception as exc:
        print(f"      [WARN] DEM via GDAL failed ({exc}); trying pure-python writer",
              flush=True)
        _write_fallback_dem(dem_path, nx, ny, px, x0, y0)
        LAYERS["dem"] = str(dem_path)

    # ---- coastline -------------------------------------------------------
    LAYERS["coastline"] = _write_gpkg(
        WORK_DIR / "coastline.gpkg", CRS, "LineString",
        _flds(("name", QVariant.String), ("type", QVariant.String)),
        [(_line([(1950, 0), (1950, 1400)]), ["Shoreline", "shoreline"])])

    # ---- vegetation band (wildland-urban interface) ---------------------
    veg_rows = []
    for i in range(6):
        x1 = 60 + i * 40
        veg_rows.append((_poly(x1, 780 + (i % 3) * 40, x1 + 90, 900 + (i % 3) * 40),
                         [f"Forest patch {i + 1}", "forest"]))
    veg_rows.append((_poly(60, 60, 220, 220), ["North woodland", "woodland"]))
    LAYERS["vegetation"] = _write_gpkg(
        WORK_DIR / "vegetation.gpkg", CRS, "Polygon",
        _flds(("name", QVariant.String), ("type", QVariant.String)), veg_rows)

    # ---- street trees ----------------------------------------------------
    tree_rows = []
    for i in range(24):
        x = 480 + (i % 8) * 90
        y = 560 + (i // 8) * 110
        tree_rows.append((_pt(x, y), [f"Tree {i + 1}", "street_tree"]))
    LAYERS["trees"] = _write_gpkg(
        WORK_DIR / "trees.gpkg", CRS, "Point",
        _flds(("name", QVariant.String), ("type", QVariant.String)), tree_rows)

    # ---- emission sources -------------------------------------------------
    LAYERS["emission_sources"] = _write_gpkg(
        WORK_DIR / "emission_sources.gpkg", CRS, "Point",
        _flds(("name", QVariant.String), ("type", QVariant.String)),
        [(_pt(1900, 1180), ["Harbour industrial", "industrial"]),
         (_pt(90, 180), ["Ring road depot", "depot"]),
         (_pt(1000, 1250), ["District boiler", "boiler"])])

    # ---- shelter siting candidates ---------------------------------------
    cand_rows = []
    for r in range(5):
        for c in range(6):
            cand_rows.append((_pt(180 + c * 330, 160 + r * 270),
                              [f"Candidate {r * 6 + c + 1}", "candidate"]))
    LAYERS["candidates"] = _write_gpkg(
        WORK_DIR / "shelter_candidates.gpkg", CRS, "Point",
        _flds(("name", QVariant.String), ("type", QVariant.String)), cand_rows)

    # ---- planning units (5 x 4 grid over the study area) -----------------
    unit_rows = []
    uid = 0
    for r in range(4):
        for c in range(5):
            uid += 1
            x1, y1 = c * 400.0, r * 350.0
            x2, y2 = x1 + 400.0, y1 + 350.0
            population = 180 + (uid * 37) % 420
            score = 22.0 + (uid * 13) % 68
            scen = max(6.0, score - 12.0 - (uid % 5) * 3.0)
            unit_rows.append((_poly(x1, y1, x2, y2), [
                f"Unit {uid:02d}", uid, population,
                round(population / 0.14, 2),        # pop_density (per hectare)
                round(score, 2),                    # score      (baseline hazard)
                round(scen, 2),                     # scen_score (post-intervention)
                round(scen - score, 2),             # delta
                round(0.15 + (uid * 7) % 60 / 100.0, 3),   # diversity
                round(6.0 + (uid * 5) % 18, 2),           # redundancy
                round(0.05 + (uid * 11) % 40 / 100.0, 3),  # green_ratio
                round(0.2 + (uid * 13) % 70 / 100.0, 3),   # cohesion
                round(120.0 + (uid * 45) % 900, 2),        # rec_cost
                round(60.0 + (uid * 30) % 700, 2),         # rec_benefit
                round(25000.0 + (uid * 900) % 90000, 2),   # capex
                round(1800.0 + (uid * 130) % 9000, 2),     # opex
            ]))
    unit_fields = _flds(
        ("name", QVariant.String), ("uid", QVariant.Int),
        ("population", QVariant.Int), ("pop_density", QVariant.Double),
        ("score", QVariant.Double), ("scen_score", QVariant.Double),
        ("delta", QVariant.Double), ("diversity", QVariant.Double),
        ("redundancy", QVariant.Double), ("green_ratio", QVariant.Double),
        ("cohesion", QVariant.Double), ("rec_cost", QVariant.Double),
        ("rec_benefit", QVariant.Double), ("capex", QVariant.Double),
        ("opex", QVariant.Double))
    LAYERS["units"] = _write_gpkg(WORK_DIR / "planning_units.gpkg", CRS, "Polygon",
                                   unit_fields, unit_rows)

    # ---- vulnerability sample points (0-100 values for the IDW tool) -----
    vuln_rows = []
    for i in range(12):
        col = i % 4
        row = i // 4
        x = 250 + col * 500
        y = 250 + row * 420
        value = 18.0 + (i * 7) % 74
        vuln_rows.append((_pt(x, y), [f"Observation {i + 1}", round(value, 2)]))
    LAYERS["vulnerability_points"] = _write_gpkg(
        WORK_DIR / "vulnerability_points.gpkg", CRS, "Point",
        _flds(("name", QVariant.String), ("vulnerability", QVariant.Double)), vuln_rows)

    # ---- two hazard periods for the frequency aggregation tool -----------
    for tag, shift in (("t1", 0.0), ("t2", -11.0)):
        rows = []
        for geom, attrs in unit_rows:
            a = list(attrs)
            a[4] = round(max(5.0, min(100.0, a[4] + shift)), 2)
            rows.append((geom, a))
        LAYERS[f"period_{tag}"] = _write_gpkg(
            WORK_DIR / f"hazard_period_{tag}.gpkg", CRS, "Polygon", unit_fields, rows)

    print("[OK] auxiliary layers ready", flush=True)


# ------------------------------------------------------- street network
STREETS = [
    # name, orientation, position, class, capacity (persons/h), direction
    ("South lane", "h", 100.0, "local", 600, "both"),
    ("Main avenue", "h", 400.0, "arterial", 2400, "both"),
    ("Central boulevard", "h", 700.0, "collector", 1200, "both"),
    ("Market street", "h", 850.0, "collector", 1200, "both"),
    ("North lane", "h", 1100.0, "local", 600, "both"),
    ("Ridge lane", "h", 1350.0, "local", 600, "ft"),
    ("West lane", "v", 150.0, "local", 600, "both"),
    ("Mid block street", "v", 625.0, "collector", 1200, "both"),
    ("East spine", "v", 1025.0, "collector", 1200, "both"),
    ("Canal street", "v", 1425.0, "collector", 1200, "both"),
    ("Harbour road", "v", 1875.0, "local", 600, "both"),
]

#: every street vertex sits on this lattice, so the SNAP_TOLERANCE used by the
#: emergency tools quantises to the true coordinates (no rounding of lengths)
LATTICE = 25.0


def build_road_network():
    """A noded street network serving the demo layout.

    The demo dataset ships four two-vertex roads. The emergency tools build
    their graph from line *vertices*, so a network whose lines cross without a
    shared vertex comes out as four disconnected components and most origins
    read as "Unreachable". This network is densified on a 25 m lattice and
    crosses at shared vertices, which is what a real (OSM-derived) network
    looks like - and because every vertex sits on the lattice, the
    SNAP_TOLERANCE quantisation is exact and the reported distances are true
    distances.

    The street spacing matters too: "Market street" runs along the south face
    of the mixed-use blocks, so the debris envelope of a collapsed building
    really does sever a street and the seismic cascade has something to show.
    """
    rows = []
    for name, orient, pos, cls, cap, direction in STREETS:
        if orient == "h":
            pts = [(float(x), pos) for x in range(0, 2001, int(LATTICE))]
        else:
            pts = [(pos, float(y)) for y in range(0, 1401, int(LATTICE))]
        rows.append((_line(pts), [name, cls, cap, direction]))
    LAYERS["roads"] = _write_gpkg(
        WORK_DIR / "roads_noded.gpkg", CRS, "LineString",
        _flds(("name", QVariant.String), ("class", QVariant.String),
              ("capacity_ph", QVariant.Int), ("direction", QVariant.String)),
        rows)
    print(f"[OK] noded street network ready ({len(rows)} streets, "
          f"{int(LATTICE)} m lattice)", flush=True)


def build_land_parcels():
    """Land parcels = the individual building plots of the demo layout.

    The seismic debris model subtracts parcels *and* buildings from the study
    envelope to obtain the open network, then intersects the debris envelope
    with what is left. Plot-sized parcels (footprint + 5 m) therefore leave the
    debris spread visible in the "open space" network, instead of swallowing it.
    """
    src = load_layer(LAYERS["buildings"], "b")
    if src is None:
        LAYERS["parcels"] = ""
        return
    rows = []
    for feat in src.getFeatures():
        bb = feat.geometry().boundingBox()
        m = 5.0
        rows.append((_poly(bb.xMinimum() - m, bb.yMinimum() - m,
                           bb.xMaximum() + m, bb.yMaximum() + m),
                     [f"Plot {feat['name']}", str(feat["land_use"])]))
    LAYERS["parcels"] = _write_gpkg(
        WORK_DIR / "land_parcels.gpkg", CRS, "Polygon",
        _flds(("name", QVariant.String), ("land_use", QVariant.String)), rows)
    print(f"[OK] {len(rows)} land parcels ready", flush=True)



def _write_fallback_dem(path, nx, ny, px, x0=0.0, y0=1400.0):
    """Minimal GeoTIFF writer used only when GDAL is unavailable."""
    import struct

    header_size = 8
    entries = []
    data = bytearray()
    for y in range(ny):
        yc = y0 - (y + 0.5) * px
        for xi in range(nx):
            xc = x0 + (xi + 0.5) * px
            e = 14.0 * max(0.0, min(1.0, (1800.0 - xc) / 1800.0))
            db = ((xc - 700.0) ** 2 + (yc - 500.0) ** 2) ** 0.5
            e -= max(0.0, min(5.0, (300.0 - db) / 60.0))
            dr = ((xc - 300.0) ** 2 + (yc - 1100.0) ** 2) ** 0.5
            e += max(0.0, min(4.0, (60.0 - dr) / 15.0))
            data += struct.pack("<f", e)
    entries.append((256, 3, 1, struct.pack("<I", nx)))          # width
    entries.append((257, 3, 1, struct.pack("<I", ny)))          # height
    entries.append((258, 3, 1, struct.pack("<H", 1)))           # bits per sample
    entries.append((259, 3, 1, struct.pack("<H", 1)))           # compression
    entries.append((262, 3, 1, struct.pack("<H", 1)))           # photometric
    entries.append((273, 4, 1, struct.pack("<I", 0)))           # strip offset
    entries.append((277, 3, 1, struct.pack("<H", 1)))           # samples
    entries.append((278, 4, 1, struct.pack("<I", ny)))          # rows per strip
    entries.append((279, 4, 1, struct.pack("<I", len(data))))   # strip byte count
    ifd_offset = header_size
    ifd_size = 2 + 12 * len(entries) + 4
    extra_offset = ifd_offset + ifd_size
    out = bytearray(b"II" + struct.pack("<HI", 42, ifd_offset))
    out += struct.pack("<H", len(entries))
    for tag_id, typ, count, value in entries:
        out += struct.pack("<HHI", tag_id, typ, count)
        if typ == 3:
            out += value + b"\x00\x00"
        else:
            out += value
    out += struct.pack("<I", extra_offset)
    out += data
    with open(path, "wb") as fh:
        fh.write(bytes(out))


def build_demo_data():
    """Run the plugin's own synthetic dataset algorithm."""
    print("[..] running synthetic_resilience_demo_dataset", flush=True)
    dest = {name: sh(WORK_DIR / f"demo_{name.lower()}.gpkg")
            for name in ("STUDY_AREA", "BUILDINGS", "ROADS", "IMPERVIOUS", "GREEN",
                         "WATER", "SHELTERS", "SOCIAL_UNITS", "SENSITIVE")}
    res = run("synthetic_resilience_demo_dataset", {"SCALE": 1.0}, dest)
    if res is None:
        print("[FAIL] could not create the synthetic dataset", flush=True)
        return False
    keys = {"STUDY_AREA": "study", "BUILDINGS": "buildings", "ROADS": "roads",
            "IMPERVIOUS": "impervious", "GREEN": "green", "WATER": "water",
            "SHELTERS": "shelters", "SOCIAL_UNITS": "social", "SENSITIVE": "sensitive"}
    for k, short in keys.items():
        LAYERS[short] = sh(WORK_DIR / f"demo_{k.lower()}.gpkg")
    LAYERS["roads_demo"] = LAYERS["roads"]
    PRODUCED["synthetic_resilience_demo_dataset"] = dict(LAYERS)
    print("[OK] synthetic dataset ready (9 layers, EPSG:3857)", flush=True)
    build_road_network()
    build_land_parcels()
    return True


# ============================================================ per-algo setup
def _out(aid, param):
    """Path of an already produced output of `aid`."""
    return PRODUCED.get(aid, {}).get(param, "")


def build_setup(aid):
    """Return (explicit params, list of logical input-layer names)."""
    L = LAYERS
    P = {}
    inp = []

    def use(*keys):
        for k in keys:
            if k in L and k not in inp:
                inp.append(k)

    if aid == "synthetic_resilience_demo_dataset":
        P = {"SCALE": 1.0}

    elif aid == "urban_heat_comfort_risk":
        P = {"STUDY_AREA": L["study"], "BUILDINGS": L["buildings"],
             "IMPERVIOUS": L["impervious"], "GREEN": L["green"], "WATER": L["water"],
             "VULNERABLE": L["social"], "CELL_SIZE": 100.0,
             "COOLING_DISTANCE": 400.0}
        use("study", "buildings", "impervious", "green", "water", "social")

    elif aid == "pluvial_flood_susceptibility":
        P = {"DEM": L["dem"], "STUDY_AREA": L["study"], "BUILDINGS": L["buildings"],
             "ROADS": L["roads"], "DRAINAGE": L["water"], "CELL_SIZE": 100.0,
             "NEIGHBORHOOD": 150.0}
        use("study", "buildings", "roads", "water")

    elif aid == "coastal_slr_exposure":
        P = {"STUDY_AREA": L["study"], "DEM": L["dem"], "COASTLINE": L["coastline"],
             "BUILDINGS": L["buildings"], "ROADS": L["roads"],
             "SCENARIO_PRESET": 1, "CONNECTIVITY_RULE": 0, "CELL_SIZE": 100.0,
             "NEAR_SHORE_BUFFER_M": 250.0}
        use("study", "coastline", "buildings", "roads")

    elif aid == "social_vulnerability_index":
        P = {"AREAS": L["social"], "POPULATION_FIELD": "population",
             "ELDERLY_FIELD": "elderly", "CHILDREN_FIELD": "children",
             "DISABILITY_FIELD": "disability", "LOW_INCOME_FIELD": "low_income"}
        use("social")

    elif aid == "seismic_debris_monte_carlo":
        P = {"INPUT_BUILDINGS": L["buildings"], "FIELD_FLOORS": "floor_count",
             "FIELD_YEAR": "year", "MAGNITUDE": 7.0, "INPUT_PARCELS": L["parcels"],
             "INPUT_STUDY_AREA": L["study"], "FLOOR_HEIGHT": 3.0,
             "DEBRIS_FACTOR": 0.5, "SOLID_VOLUME_RATIO": 0.3, "SEED": 42}
        use("buildings", "parcels", "study")

    elif aid == "emergency_accessibility_shelter_coverage":
        P = {"STUDY_AREA": L["study"], "SHELTERS": L["shelters"],
             "POPULATION_ASSETS": L["buildings"], "BARRIERS": L["impervious"],
             "CELL_SIZE": 100.0, "SERVICE_DISTANCE": 500.0,
             "CRITICAL_DISTANCE": 1200.0}
        use("study", "shelters", "buildings", "impervious")

    elif aid == "network_emergency_accessibility":
        P = {"ROADS": L["roads"], "ORIGINS": L["buildings"],
             "DESTINATIONS": L["shelters"], "SPEED_KMH": 4.5,
             "TARGET_MINUTES": 10.0, "CRITICAL_MINUTES": 25.0,
             "SNAP_TOLERANCE": 25.0}
        use("roads", "buildings", "shelters")

    elif aid == "network_criticality":
        P = {"ROADS": L["roads"], "ORIGINS": L["buildings"],
             "DESTINATIONS": L["shelters"], "SNAP_TOLERANCE": 25.0,
             "ROAD_DIRECTION_FIELD": "direction"}
        use("roads", "buildings", "shelters")

    elif aid == "evacuation_time_simulation":
        P = {"ROADS": L["roads"], "ORIGINS": L["buildings"], "POP_FIELD": "population",
             "SHELTERS": L["shelters"], "CAPACITY_FIELD": "capacity",
             "SPEED_KMH": 30.0, "TARGET_MINUTES": 15.0, "CRITICAL_MINUTES": 45.0,
             "ROAD_CAPACITY_FIELD": "capacity_ph", "ROAD_CLASS_FIELD": "class",
             "ROAD_DIRECTION_FIELD": "direction", "TIMESTEP_MINUTES": 0.0,
             "MAX_TIMESTEPS": 60,
             "SNAP_TOLERANCE": 25.0, "ASSIGN_ORDER": 0}
        use("roads", "buildings", "shelters")

    elif aid == "seismic_cascade_accessibility":
        P = {"ROADS": L["roads"],
             "DEBRIS": _out("seismic_debris_monte_carlo", "OUTPUT_HAZARD_MODEL"),
             "ORIGINS": L["buildings"], "DESTINATIONS": L["shelters"],
             "SNAP_TOLERANCE": 25.0}
        use("roads", "buildings", "shelters")

    elif aid == "optimal_shelter_siting":
        P = {"CANDIDATES": L["candidates"], "DEMAND": L["buildings"],
             "POP_FIELD": "population", "MAX_DISTANCE": 400.0, "NUM_SITES": 3,
             "EXISTING": L["shelters"]}
        use("candidates", "buildings", "shelters")

    elif aid == "evacuation_shelter_arrival_summary":
        P = {"INPUT": _out("evacuation_time_simulation", "OUTPUT_ORIGINS"),
             "SHELTER_FIELD": "evac_shelter", "POP_FIELD": "evac_pop",
             "TIMESTEP_FIELD": "", "MINUTES_FIELD": "evac_min",
             "MINUTE_BIN": 1.0}
        use("buildings")

    elif aid == "air_quality_exposure_screening":
        P = {"STUDY_AREA": L["study"], "ROADS": L["roads"],
             "EMISSION_SOURCES": L["emission_sources"], "SENSITIVE": L["sensitive"],
             "GREEN_BUFFERS": L["green"], "CELL_SIZE": 100.0,
             "ROAD_DISTANCE": 300.0, "SOURCE_DISTANCE": 600.0}
        use("study", "roads", "emission_sources", "sensitive", "green")

    elif aid == "green_infrastructure_drought_stress":
        P = {"GREEN": L["green"], "STUDY_AREA": L["study"],
             "IMPERVIOUS": L["impervious"], "WATER": L["water"], "TREES": L["trees"],
             "MAX_WATER_DISTANCE": 500.0}
        use("green", "study", "impervious", "water", "trees")

    elif aid == "wui_exposure_screening":
        P = {"STUDY_AREA": L["study"], "VEGETATION": L["vegetation"],
             "BUILDINGS": L["buildings"], "ROADS": L["roads"], "DEM": L["dem"],
             "CELL_SIZE": 100.0, "WUI_BUFFER": 300.0, "MAX_EGRESS_DIST": 400.0}
        use("study", "vegetation", "buildings", "roads")

    elif aid == "join_scores_to_planning_units":
        # first pass: heat / flood / air / access / wildfire
        P = {"UNITS": L["units"],
             "SOURCE1": _out("urban_heat_comfort_risk", "OUTPUT_GRID"),
             "FIELD1": "heat_score", "OUT1": "heat_score",
             "SOURCE2": _out("pluvial_flood_susceptibility", "OUTPUT_GRID"),
             "FIELD2": "flood_score", "OUT2": "flood_score",
             "SOURCE3": _out("air_quality_exposure_screening", "OUTPUT_GRID"),
             "FIELD3": "air_score", "OUT3": "air_score",
             "SOURCE4": _out("emergency_accessibility_shelter_coverage", "OUTPUT_GRID"),
             "FIELD4": "access_score", "OUT4": "access_score",
             "SOURCE5": _out("wui_exposure_screening", "OUTPUT_GRID"),
             "FIELD5": "wui_score", "OUT5": "wui_score"}
        use("units")

    elif aid == "multi_hazard_composite_index":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "HAZARD_FIELDS": ["heat_score", "flood_score", "air_score",
                               "access_score", "wui_score"],
             "WEIGHTS": "0.25,0.25,0.20,0.15,0.15"}
        use("units")

    elif aid == "equity_adjusted_priority":
        P = {"INPUT": _out("multi_hazard_composite_index", "OUTPUT"),
             "HAZARD_FIELD": "mh_score", "SVI_FIELD": "svi_score",
             "EQUITY_WEIGHT": 0.5}
        use("units")

    elif aid == "climate_adaptation_priority_synthesis":
        P = {"UNITS": _out("join_scores_to_planning_units", "OUTPUT"),
             "HEAT_FIELD": "heat_score", "FLOOD_FIELD": "flood_score",
             "SOCIAL_FIELD": "svi_score", "AIR_FIELD": "air_score",
             "ACCESS_FIELD": "access_score", "DROUGHT_FIELD": "stress_score",
             "WUI_FIELD": "wui_score", "COASTAL_FIELD": "slr_score"}
        use("units")

    elif aid == "climate_projection_overlay":
        P = {"INPUT": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "SCORE_FIELD": "adapt_score", "SCENARIO": 3, "CUSTOM_FACTOR": 1.3}
        use("units")

    elif aid == "recovery_capacity_index":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "DIVERSITY_FIELDS": ["diversity"], "REDUNDANCY_FIELD": "redundancy",
             "REDUNDANCY_SCALE": 25.0, "GREEN_FIELD": "green_ratio",
             "COHESION_FIELD": "cohesion", "WEIGHTS": "1,1,1,1"}
        use("units")

    elif aid == "risk_recovery_priority_matrix":
        P = {"INPUT": _out("recovery_capacity_index", "OUTPUT"),
             "HAZARD_FIELD": "mh_score", "RECOVERY_FIELD": "rc_score",
             "RECOVERY_WEIGHT": 0.5}
        use("units")

    elif aid == "hotspot_analysis_getis_ord":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "VALUE_FIELD": "score", "DISTANCE": 500.0, "WEIGHT_METHOD": 0}
        use("units")

    elif aid == "lisa_local_moran":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "VALUE_FIELD": "score", "DISTANCE": 500.0, "WEIGHT_METHOD": 0}
        use("units")

    elif aid == "population_weighted_exposure":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "SCORE_FIELD": "score", "POP_FIELD": "population"}
        use("units")

    elif aid == "hazard_frequency_aggregation":
        P = {"UNITS": L["units"], "SOURCES": [L["period_t1"], L["period_t2"]],
             "SCORE_FIELD": "score", "THRESHOLD": 50.0, "AGG_MODE": 2}
        use("units")

    elif aid == "vulnerability_surface_idw":
        P = {"POINTS": L["vulnerability_points"], "VALUE_FIELD": "vulnerability",
             "STUDY": L["study"], "CELL_SIZE": 200.0, "POWER": 2.0,
             "MAX_NEIGHBOURS": 12}
        use("vulnerability_points", "study")

    elif aid == "critical_infrastructure_exposure":
        P = {"HAZARD": _out("urban_heat_comfort_risk", "OUTPUT_GRID"),
             "HAZARD_FIELD": "heat_score", "FACILITIES": L["shelters"],
             "CRITICALITY_DEFAULT": 1.0, "NAME_FIELD": "name"}
        use("shelters")

    elif aid == "scenario_sensitivity":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "COMPONENT_FIELDS": ["heat_score", "flood_score", "air_score"],
             "WEIGHTS": "0.4,0.4,0.2", "PERTURB": 0.3, "SAMPLES": 60, "SEED": 42}
        use("units")

    elif aid == "risk_trend_hotspot":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "LATER_SCORE": "scen_score", "DELTA_FIELD": "delta", "DISTANCE": 500.0,
             "DELTA_TOL": 1.0}
        use("units")

    elif aid == "cost_benefit_analyzer":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "SCORE_FIELD": "score", "UNIT_COST": 100.0, "DEFAULT_REDUCTION": 0.7,
             "POP_FIELD": "population"}
        use("units")

    elif aid == "pareto_optimal_selector":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "COST_FIELD": "rec_cost", "BENEFIT_FIELD": "rec_benefit"}
        use("units")

    elif aid == "lifecycle_cost_calculator":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "CAPEX_FIELD": "capex", "OPEX_FIELD": "opex", "MAINT_INTERVAL": 5,
             "MAINT_COST": 200.0, "REPL_YEARS": 20, "REPL_COST": 500.0,
             "HORIZON": 25, "DISCOUNT": 4.0, "AREA_SCALE": False}
        use("units")

    elif aid == "resilience_time_series":
        P = {"EARLIER": _out("join_scores_to_planning_units", "OUTPUT"),
             "EARLIER_ID": "uid", "EARLIER_SCORE": "score",
             "LATER": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "LATER_ID": "uid", "LATER_SCORE": "adapt_score",
             "TARGET_VALUE": 40.0}
        use("units")

    elif aid == "resilience_scenario_comparison":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "BASELINE_FIELD": "score", "SCENARIO_FIELD": "scen_score",
             "THRESHOLD": 5.0}
        use("units")

    elif aid == "scenario_planning_template":
        P = {"INPUT": L["units"], "BASE_SCORE_FIELD": "score",
             "DEFAULT_BASE_SCORE": 50.0, "SCENARIO_NAME": "Green corridor retrofit",
             "INTERVENTION_TYPE": 0, "EXPECTED_REDUCTION": 15.0}
        use("units")

    elif aid == "resilience_score_html_report":
        P = {"INPUT": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "SCORE_FIELD": "adapt_score", "CLASS_FIELD": "adapt_class",
             "DRIVER_FIELD": "drivers",
             "TITLE": "PlanX Urban Resilience - Adaptation Priority Report"}
        use("units")

    elif aid == "resilience_studio_brief_markdown":
        P = {"INPUT": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "SCORE_FIELD": "adapt_score", "CLASS_FIELD": "adapt_class",
             "DRIVER_FIELD": "drivers",
             "TITLE": "PlanX Urban Resilience - Studio Brief",
             "STUDY_CONTEXT": "Demo district, EPSG:3857 synthetic fixture, "
                              "screening-level screening for teaching use."}
        use("units")

    elif aid == "recommended_actions_report":
        P = {"INPUT": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "SCORE_FIELD": "adapt_score", "CLASS_FIELD": "adapt_class",
             "HAZARD_FIELD": "drivers", "UNIT_NAME_FIELD": "name", "TOP_N": 10,
             "PROJECT": "PlanX Urban Resilience - Demo District"}
        use("units")

    elif aid == "apply_resilience_symbology":
        target = _out("climate_adaptation_priority_synthesis", "OUTPUT")
        P = {"LAYER": target, "FIELD": "adapt_score", "PRESET": 0, "REFRESH": True}
        use("units")

    elif aid == "bivariate_choropleth_symbology":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "RISK_FIELD": "score", "VULN_FIELD": "pop_density"}
        use("units")

    elif aid == "resilience_pdf_atlas":
        P = {"INPUT": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "SCORE_FIELD": "adapt_score", "CLASS_FIELD": "adapt_class",
             "TITLE": "PlanX Urban Resilience - Demo District Atlas",
             "SUBTITLE": "Screening atlas (not engineering-grade simulation)",
             "AUTHOR": "Geophilo", "PROJECT": "PlanX Urban Resilience",
             "METHOD": 1, "ATLAS_PRESET": 0}
        use("units")

    elif aid == "multi_hazard_correlation_matrix":
        P = {"INPUT": _out("join_scores_to_planning_units", "OUTPUT"),
             "FIELDS": ["heat_score", "flood_score", "air_score", "access_score",
                        "wui_score"],
             "PROJECT": "PlanX Urban Resilience - Demo District"}
        use("units")

    elif aid == "risk_3d_volume_export":
        P = {"INPUT": _out("climate_adaptation_priority_synthesis", "OUTPUT"),
             "SCORE_FIELD": "adapt_score", "MAX_HEIGHT": 60.0, "COLOR_RAMP": 0}
        use("units")

    else:
        return None, []

    return P, inp


# ============================================================ param resolving
def _first_field(path, skip=()):
    try:
        lyr = load_layer(path, "probe")
        if lyr is None:
            return ""
        for f in lyr.fields():
            if f.name().lower() in skip:
                continue
            return f.name()
    except Exception:
        pass
    return ""


def resolve_params(aid, algo, P):
    """Repair the explicit setup against the algorithm's own definitions."""
    out = {}
    for prm in algo.parameterDefinitions():
        name = prm.name()
        if isinstance(prm, (QgsProcessingParameterFeatureSink,
                            QgsProcessingParameterRasterDestination,
                            QgsProcessingParameterVectorDestination,
                            QgsProcessingParameterFileDestination)):
            continue
        if isinstance(prm, QgsProcessingParameterField):
            cur = P.get(name)
            if isinstance(cur, (list, tuple)):
                out[name] = list(cur)
                continue
            parent = prm.parentLayerParameterName()
            src = P.get(parent)
            if not isinstance(src, str) or not os.path.exists(src):
                out[name] = ""
                continue
            if isinstance(cur, str) and cur:
                lyr = load_layer(src, "probe")
                if lyr is not None and lyr.fields().lookupField(cur) >= 0:
                    out[name] = cur
                    continue
            cand = _first_field(src)
            out[name] = cand or ""
            continue
        if isinstance(prm, QgsProcessingParameterEnum):
            cur = P.get(name)
            if isinstance(cur, int) and not isinstance(cur, bool) \
                    and 0 <= cur < len(prm.options()):
                out[name] = cur
            else:
                out[name] = prm.defaultValue()
            continue
        if isinstance(prm, QgsProcessingParameterNumber):
            cur = P.get(name)
            if isinstance(cur, (int, float)) and not isinstance(cur, bool):
                out[name] = cur
            else:
                out[name] = prm.defaultValue()
            continue
        if isinstance(prm, QgsProcessingParameterBoolean):
            cur = P.get(name)
            out[name] = cur if isinstance(cur, bool) else prm.defaultValue()
            continue
        if isinstance(prm, QgsProcessingParameterCrs):
            out[name] = P.get(name) or CRS
            continue
        if isinstance(prm, QgsProcessingParameterExtent):
            continue
        if isinstance(prm, QgsProcessingParameterMultipleLayers):
            cur = P.get(name)
            out[name] = list(cur) if isinstance(cur, (list, tuple)) else []
            continue
        if isinstance(prm, QgsProcessingParameterVectorLayer):
            cur = P.get(name)
            out[name] = cur if cur else ""
            continue
        if isinstance(prm, QgsProcessingParameterRasterLayer):
            cur = P.get(name)
            out[name] = cur if cur else ""
            continue
        if isinstance(prm, QgsProcessingParameterFile):
            out[name] = P.get(name) or ""
            continue
        cur = P.get(name)
        if cur is None:
            try:
                out[name] = prm.defaultValue()
            except Exception:
                out[name] = ""
        else:
            out[name] = cur
    for k, v in P.items():
        out.setdefault(k, v)
    return out


def dest_paths(aid, algo):
    """Give every destination parameter a file path."""
    o = {}
    for prm in algo.parameterDefinitions():
        if isinstance(prm, (QgsProcessingParameterFeatureSink,
                            QgsProcessingParameterVectorDestination)):
            o[prm.name()] = sh(WORK_DIR / f"{aid}__{prm.name()}.gpkg")
        elif isinstance(prm, QgsProcessingParameterRasterDestination):
            o[prm.name()] = sh(WORK_DIR / f"{aid}__{prm.name()}.tif")
        elif isinstance(prm, QgsProcessingParameterFileDestination):
            ext = ""
            try:
                ext = prm.defaultFileExtension() or ""
            except Exception:
                pass
            if not ext:
                ext = ".out"
            if not ext.startswith("."):
                ext = "." + ext
            o[prm.name()] = sh(WORK_DIR / f"{aid}__{prm.name()}{ext}")
    return o


# ============================================================ execution order
ORDER = [
    # 0 - demo
    "synthetic_resilience_demo_dataset",
    # 2 - heat
    "urban_heat_comfort_risk",
    # 3 - flood and coastal
    "pluvial_flood_susceptibility",
    "coastal_slr_exposure",
    # 4 - social
    "social_vulnerability_index",
    # 1 - seismic
    "seismic_debris_monte_carlo",
    # 5 - emergency
    "emergency_accessibility_shelter_coverage",
    "network_emergency_accessibility",
    "network_criticality",
    "evacuation_time_simulation",
    "seismic_cascade_accessibility",
    "optimal_shelter_siting",
    "evacuation_shelter_arrival_summary",
    # 6 - air
    "air_quality_exposure_screening",
    # 7 - drought and wildfire
    "green_infrastructure_drought_stress",
    "wui_exposure_screening",
    # 8 - synthesis
    "join_scores_to_planning_units",
    "multi_hazard_composite_index",
    "equity_adjusted_priority",
    "climate_adaptation_priority_synthesis",
    "climate_projection_overlay",
    "recovery_capacity_index",
    "risk_recovery_priority_matrix",
    "hotspot_analysis_getis_ord",
    "lisa_local_moran",
    "population_weighted_exposure",
    "hazard_frequency_aggregation",
    "vulnerability_surface_idw",
    "critical_infrastructure_exposure",
    "scenario_sensitivity",
    "risk_trend_hotspot",
    "cost_benefit_analyzer",
    "pareto_optimal_selector",
    "lifecycle_cost_calculator",
    # 9 - report and QA
    "resilience_time_series",
    "resilience_scenario_comparison",
    "scenario_planning_template",
    "resilience_score_html_report",
    "resilience_studio_brief_markdown",
    "recommended_actions_report",
    "apply_resilience_symbology",
    "bivariate_choropleth_symbology",
    "resilience_pdf_atlas",
    "multi_hazard_correlation_matrix",
    "risk_3d_volume_export",
]


def _write_manifest(aid, algo, png_rel, caption, panels, params, seconds, extra=None):
    entry = {
        "algo_id": aid,
        "display_name": algo.displayName(),
        "group": algo.group(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "screenshots": [{
            "step": 1,
            "caption": caption,
            "path": png_rel,
            "panels": panels,
        }],
        "params": {k: (v if isinstance(v, (int, float, bool)) else str(v))
                   for k, v in params.items() if v not in (None, "")},
        "seconds": seconds,
    }
    if extra:
        entry.update(extra)
    with open(MANIFEST_DIR / f"screenshots_{aid}.json", "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)


def main():
    only = None
    if "--algo" in sys.argv:
        only = sys.argv[sys.argv.index("--algo") + 1]
    if "--list" in sys.argv:
        for aid in sorted(ALGOS):
            print(f"{aid}\t{ALGOS[aid].displayName()}")
        return 0
    if "--clean" in sys.argv:
        # the scratch directory is regenerated on every run; removing it keeps
        # the repository (and the published portal bundle) free of generated
        # GeoPackages, rasters and print atlases
        if WORK_DIR.exists():
            shutil.rmtree(WORK_DIR, ignore_errors=True)
        print(f"[OK] removed {WORK_DIR}", flush=True)
        return 0

    build_aux_data()
    if not build_demo_data():
        return 1

    order = [a for a in ORDER if a in ALGOS]
    for aid in ALGOS:
        if aid not in order:
            order.append(aid)
    capture_only = only
    if only:
        # the tools chain off each other, so a single-tool run still has to
        # execute everything that comes before it - only the screenshot of the
        # requested tool is captured.
        if only in order:
            order = order[:order.index(only) + 1]
        else:
            order = [only]

    ok, fail, noparam = 0, 0, 0
    results = {}
    print(f"\n=== STAGE 2: {len(order)} algorithms ===", flush=True)

    for i, aid in enumerate(order, 1):
        t0 = time.time()
        algo = ALGOS[aid]
        P, inp_keys = build_setup(aid)
        if P is None:
            print(f"[{i:2d}/{len(order)}] {aid}: NO SETUP", flush=True)
            noparam += 1
            continue
        P = resolve_params(aid, algo, P)
        dests = dest_paths(aid, algo)
        res = run(aid, P, dests)
        if res is None:
            print(f"[{i:2d}/{len(order)}] {aid}: RUN FAILED", flush=True)
            results[aid] = {"ok": False, "reason": "run failed"}
            fail += 1
            continue

        produced = {}
        out_layers = []
        for k, v in res.items():
            if isinstance(v, str) and os.path.exists(v):
                produced[k] = v
                lyr = load_layer(v, f"{aid}_{k}")
                if lyr is not None and lyr.isValid():
                    out_layers.append(lyr)
                    try:
                        if lyr.id() not in PROJECT.mapLayers():
                            PROJECT.addMapLayer(lyr)
                    except Exception:
                        pass
            elif hasattr(v, "isValid") and hasattr(v, "name"):
                out_layers.append(v)
        PRODUCED[aid] = produced

        in_layers = [load_layer(LAYERS[k], k) for k in inp_keys] if inp_keys else []
        in_layers = [ly for ly in in_layers if ly is not None]

        png_rel = f"screenshots/{aid}/{aid}_4panel.png"
        png = SHOT_DIR / aid / f"{aid}_4panel.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        secs = round(time.time() - t0, 1)
        param_text = _fmt_params(P)

        if capture_only and aid != capture_only:
            # prerequisite of the requested tool: the result is kept, the
            # screenshot is left untouched
            results[aid] = {"ok": True, "display_name": algo.displayName(),
                            "group": algo.group(), "seconds": secs,
                            "prerequisite": True}
            print(f"[{i:2d}/{len(order)}] {aid}: prerequisite OK ({secs}s)",
                  flush=True)
            ok += 1
            continue

        # ---- special case: a tool whose result is a style, not a layer ----
        if aid == "apply_resilience_symbology":
            target = produced.get("OUTPUT_QML", "")
            styled_src = P.get("LAYER")
            styled = load_layer(styled_src, "styled") if isinstance(styled_src, str) \
                else styled_src
            raw = load_layer(styled_src, "raw") if isinstance(styled_src, str) else None
            if styled is not None:
                try:
                    if styled.id() not in PROJECT.mapLayers():
                        PROJECT.addMapLayer(styled)
                except Exception:
                    pass
                # the algorithm styles the layer in place; re-run it on our own
                # object so the captured render shows the plugin's preset rather
                # than the guide's automatic styling
                run(aid, dict(P, LAYER=styled), dests)
            ok_capture = capture_symbology_4panel(
                aid, algo.displayName(), raw, styled, param_text, sh(png),
                target, algo.parameterDefinitions()[2].options()[
                    P.get("PRESET", 0) if isinstance(P.get("PRESET", 0), int) else 0])
            results[aid] = {"ok": ok_capture, "display_name": algo.displayName(),
                            "group": algo.group(), "png": png_rel,
                            "params": {k: (v if isinstance(v, (int, float, bool)) else str(v))
                                       for k, v in P.items() if v not in (None, "")},
                            "seconds": secs}
            _write_manifest(aid, algo, png_rel,
                            f"{algo.displayName()} - style presets applied to the "
                            f"resilience layer", ["Input (Raw)", "Parameters",
                                                  "Output (Styled)", "Legend"],
                            P, secs)
            print(f"[{i:2d}/{len(order)}] {aid}: OK (style) ({secs}s)", flush=True)
            ok += 1
            continue

        # ---- report-style output (html / md / pdf) ------------------------
        text_outputs = [(k, v) for k, v in produced.items()
                        if v.lower().endswith((".html", ".htm", ".md", ".txt", ".out"))]
        if not out_layers and text_outputs:
            k, path = text_outputs[0]
            title = Path(path).name
            capture_report_4panel(aid, algo.displayName(), in_layers, path,
                                  param_text, sh(png), title)
            results[aid] = {"ok": True, "display_name": algo.displayName(),
                            "group": algo.group(), "png": png_rel, "report": path,
                            "params": {k: (v if isinstance(v, (int, float, bool)) else str(v))
                                       for k, v in P.items() if v not in (None, "")},
                            "seconds": secs}
            _write_manifest(aid, algo, png_rel,
                            f"{algo.displayName()} - report output preview",
                            ["Input Data", "Parameters + Report", "Report Map",
                             "Report Output"], P, secs)
            print(f"[{i:2d}/{len(order)}] {aid}: OK (report) ({secs}s)", flush=True)
            ok += 1
            continue

        if aid == "resilience_pdf_atlas" and not out_layers:
            pdf = produced.get("OUTPUT", "")
            size_kb = round(os.path.getsize(pdf) / 1024.0, 1) if os.path.exists(pdf) else 0
            capture_report_4panel(aid, algo.displayName(), in_layers,
                                  WORK_DIR / "_atlas_note.txt", param_text, sh(png),
                                  f"PDF atlas ({size_kb} kB)")
            (WORK_DIR / "_atlas_note.txt").write_text(
                f"Atlas PDF written to {pdf}\nSize: {size_kb} kB\n"
                f"Method: {algo.parameterDefinitions()[7].options()[P.get('METHOD', 1)]}\n"
                f"Preset: {algo.parameterDefinitions()[8].options()[P.get('ATLAS_PRESET', 0)]}\n",
                encoding="utf-8")
            results[aid] = {"ok": True, "display_name": algo.displayName(),
                            "group": algo.group(), "png": png_rel, "report": pdf,
                            "seconds": secs}
            _write_manifest(aid, algo, png_rel,
                            f"{algo.displayName()} - print atlas preview",
                            ["Input Data", "Parameters", "Atlas Map", "Atlas Output"],
                            P, secs)
            print(f"[{i:2d}/{len(order)}] {aid}: OK (pdf) ({secs}s)", flush=True)
            ok += 1
            continue

        if not out_layers:
            print(f"[{i:2d}/{len(order)}] {aid}: no spatial output", flush=True)
            results[aid] = {"ok": False, "reason": "no spatial output"}
            fail += 1
            continue

        capture_4panel(aid, algo.displayName(), in_layers, out_layers,
                       param_text, sh(png))
        results[aid] = {"ok": True, "display_name": algo.displayName(),
                        "group": algo.group(), "png": png_rel,
                        "params": {k: (v if isinstance(v, (int, float, bool)) else str(v))
                                   for k, v in P.items() if v not in (None, "")},
                        "seconds": secs}
        _write_manifest(aid, algo, png_rel,
                        f"{algo.displayName()} - 4-panel view "
                        f"(Input | Parameters | Raw Output | Styled Output)",
                        ["Input Data", "Parameters", "Raw Output", "Styled Output"],
                        P, secs)
        print(f"[{i:2d}/{len(order)}] {aid}: OK ({secs}s)", flush=True)
        ok += 1

    summary = {"total": len(order), "ok": ok, "failed": fail, "no_setup": noparam,
               "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results}
    with open(MANIFEST_DIR / "screenshots_all.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n=== DONE: {ok} ok / {fail} failed / {noparam} no-setup / "
          f"{len(order)} total ===", flush=True)
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
