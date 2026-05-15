# -*- coding: utf-8 -*-
from __future__ import annotations

import processing
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsProject


MODULES = [
    {
        "title": "Synthetic Resilience Demo Dataset",
        "algorithm": "planx_urban_resilience:synthetic_resilience_demo_dataset",
        "group": "0 - Demo and QA",
        "inputs": "No project data required; only a scale multiplier.",
        "outputs": "Synthetic study area, buildings, roads, impervious surfaces, green infrastructure, water, shelters, social units and sensitive receptors.",
    },
    {
        "title": "Seismic Debris and Logistics",
        "algorithm": "planx_urban_resilience:sismik_risk_dinamik_analizor_v2",
        "group": "1 - Seismic",
        "inputs": "Buildings, parcels, study/road area, floor and construction year fields.",
        "outputs": "Collapse probability, debris envelope, road blockage and clearance corridors.",
    },
    {
        "title": "Urban Heat Comfort Risk",
        "algorithm": "planx_urban_resilience:urban_heat_comfort_risk",
        "group": "2 - Heat",
        "inputs": "Study area, buildings, optional hardscape, green/cooling areas and vulnerable assets.",
        "outputs": "Heat risk grid, priority cooling zones and exposed assets.",
    },
    {
        "title": "Pluvial Flood Susceptibility",
        "algorithm": "planx_urban_resilience:pluvial_flood_susceptibility",
        "group": "3 - Flood",
        "inputs": "DEM, study area, optional buildings, roads and drainage/water network.",
        "outputs": "Flood susceptibility grid, exposed buildings and exposed road segments.",
    },
    {
        "title": "Social Vulnerability Index",
        "algorithm": "planx_urban_resilience:social_vulnerability_index",
        "group": "4 - Social",
        "inputs": "Neighborhood or census polygons with optional population, elderly, children, disability and deprivation fields.",
        "outputs": "0-100 social vulnerability index with risk classes and data-quality flags.",
    },
    {
        "title": "Emergency Accessibility and Shelter Coverage",
        "algorithm": "planx_urban_resilience:emergency_accessibility_shelter_coverage",
        "group": "5 - Emergency",
        "inputs": "Study area, shelters or safe assembly areas, optional assets and barriers.",
        "outputs": "Accessibility deficit grid and underserved buildings, facilities or population assets.",
    },
    {
        "title": "Air Quality / Urban Exposure",
        "algorithm": "planx_urban_resilience:air_quality_exposure_screening",
        "group": "6 - Air",
        "inputs": "Study area, major roads, optional emission sources, sensitive receptors and green buffers.",
        "outputs": "Air exposure grid and exposed sensitive receptors.",
    },
    {
        "title": "Drought and Green Infrastructure Stress",
        "algorithm": "planx_urban_resilience:green_infrastructure_drought_stress",
        "group": "7 - Drought",
        "inputs": "Green infrastructure polygons, optional impervious surfaces, water layers and tree points.",
        "outputs": "Green infrastructure stress index and high-priority patches.",
    },
    {
        "title": "Climate Adaptation Priority Synthesis",
        "algorithm": "planx_urban_resilience:climate_adaptation_priority_synthesis",
        "group": "8 - Synthesis",
        "inputs": "Planning units with joined 0-100 risk fields from other modules.",
        "outputs": "Adaptation priority score, class, top drivers and missing-data flags.",
    },
    {
        "title": "Scenario Comparison / Delta Map",
        "algorithm": "planx_urban_resilience:resilience_scenario_comparison",
        "group": "9 - Report and QA",
        "inputs": "One layer with baseline and scenario 0-100 score fields.",
        "outputs": "Delta, percent change, improved/stable/worsened class and action hint.",
    },
    {
        "title": "Resilience Score HTML Report",
        "algorithm": "planx_urban_resilience:resilience_score_html_report",
        "group": "9 - Report and QA",
        "inputs": "Any scored resilience layer with optional class and driver fields.",
        "outputs": "Standalone HTML summary with score statistics, class distribution and top drivers.",
    },
]


class UrbanResilienceDashboard(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("PlanX Urban Resilience")
        self.resize(980, 700)
        self._build_ui()
        self._refresh_report()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QDialog { background: #f4f7fb; color: #243044; }
            QListWidget {
                background: #102027;
                color: #dce9ed;
                border: none;
                border-radius: 10px;
                padding: 8px;
                font-weight: 600;
            }
            QListWidget::item { padding: 12px 10px; border-radius: 7px; }
            QListWidget::item:selected { background: #0f766e; color: white; }
            QLabel#heroTitle { font-size: 22px; font-weight: 800; color: #12343b; }
            QLabel#heroSub { color: #64748b; }
            QGroupBox {
                border: 1px solid #d8e0ea;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px 10px 10px 10px;
                background: white;
                font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QPushButton {
                min-height: 32px;
                border-radius: 7px;
                padding: 6px 12px;
                background: white;
                border: 1px solid #cbd5e1;
            }
            QPushButton:hover { background: #eef6f4; border-color: #0f766e; }
            QPushButton#primaryButton {
                color: white;
                background: #0f766e;
                border: 1px solid #0f766e;
                font-weight: 700;
            }
            QTextBrowser {
                border: 1px solid #d8e0ea;
                border-radius: 8px;
                background: white;
                padding: 10px;
            }
            """
        )
        shell = QHBoxLayout(self)
        self.nav = QListWidget()
        self.nav.setFixedWidth(170)
        for label in ("Overview", "Data", "Modules", "Run", "Report", "Test"):
            QListWidgetItem(label, self.nav)
        self.nav.setCurrentRow(0)
        shell.addWidget(self.nav)

        content = QVBoxLayout()
        title = QLabel("PlanX Urban Resilience")
        title.setObjectName("heroTitle")
        subtitle = QLabel("Prepare resilience layers, launch screening modules and review project readiness from one QGIS panel.")
        subtitle.setObjectName("heroSub")
        subtitle.setWordWrap(True)
        content.addWidget(title)
        content.addWidget(subtitle)

        self.pages = [
            self._overview_page(),
            self._data_page(),
            self._modules_page(),
            self._run_page(),
            self._report_page(),
            self._test_page(),
        ]
        for i, page in enumerate(self.pages):
            page.setVisible(i == 0)
            content.addWidget(page, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        content.addWidget(buttons)
        shell.addLayout(content, 1)
        self.nav.currentRowChanged.connect(self._switch_page)

    def _overview_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QTextBrowser()
        intro.setHtml(
            """
            <h2>Urban resilience cockpit</h2>
            <p>This suite currently includes a synthetic QA dataset generator, seismic debris logistics, urban heat comfort risk, pluvial flood susceptibility, social vulnerability, emergency accessibility, air exposure, green infrastructure stress, adaptation priority synthesis, scenario comparison, and HTML reporting.</p>
            <p>The first release is offline-first: load your own QGIS layers, review readiness, then run the Processing modules.</p>
            """
        )
        layout.addWidget(intro)
        layout.addWidget(self._module_cards())
        return page

    def _data_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.data_report = QTextBrowser()
        layout.addWidget(self.data_report)
        refresh = QPushButton("Refresh data readiness")
        refresh.clicked.connect(self._refresh_report)
        layout.addWidget(refresh)
        return page

    def _modules_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._module_cards(with_buttons=True))
        return page

    def _run_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        run_group = QGroupBox("Open Processing tools")
        grid = QGridLayout(run_group)
        for row, module in enumerate(MODULES):
            label = QLabel(f"<b>{module['title']}</b><br><span style='color:#64748b'>{module['outputs']}</span>")
            label.setWordWrap(True)
            button = QPushButton("Open")
            button.setObjectName("primaryButton")
            button.clicked.connect(lambda _checked=False, alg=module["algorithm"]: self._open_algorithm(alg))
            grid.addWidget(label, row, 0)
            grid.addWidget(button, row, 1)
        layout.addWidget(run_group)
        layout.addStretch(1)
        return page

    def _report_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_report = QTextBrowser()
        layout.addWidget(self.summary_report)
        return page

    def _test_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        test_group = QGroupBox("Synthetic smoke-test workflow")
        test_layout = QVBoxLayout(test_group)
        info = QLabel(
            "Generate the synthetic dataset first, then run Heat, Air, Social, Emergency and Drought modules with the generated layers. Flood still needs a DEM raster; Synthesis needs joined risk fields."
        )
        info.setWordWrap(True)
        test_layout.addWidget(info)
        button = QPushButton("Generate Synthetic Dataset")
        button.setObjectName("primaryButton")
        button.clicked.connect(lambda _checked=False: self._open_algorithm("planx_urban_resilience:synthetic_resilience_demo_dataset"))
        test_layout.addWidget(button)
        layout.addWidget(test_group)
        layout.addStretch(1)
        return page

    def _module_cards(self, with_buttons=False):
        group = QGroupBox("Modules")
        grid = QGridLayout(group)
        for idx, module in enumerate(MODULES):
            card = QGroupBox(module["title"])
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(f"<b>{module['group']}</b>"))
            body = QLabel(f"Inputs: {module['inputs']}<br>Outputs: {module['outputs']}")
            body.setWordWrap(True)
            card_layout.addWidget(body)
            if with_buttons:
                button = QPushButton("Open Processing")
                button.clicked.connect(lambda _checked=False, alg=module["algorithm"]: self._open_algorithm(alg))
                card_layout.addWidget(button)
            grid.addWidget(card, idx // 2, idx % 2)
        future = QGroupBox("Future modules")
        future_layout = QVBoxLayout(future)
        future_label = QLabel("Next candidates: GEE-backed historical climate connectors, network-based evacuation/accessibility, PDF atlas export, and scenario library templates.")
        future_label.setWordWrap(True)
        future_layout.addWidget(future_label)
        next_row = (len(MODULES) + 1) // 2
        grid.addWidget(future, next_row, 1)
        return group

    def _refresh_report(self):
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        vectors = [layer for layer in layers if hasattr(layer, "featureCount")]
        rasters = [layer for layer in layers if not hasattr(layer, "featureCount")]
        crs_values = sorted({layer.crs().authid() for layer in layers if hasattr(layer, "crs") and layer.crs().isValid()})
        html = f"""
        <h2>Project data readiness</h2>
        <p><b>Loaded layers:</b> {len(layers)} ({len(vectors)} vector, {len(rasters)} raster)</p>
        <p><b>CRS values:</b> {', '.join(crs_values) if crs_values else 'No CRS found'}</p>
        <h3>Suggested layer preparation</h3>
        <ul>
          <li>Seismic: buildings, parcels, study/road area, floor and construction year fields.</li>
          <li>Demo/QA: run the synthetic dataset generator to create artificial test layers for module smoke tests.</li>
          <li>Heat: study area, buildings, hardscape/roads, green areas or trees, optional water and vulnerable assets.</li>
          <li>Flood: DEM raster, study area, optional buildings, roads and drainage/water network.</li>
          <li>Social: neighborhood/census polygons with optional population, elderly, children, disability and deprivation fields.</li>
          <li>Emergency: study area, shelters/safe assembly areas, optional population assets and barriers.</li>
          <li>Air: study area, traffic corridors, optional emission sources, sensitive receptors and green buffers.</li>
          <li>Drought: green infrastructure polygons, optional impervious context, water/blue infrastructure and tree points.</li>
          <li>Synthesis: one polygon layer containing joined 0-100 risk fields from previous modules.</li>
          <li>Report/QA: compare baseline vs scenario score fields or export a compact HTML score report.</li>
        </ul>
        <p><b>Note:</b> These modules are screening tools for planning support, not engineering-grade simulation models.</p>
        """
        self.data_report.setHtml(html)
        self.summary_report.setHtml(html)

    def _switch_page(self, idx):
        for i, page in enumerate(self.pages):
            page.setVisible(i == idx)

    def _open_algorithm(self, algorithm_id):
        processing.execAlgorithmDialog(algorithm_id)
