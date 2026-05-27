# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

import processing
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsProject


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
        "title": "Network Emergency Accessibility",
        "algorithm": "planx_urban_resilience:network_emergency_accessibility",
        "group": "5 - Emergency",
        "inputs": "Road network, origin assets or buildings, and shelter/safe-area destinations.",
        "outputs": "Network distance, travel time, access class, QA flag and underserved origins.",
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
        "title": "Multi-Hazard Composite Index",
        "algorithm": "planx_urban_resilience:multi_hazard_composite_index",
        "group": "8 - Synthesis",
        "inputs": "Planning units with two or more 0-100 hazard score fields (e.g. seismic, heat, flood, social, etc.).",
        "outputs": "Composite score, class, dominant hazard label, Shannon diversity index, top 3 drivers, and data-gap count per unit.",
    },
    {
        "title": "Equity-Adjusted Adaptation Priority",
        "algorithm": "planx_urban_resilience:equity_adjusted_priority",
        "group": "8 - Synthesis",
        "inputs": "Planning units with a hazard/composite score field and a social vulnerability score field (both 0-100).",
        "outputs": "Equity factor, raw and normalized adjusted priority score, and class. Surfaces high-risk + high-vulnerability units.",
    },
    {
        "title": "Climate Projection Overlay",
        "algorithm": "planx_urban_resilience:climate_projection_overlay",
        "group": "8 - Synthesis",
        "inputs": "Any scored layer with a 0-100 hazard/composite field; choose a warming scenario or custom factor.",
        "outputs": "Today vs projected score (clamped 0-100), delta, delta class (Improved/Stable/Slight/Notable/Major) and scenario metadata.",
    },
    {
        "title": "Network Criticality (edge betweenness)",
        "algorithm": "planx_urban_resilience:network_criticality",
        "group": "5 - Emergency",
        "inputs": "Road network + origins (assets/buildings) + destinations (shelters/safe areas).",
        "outputs": "Per-edge usage count and 0-100 criticality score; high-score edges are bottlenecks whose closure forces the most reroutes.",
    },
    {
        "title": "Evacuation Time Simulation",
        "algorithm": "planx_urban_resilience:evacuation_time_simulation",
        "group": "5 - Emergency",
        "inputs": "Road network (capacity field or road class), origins with population, shelters with capacity; optional timestep queue (0 = instant).",
        "outputs": "Origins (travel_min, evac_delay_min, evac_min, evac_timestep, class), shelter utilization, edges (trip_count, load_pop, congestion_pct, bottleneck_score).",
    },
    {
        "title": "Recovery Capacity Index",
        "algorithm": "planx_urban_resilience:recovery_capacity_index",
        "group": "8 - Synthesis",
        "inputs": "Planning units with optional land-use mix CSV, road-access count, green share and social-cohesion proxy fields.",
        "outputs": "Four sub-scores, composite rc_score (0-100), rc_class and rc_data_gap. Pair with Adaptation Priority for high-risk + low-recovery units.",
    },
    {
        "title": "Risk-Recovery Priority Matrix",
        "algorithm": "planx_urban_resilience:risk_recovery_priority_matrix",
        "group": "8 - Synthesis",
        "inputs": "Planning units with hazard/adaptation score (0-100) and recovery capacity score (e.g. rc_score).",
        "outputs": "rr_priority_score, deficit/factor diagnostics, Immediate/High/Medium/Monitor class. Highlights high-risk + low-recovery units.",
    },
    {
        "title": "Join Hazard Scores to Planning Units",
        "algorithm": "planx_urban_resilience:join_scores_to_planning_units",
        "group": "8 - Synthesis",
        "inputs": "Planning-unit polygons plus up to five score layers with field and output column names.",
        "outputs": "Same units with joined score fields (max intersecting value) ready for composite or adaptation synthesis.",
    },
    {
        "title": "Hot-Spot Cluster Analysis (Getis-Ord Gi*)",
        "algorithm": "planx_urban_resilience:hotspot_analysis_getis_ord",
        "group": "8 - Synthesis",
        "inputs": "Scored polygon/point layer + numeric value field + distance band (map units); choose inverse-distance or fixed-band spatial weights.",
        "outputs": "Per-feature gi_zscore, gi_pvalue, gi_class (Hot-99 / Hot-95 / Hot-90 / Not significant / Cold-90 / Cold-95 / Cold-99). Surfaces statistically significant clusters above what choropleths can show.",
    },
    {
        "title": "Population-Weighted Exposure",
        "algorithm": "planx_urban_resilience:population_weighted_exposure",
        "group": "8 - Synthesis",
        "inputs": "Scored planning units + EITHER a population field on the same layer OR a separate population point/polygon layer with its own count field.",
        "outputs": "Per-unit pop_total, pop_exposed (= score/100 × pop), exposure class, plus a study-area summary in the log (total population by risk class + top 10 exposed units).",
    },
    {
        "title": "Bivariate Choropleth Symbology (risk × vulnerability)",
        "algorithm": "planx_urban_resilience:bivariate_choropleth_symbology",
        "group": "9 - Report and QA",
        "inputs": "Polygon layer with two numeric score fields (e.g. multi-hazard composite and social vulnerability).",
        "outputs": "Output layer with bv_class / bv_risk_bin / bv_vuln_bin fields, classified into 3×3 quantile bins, and a Stevens-style bivariate categorised renderer applied automatically.",
    },
    {
        "title": "3D Risk Volume Export (GeoJSON for PlanX 3D City)",
        "algorithm": "planx_urban_resilience:risk_3d_volume_export",
        "group": "9 - Report and QA",
        "inputs": "Scored polygon layer + 0-100 score field + max extrusion height + optional base height field + colour ramp (Yellow-Red / Blue-Red / Greys).",
        "outputs": "GeoJSON in EPSG:4326 with extrusion_height + color_hex + score_norm attributes; in-QGIS preview layer in source CRS with the same fields. Drops into PlanX 3D City Viewer / Three.js / Cesium.",
    },
    {
        "title": "Pareto-Optimal Intervention Selector",
        "algorithm": "planx_urban_resilience:pareto_optimal_selector",
        "group": "8 - Synthesis",
        "inputs": "Layer with a cost field (lower = better) and a benefit field (higher = better). Pair with the Cost-Benefit Analyzer outputs (cb_cost / cb_benefit).",
        "outputs": "Per-feature pareto_rank (1 = top frontier, 2 = next skin, etc.), pareto_dominated, pareto_dominates. rank == 1 is the budget-bounded best pick set.",
    },
    {
        "title": "Multi-Period Hazard Frequency Aggregation",
        "algorithm": "planx_urban_resilience:hazard_frequency_aggregation",
        "group": "8 - Synthesis",
        "inputs": "Planning units + 2-8 source hazard layers + shared score field name + threshold + aggregation mode (Mean / Max / Frequency-weighted mean).",
        "outputs": "Per-unit hf_frequency, hf_mean, hf_max, hf_min, hf_composite (0-100), hf_class. Collapses temporal climate / scenario snapshots into one composite.",
    },
    {
        "title": "Vulnerability Surface (IDW interpolation)",
        "algorithm": "planx_urban_resilience:vulnerability_surface_idw",
        "group": "8 - Synthesis",
        "inputs": "Source point layer with a numeric value field + study-area polygon + cell size + IDW power + optional search radius and neighbour cap.",
        "outputs": "Polygon grid clipped to the study area with vs_value (interpolated), vs_class and vs_n_points (count of contributing source points) per cell.",
    },
    {
        "title": "Multi-Hazard Correlation Matrix (HTML)",
        "algorithm": "planx_urban_resilience:multi_hazard_correlation_matrix",
        "group": "9 - Report and QA",
        "inputs": "Layer with 2-12 numeric score fields on the same features (e.g. multi-hazard composite + recovery + SVI + adaptation priority).",
        "outputs": "Standalone HTML heatmap report (Pearson + Spearman) with top-10 correlations table, plus a long-format QGIS table (field_a, field_b, pearson_r, spearman_r, n_pairs).",
    },
    {
        "title": "Risk Trend Hot-Spot (Gi* × Δ score)",
        "algorithm": "planx_urban_resilience:risk_trend_hotspot",
        "group": "8 - Synthesis",
        "inputs": "Layer with a later-snapshot score field and a delta field (typically the resilience_time_series outputs ts_later_score and ts_delta).",
        "outputs": "Per-unit trh_gi_z, trh_gi_significant, trh_delta, trh_label — Rising/Stable/Cooling hot or cold spot, Hot/Cold no cluster, or Not significant.",
    },
    {
        "title": "Optimal Shelter Siting (greedy maximal coverage)",
        "algorithm": "planx_urban_resilience:optimal_shelter_siting",
        "group": "5 - Emergency",
        "inputs": "Candidate sites + demand units (population field) + max distance + K (number of new sites) + optional existing-shelter layer.",
        "outputs": "Candidates annotated with oss_selected, oss_rank (1..K), oss_pop_added, oss_pop_total_cum; per-step coverage curve and uncovered top-10 in the log.",
    },
    {
        "title": "Lifecycle Cost Calculator (25-year NPV)",
        "algorithm": "planx_urban_resilience:lifecycle_cost_calculator",
        "group": "8 - Synthesis",
        "inputs": "Planning units with capex / opex / optional per-feature maintenance and replacement cost fields + interval / horizon / discount rate parameters + optional area scaling for per-m² values.",
        "outputs": "Per-feature lc_capex_npv, lc_opex_npv, lc_maintenance_npv, lc_replacement_npv, lc_total_npv, lc_annualised (equivalent flat annual cost).",
    },
    {
        "title": "LISA Local Moran's I (cluster + outlier)",
        "algorithm": "planx_urban_resilience:lisa_local_moran",
        "group": "8 - Synthesis",
        "inputs": "Scored polygon/point layer + numeric value field + distance band; choose inverse-distance or fixed-band spatial weights.",
        "outputs": "Per-feature lisa_z, lisa_lag, lisa_I, lisa_pvalue, lisa_quadrant (HH / LL / HL / LH / Not significant). Companion to Gi* — adds outlier classes Gi* doesn't expose.",
    },
    {
        "title": "Cost-Benefit Analyzer (planning prioritisation)",
        "algorithm": "planx_urban_resilience:cost_benefit_analyzer",
        "group": "8 - Synthesis",
        "inputs": "Scored layer + default unit cost (or per-feature cost field) + default reduction factor (or per-feature field) + optional population weight.",
        "outputs": "Per-feature cb_cost, cb_benefit, cb_ratio and 1-N cb_priority_rank, ordered by B/C descending. Log prints the cumulative-budget curve (10/25/50/75/90 % of benefit).",
    },
    {
        "title": "Critical Infrastructure Exposure",
        "algorithm": "planx_urban_resilience:critical_infrastructure_exposure",
        "group": "8 - Synthesis",
        "inputs": "Hazard polygon layer with a 0-100 score field + critical-facility layer (points or polygons) + optional criticality / name / class fields.",
        "outputs": "Per-facility ci_hazard, ci_criticality, ci_combined (0-100) and ci_exposure_class. Top 10 and mean-by-class breakdown printed to log.",
    },
    {
        "title": "Seismic Cascade: Debris → Network Degradation",
        "algorithm": "planx_urban_resilience:seismic_cascade_accessibility",
        "group": "5 - Emergency",
        "inputs": "Road network + debris polygons (typically the seismic Monte Carlo OUTPUT_HAZARD_MODEL) + origins + shelter destinations.",
        "outputs": "Origins with cas_pre_dist / cas_post_dist / cas_delta_dist / cas_pre_reachable / cas_post_reachable / cas_status (Newly cut off / Always cut off / Worse / Same / Recovered). Cross-domain hazard cascading.",
    },
    {
        "title": "Recommended Actions Report (Markdown)",
        "algorithm": "planx_urban_resilience:recommended_actions_report",
        "group": "9 - Report and QA",
        "inputs": "Scored layer with optional class and dominant-hazard fields; choose top-N to list and (optionally) a unit-name / project name.",
        "outputs": "Markdown report with class distribution table, top-N units table, and curated intervention checklists per detected hazard family (heat, flood, seismic, social, air, drought, emergency).",
    },
    {
        "title": "Scenario Sensitivity Analysis",
        "algorithm": "planx_urban_resilience:scenario_sensitivity",
        "group": "8 - Synthesis",
        "inputs": "Planning units with two or more component score fields; optional nominal weights, perturbation band and LHS sample count.",
        "outputs": "Baseline/mean/std, p05/p95, range and ss_stability (0-100) showing how robust each unit's composite is to weight choices.",
    },
    {
        "title": "Resilience Time-Series Tracker",
        "algorithm": "planx_urban_resilience:resilience_time_series",
        "group": "9 - Report and QA",
        "inputs": "Earlier and later snapshots of the same scored layer joined on a stable unit ID field.",
        "outputs": "Per-unit delta, percent change, trend (Improved/Stable/Worsened) and optional target gap.",
    },
    {
        "title": "Resilience PDF Atlas",
        "algorithm": "planx_urban_resilience:resilience_pdf_atlas",
        "group": "9 - Report and QA",
        "inputs": "Scored layer with 0-100 field; optional class field; map-book preset (A3/A4/Studio); title and metadata.",
        "outputs": "Multi-page PDF (cover, overview, per-class maps) via QgsLayout.",
    },
    {
        "title": "Evacuation Shelter Arrival Summary",
        "algorithm": "planx_urban_resilience:evacuation_shelter_arrival_summary",
        "group": "9 - Report and QA",
        "inputs": "Evacuation origin outputs with evac_shelter, evac_pop and evac_timestep or evac_min.",
        "outputs": "Per-shelter arrival table (step, arrivals, cumulative, pct) and optional HTML summary.",
    },
    {
        "title": "Scenario Comparison / Delta Map",
        "algorithm": "planx_urban_resilience:resilience_scenario_comparison",
        "group": "9 - Report and QA",
        "inputs": "One layer with baseline and scenario 0-100 score fields.",
        "outputs": "Delta, percent change, improved/stable/worsened class and action hint.",
    },
    {
        "title": "Scenario Planning Template",
        "algorithm": "planx_urban_resilience:scenario_planning_template",
        "group": "9 - Report and QA",
        "inputs": "Planning units or scored layer, optional baseline score field and intervention settings.",
        "outputs": "Editable scenario worksheet with baseline/proposed score fields and notes.",
    },
    {
        "title": "Resilience Score HTML Report",
        "algorithm": "planx_urban_resilience:resilience_score_html_report",
        "group": "9 - Report and QA",
        "inputs": "Any scored resilience layer with optional class and driver fields.",
        "outputs": "Standalone HTML summary with score statistics, class distribution and top drivers.",
    },
    {
        "title": "Resilience Studio Brief (Markdown)",
        "algorithm": "planx_urban_resilience:resilience_studio_brief_markdown",
        "group": "9 - Report and QA",
        "inputs": "Any scored resilience layer plus optional class/driver fields and study context.",
        "outputs": "Markdown brief with executive summary, key metrics, limitations and suggested actions.",
    },
    {
        "title": "Apply Resilience Symbology",
        "algorithm": "planx_urban_resilience:apply_resilience_symbology",
        "group": "9 - Report and QA",
        "inputs": "Any scored or classified resilience layer.",
        "outputs": "In-place QGIS renderer update and optional QML style export.",
    },
]


_MOJIBAKE_FIXES = {
    "â€”": "-",
    "â€“": "-",
    "â†’": "->",
    "Î”": "Delta",
    "Ã—": "x",
    "â€¦": "...",
    "Â²": "m2",
}


def _normalize_ui_text(text: str) -> str:
    value = text
    for old, new in _MOJIBAKE_FIXES.items():
        value = value.replace(old, new)
    return value


def _normalize_module_rows(rows):
    normalized = []
    for row in rows:
        fixed = dict(row)
        for key in ("title", "group", "inputs", "outputs"):
            fixed[key] = _normalize_ui_text(str(row.get(key, "")))
        normalized.append(fixed)
    return normalized


MODULES = _normalize_module_rows(MODULES)
IS_QGIS4 = int(getattr(Qgis, "QGIS_VERSION_INT", 0)) >= 40000
DASHBOARD_SIZE = (960, 680) if IS_QGIS4 else (980, 700)
NAV_WIDTH = 158 if IS_QGIS4 else 170
RUN_BUTTON_MIN_WIDTH = 90 if IS_QGIS4 else 96


def _processing_provider_enabled() -> bool:
    return int(getattr(Qgis, "QGIS_VERSION_INT", 0)) < 40000


class UrbanResilienceDashboard(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("PlanX Urban Resilience")
        self.resize(*DASHBOARD_SIZE)
        self._build_ui()
        self._refresh_report()

    def _build_ui(self):
        hero_title_size = 21 if IS_QGIS4 else 22
        nav_item_padding = 10 if IS_QGIS4 else 12
        group_radius = 7 if IS_QGIS4 else 8
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
            QListWidget::item { padding: %(nav_item_padding)dpx 10px; border-radius: 7px; }
            QListWidget::item:selected { background: #0f766e; color: white; }
            QLabel#heroTitle { font-size: %(hero_title_size)dpx; font-weight: 800; color: #12343b; }
            QLabel#heroSub { color: #64748b; }
            QGroupBox {
                border: 1px solid #d8e0ea;
                border-radius: %(group_radius)dpx;
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
                border-radius: %(group_radius)dpx;
                background: white;
                padding: 10px;
            }
            """
            % {
                "hero_title_size": hero_title_size,
                "nav_item_padding": nav_item_padding,
                "group_radius": group_radius,
            }
        )
        shell = QHBoxLayout(self)
        shell.setContentsMargins(8, 8, 8, 8)
        shell.setSpacing(10)
        self.nav = QListWidget()
        self.nav.setFixedWidth(NAV_WIDTH)
        for label in ("Overview", "Data", "Modules", "Run", "Report", "Test", "Beta"):
            QListWidgetItem(label, self.nav)
        self.nav.setCurrentRow(0)
        shell.addWidget(self.nav)

        content = QVBoxLayout()
        content.setSpacing(8)
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
            self._beta_page(),
        ]
        for i, page in enumerate(self.pages):
            page.setVisible(i == 0)
            content.addWidget(page, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        content.addWidget(buttons)
        shell.addLayout(content, 1)
        self.nav.currentRowChanged.connect(self._switch_page)

    def _overview_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QTextBrowser()
        intro.setMaximumHeight(180)
        intro.setHtml(
            """
            <h2>Urban resilience cockpit</h2>
            <p>This suite includes synthetic QA data, seismic debris, heat, flood, social vulnerability, Euclidean and network emergency access, network criticality, evacuation time simulation, air and drought screening, multi-hazard and equity-adjusted synthesis, climate projection overlay, recovery capacity, scenario sensitivity, time-series tracking, scenario templates/comparison, HTML/Markdown/PDF reporting, and QGIS style presets.</p>
            <p>The first release is offline-first: load your own QGIS layers, review readiness, then run the Processing modules.</p>
            """
        )
        layout.addWidget(intro)

        # Module cards in a scroll area so the overview never overflows the dialog.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self._module_cards())
        layout.addWidget(scroll, 1)
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

        # Search filter - narrows visible modules by title / inputs / outputs.
        search_bar = QLineEdit()
        search_bar.setPlaceholderText("Search modules (title, inputs, outputs)...")
        search_bar.setClearButtonEnabled(True)
        layout.addWidget(search_bar)

        # Scroll area wrapping grouped category cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        cards_widget, modules_index = self._build_grouped_cards(with_buttons=True)
        scroll.setWidget(cards_widget)
        layout.addWidget(scroll, 1)

        search_bar.textChanged.connect(lambda text: self._filter_modules(text, modules_index))
        return page

    def _run_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        search_bar = QLineEdit()
        search_bar.setPlaceholderText("Search to open a Processing tool...")
        search_bar.setClearButtonEnabled(True)
        layout.addWidget(search_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        run_widget, run_index = self._build_run_rows()
        scroll.setWidget(run_widget)
        layout.addWidget(scroll, 1)

        search_bar.textChanged.connect(lambda text: self._filter_modules(text, run_index))
        return page

    @staticmethod
    def _matches(text: str, module: dict) -> bool:
        if not text:
            return True
        needle = text.strip().lower()
        haystack = " ".join((
            module.get("title", ""),
            module.get("group", ""),
            module.get("inputs", ""),
            module.get("outputs", ""),
        )).lower()
        return needle in haystack

    def _filter_modules(self, text: str, index):
        """index = list[(QWidget, dict)] — show/hide row widgets and roll up empty group boxes."""
        groups_visible: dict = {}
        for widget, module in index:
            visible = self._matches(text, module)
            widget.setVisible(visible)
            group = widget.parent()
            while group is not None and not isinstance(group, QGroupBox):
                group = group.parent()
            if group is not None:
                groups_visible[group] = groups_visible.get(group, False) or visible
        for group, any_visible in groups_visible.items():
            group.setVisible(any_visible)

    def _report_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_report = QTextBrowser()
        layout.addWidget(self.summary_report)
        buttons = QHBoxLayout()
        copy_issue = QPushButton("Copy Issue Template")
        copy_issue.clicked.connect(self._copy_issue_template)
        buttons.addWidget(copy_issue)
        refresh = QPushButton("Refresh readiness")
        refresh.clicked.connect(self._refresh_report)
        buttons.addWidget(refresh)
        layout.addLayout(buttons)
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

    def _beta_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.beta_report = QTextBrowser()
        layout.addWidget(self.beta_report)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh beta checks")
        refresh.setObjectName("primaryButton")
        refresh.clicked.connect(self._refresh_report)
        row.addWidget(refresh)
        copy_issue = QPushButton("Copy Issue Template")
        copy_issue.clicked.connect(self._copy_issue_template)
        row.addWidget(copy_issue)
        copy_diag = QPushButton("Copy Diagnostics")
        copy_diag.clicked.connect(self._copy_diagnostics_report)
        row.addWidget(copy_diag)
        copy_smoke = QPushButton("Copy Smoke Plan")
        copy_smoke.clicked.connect(self._copy_smoke_test_plan)
        row.addWidget(copy_smoke)
        copy_release = QPushButton("Copy Release Notes Draft")
        copy_release.clicked.connect(self._copy_release_notes_draft)
        row.addWidget(copy_release)
        copy_hub = QPushButton("Copy Hub Changelog Draft")
        copy_hub.clicked.connect(self._copy_hub_changelog_draft)
        row.addWidget(copy_hub)
        export_html = QPushButton("Export Beta HTML")
        export_html.clicked.connect(self._export_beta_html_report)
        row.addWidget(export_html)
        run_demo = QPushButton("Run Synthetic Dataset")
        run_demo.clicked.connect(
            lambda _checked=False: self._open_algorithm("planx_urban_resilience:synthetic_resilience_demo_dataset")
        )
        row.addWidget(run_demo)
        open_heat = QPushButton("Open Heat Tool")
        open_heat.clicked.connect(
            lambda _checked=False: self._open_algorithm("planx_urban_resilience:urban_heat_comfort_risk")
        )
        row.addWidget(open_heat)
        open_emergency = QPushButton("Open Network Access")
        open_emergency.clicked.connect(
            lambda _checked=False: self._open_algorithm("planx_urban_resilience:network_emergency_accessibility")
        )
        row.addWidget(open_emergency)
        layout.addLayout(row)
        return page

    def _module_cards(self, with_buttons=False):
        """Legacy entry: returns a QWidget wrapping grouped cards.

        Kept for the Overview page (no search there); for filterable pages use
        `_build_grouped_cards`.
        """
        widget, _ = self._build_grouped_cards(with_buttons=with_buttons)
        return widget

    def _build_grouped_cards(self, with_buttons=False):
        """Build a vertical layout of category group-boxes, each holding the
        module cards that belong to that category.

        Returns:
            (container_widget, index)
            index = list[(card_widget, module_dict)] for search filtering.
        """
        # Group modules by their "group" field (e.g. "1 - Seismic", "2 - Heat").
        ordered_groups: list[str] = []
        bucket: dict[str, list[dict]] = {}
        for module in MODULES:
            key = module.get("group", "Other")
            if key not in bucket:
                bucket[key] = []
                ordered_groups.append(key)
            bucket[key].append(module)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        index: list = []
        for group_name in ordered_groups:
            group_box = QGroupBox(group_name)
            grid = QGridLayout(group_box)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            for idx, module in enumerate(bucket[group_name]):
                card = QGroupBox(module["title"])
                card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                card_layout = QVBoxLayout(card)
                body = QLabel(f"Inputs: {module['inputs']}<br>Outputs: {module['outputs']}")
                body.setWordWrap(True)
                card_layout.addWidget(body)
                if with_buttons:
                    button = QPushButton("Open Processing")
                    button.setObjectName("primaryButton")
                    button.clicked.connect(
                        lambda _checked=False, alg=module["algorithm"]: self._open_algorithm(alg)
                    )
                    card_layout.addWidget(button)
                grid.addWidget(card, idx // 2, idx % 2)
                index.append((card, module))
            outer.addWidget(group_box)

        # Future-work hint stays at the bottom
        future = QGroupBox("Future modules")
        future_layout = QVBoxLayout(future)
        future_label = QLabel(
            "Next candidates: GEE-backed climate connectors and evacuation directional-network refinements. "
            "See ROADMAP.md for details."
        )
        future_label.setWordWrap(True)
        future_layout.addWidget(future_label)
        outer.addWidget(future)
        outer.addStretch(1)
        return container, index

    def _build_run_rows(self):
        """Compact "Open Processing tool" rows grouped by category."""
        ordered_groups: list[str] = []
        bucket: dict[str, list[dict]] = {}
        for module in MODULES:
            key = module.get("group", "Other")
            if key not in bucket:
                bucket[key] = []
                ordered_groups.append(key)
            bucket[key].append(module)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        index: list = []
        for group_name in ordered_groups:
            group_box = QGroupBox(group_name)
            grid = QGridLayout(group_box)
            for row, module in enumerate(bucket[group_name]):
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                label = QLabel(
                    f"<b>{module['title']}</b>"
                    f"<br><span style='color:#64748b'>{module['outputs']}</span>"
                )
                label.setWordWrap(True)
                button = QPushButton("Open")
                button.setObjectName("primaryButton")
                button.setMinimumWidth(RUN_BUTTON_MIN_WIDTH)
                button.setMaximumWidth(RUN_BUTTON_MIN_WIDTH + 24)
                button.clicked.connect(
                    lambda _checked=False, alg=module["algorithm"]: self._open_algorithm(alg)
                )
                row_layout.addWidget(label, 1)
                row_layout.addWidget(button)
                grid.addWidget(row_widget, row, 0)
                index.append((row_widget, module))
            outer.addWidget(group_box)

        outer.addStretch(1)
        return container, index

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
          <li>Emergency: study area, shelters/safe assembly areas, optional population assets and barriers; for network analysis also load a connected road line layer.</li>
          <li>Air: study area, traffic corridors, optional emission sources, sensitive receptors and green buffers.</li>
          <li>Drought: green infrastructure polygons, optional impervious context, water/blue infrastructure and tree points.</li>
          <li>Synthesis: one polygon layer containing joined 0-100 risk fields from previous modules.</li>
          <li>Report/QA: create scenario templates, compare baseline vs scenario score fields, export HTML/Markdown reports, or apply a PlanX style preset.</li>
        </ul>
        <p><b>Note:</b> These modules are screening tools for planning support, not engineering-grade simulation models.</p>
        """
        self.data_report.setHtml(html)
        self.summary_report.setHtml(html)
        self.beta_report.setHtml(self._build_beta_html(layers, vectors, rasters, crs_values))

    def _build_beta_html(self, layers, vectors, rasters, crs_values):
        algo_total, algo_available, missing = self._algorithm_registry_status()
        checks = []
        checks.append(("Project has layers", "OK" if len(layers) > 0 else "WARN", f"{len(layers)} loaded"))
        checks.append(("Vector coverage", "OK" if len(vectors) >= 3 else "WARN", f"{len(vectors)} vector layers"))
        checks.append(("CRS consistency", "OK" if len(crs_values) <= 2 and len(crs_values) > 0 else "WARN",
                       ", ".join(crs_values) if crs_values else "No CRS found"))
        checks.append(("Raster availability (for flood)", "OK" if len(rasters) > 0 else "WARN", f"{len(rasters)} raster layers"))
        checks.append(("Module catalog", "OK" if len(MODULES) >= 40 else "WARN", f"{len(MODULES)} modules listed"))
        checks.append(("Algorithm registry", "OK" if algo_total == algo_available else "WARN", f"{algo_available}/{algo_total} available"))
        module_rows = self._core_module_readiness(layers, vectors, rasters)
        warn_count = len([c for c in checks if c[1] != "OK"])
        warn_count += len([m for m in module_rows if m[1] != "OK"])
        status = "READY" if warn_count == 0 else "NOT READY"
        status_tr = "HAZIR" if warn_count == 0 else "HAZIR DEGIL"
        rows = "".join(
            f"<tr><td>{name}</td><td><b>{st}</b></td><td>{val}</td></tr>"
            for name, st, val in checks
        )
        missing_html = ""
        if missing:
            items = "".join(f"<li>{m}</li>" for m in missing[:12])
            missing_html = f"<h3>Missing algorithms</h3><ul>{items}</ul>"
        module_checks_html = "".join(
            f"<tr><td>{name}</td><td><b>{st}</b></td><td>{val}</td></tr>"
            for name, st, val in module_rows
        )
        return f"""
        <h2>Beta readiness snapshot: {status} / {status_tr}</h2>
        <p><b>Generated:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <table border="1" cellspacing="0" cellpadding="6">
          <tr><th>Check</th><th>Status</th><th>Value</th></tr>
          {rows}
        </table>
        <h3>Core module readiness (heuristic)</h3>
        <table border="1" cellspacing="0" cellpadding="6">
          <tr><th>Module</th><th>Status</th><th>Evidence</th></tr>
          {module_checks_html}
        </table>
        {missing_html}
        <p><b>Tip:</b> Run Synthetic Dataset first, then Heat/Air/Social/Emergency/Drought, and finally Synthesis + Reporting checks.</p>
        """

    @staticmethod
    def _algorithm_registry_status():
        reg = QgsApplication.processingRegistry()
        missing = []
        for module in MODULES:
            alg = reg.algorithmById(module.get("algorithm", ""))
            if alg is None:
                missing.append(module.get("algorithm", ""))
        return len(MODULES), len(MODULES) - len(missing), missing

    def _copy_issue_template(self):
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        layer_names = [getattr(layer, "name", lambda: "unknown")() for layer in layers]
        crs_values = sorted({layer.crs().authid() for layer in layers if hasattr(layer, "crs") and layer.crs().isValid()})
        text = (
            "PlanX Urban Resilience Issue Template\n"
            "=====================================\n\n"
            "Summary:\n-\n\n"
            "Expected behavior:\n-\n\n"
            "Actual behavior:\n-\n\n"
            "Reproduction steps:\n1.\n2.\n3.\n\n"
            f"Loaded layers ({len(layer_names)}):\n- " + "\n- ".join(layer_names[:30]) + "\n\n"
            f"CRS values: {', '.join(crs_values) if crs_values else 'No CRS found'}\n\n"
            "Notes:\n-\n"
        )
        QApplication.clipboard().setText(text)

    def _copy_diagnostics_report(self):
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        vectors = [layer for layer in layers if hasattr(layer, "featureCount")]
        rasters = [layer for layer in layers if not hasattr(layer, "featureCount")]
        crs_values = sorted({layer.crs().authid() for layer in layers if hasattr(layer, "crs") and layer.crs().isValid()})
        algo_total, algo_available, missing = self._algorithm_registry_status()
        module_rows = self._core_module_readiness(layers, vectors, rasters)
        text = (
            "PlanX Urban Resilience Diagnostics\n"
            "==================================\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Loaded layers: {len(layers)}\n"
            f"Vector layers: {len(vectors)}\n"
            f"Raster layers: {len(rasters)}\n"
            f"CRS values: {', '.join(crs_values) if crs_values else 'No CRS found'}\n"
            f"Module catalog size: {len(MODULES)}\n"
            f"Algorithms available: {algo_available}/{algo_total}\n"
            f"Missing algorithms: {', '.join(missing) if missing else 'None'}\n"
            "Core module readiness:\n- " + "\n- ".join(
                f"{name}: {status} ({evidence})" for name, status, evidence in module_rows
            ) + "\n"
        )
        QApplication.clipboard().setText(text)

    def _copy_smoke_test_plan(self):
        text = (
            "PlanX Urban Resilience Smoke Test Plan\n"
            "======================================\n"
            "1) Run Synthetic Resilience Demo Dataset\n"
            "2) Run Urban Heat Comfort Risk\n"
            "3) Run Air Quality / Urban Exposure\n"
            "4) Run Social Vulnerability Index\n"
            "5) Run Emergency Accessibility and Shelter Coverage\n"
            "6) Run Network Emergency Accessibility\n"
            "7) (Optional) Run Pluvial Flood Susceptibility if DEM is available\n"
            "8) Join scores to planning units\n"
            "9) Run Multi-Hazard Composite Index + Adaptation Priority\n"
            "10) Export one reporting output (HTML/Markdown/PDF)\n"
            "\n"
            "Acceptance:\n"
            "- No algorithm crash\n"
            "- Outputs created with expected fields/classes\n"
            "- Dashboard Beta checks return READY or explained WARNs\n"
        )
        QApplication.clipboard().setText(text)

    def _copy_release_notes_draft(self):
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        vectors = [layer for layer in layers if hasattr(layer, "featureCount")]
        rasters = [layer for layer in layers if not hasattr(layer, "featureCount")]
        algo_total, algo_available, missing = self._algorithm_registry_status()
        module_rows = self._core_module_readiness(layers, vectors, rasters)
        ready_modules = [name for name, st, _ in module_rows if st == "OK"]
        warn_modules = [name for name, st, _ in module_rows if st != "OK"]
        draft = (
            "PlanX Urban Resilience - Beta Readiness Draft\n"
            "============================================\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Layers loaded: {len(layers)} (vector {len(vectors)}, raster {len(rasters)})\n"
            f"Algorithm registry: {algo_available}/{algo_total} available\n"
            f"Missing algorithms: {', '.join(missing) if missing else 'None'}\n"
            f"Core modules ready: {', '.join(ready_modules) if ready_modules else 'None'}\n"
            f"Core modules needing input: {', '.join(warn_modules) if warn_modules else 'None'}\n\n"
            "Highlights:\n"
            "- Dashboard beta control center active (readiness + diagnostics + smoke plan + issue template).\n"
            "- QA flow supports reproducible smoke testing and structured reporting.\n"
            "- Processing catalog integrity checked against dashboard module list.\n"
        )
        QApplication.clipboard().setText(draft)

    def _copy_hub_changelog_draft(self):
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        vectors = [layer for layer in layers if hasattr(layer, "featureCount")]
        rasters = [layer for layer in layers if not hasattr(layer, "featureCount")]
        algo_total, algo_available, missing = self._algorithm_registry_status()
        module_rows = self._core_module_readiness(layers, vectors, rasters)
        ok_count = len([m for m in module_rows if m[1] == "OK"])
        warn_count = len(module_rows) - ok_count
        text = (
            f"Dashboard beta control center upgrade ({datetime.now().strftime('%Y-%m-%d')}).\n"
            "- Added registry-aware readiness snapshot (READY/NOT READY) with missing algorithm visibility.\n"
            "- Added one-click diagnostics, issue template, smoke plan and release-notes draft copy actions.\n"
            "- Added core module readiness heuristics for Heat/Flood/Social/Emergency/Synthesis.\n"
            "- Added quick-launch actions for Synthetic Dataset, Urban Heat and Network Emergency Accessibility.\n"
            f"- Runtime audit sample: {algo_available}/{algo_total} algorithms available, "
            f"{len(layers)} loaded layers ({len(vectors)} vector, {len(rasters)} raster), "
            f"core readiness {ok_count} OK / {warn_count} WARN.\n"
            f"- Missing algorithms at snapshot: {', '.join(missing) if missing else 'None'}."
        )
        QApplication.clipboard().setText(text)

    def _export_beta_html_report(self):
        project = QgsProject.instance()
        layers = list(project.mapLayers().values())
        vectors = [layer for layer in layers if hasattr(layer, "featureCount")]
        rasters = [layer for layer in layers if not hasattr(layer, "featureCount")]
        crs_values = sorted({layer.crs().authid() for layer in layers if hasattr(layer, "crs") and layer.crs().isValid()})
        html = self._build_beta_html(layers, vectors, rasters, crs_values)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Beta HTML Report",
            "planx_beta_readiness_report.html",
            "HTML Files (*.html)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            return

    @staticmethod
    def _core_module_readiness(layers, vectors, rasters):
        layer_names = [getattr(layer, "name", lambda: "")().lower() for layer in layers]
        field_names = set()
        for layer in vectors:
            try:
                for f in layer.fields():
                    field_names.add(str(f.name()).lower())
            except Exception:
                continue

        def has_name(*needles):
            blob = " ".join(layer_names)
            return any(n in blob for n in needles)

        rows = []
        heat_ok = len(vectors) >= 2 and has_name("build", "imperv", "green", "heat", "study")
        rows.append(("Heat", "OK" if heat_ok else "WARN", "layer-name heuristic"))
        flood_ok = len(rasters) >= 1 and has_name("dem", "flood", "drain", "water")
        rows.append(("Flood", "OK" if flood_ok else "WARN", "DEM + flood/water hint"))
        social_ok = has_name("social", "neigh", "census") or any(k in field_names for k in ("population", "elderly", "children", "income"))
        rows.append(("Social", "OK" if social_ok else "WARN", "social layer/field hint"))
        emergency_ok = has_name("shelter", "road", "access", "network", "evac")
        rows.append(("Emergency", "OK" if emergency_ok else "WARN", "network/shelter hint"))
        synthesis_ok = has_name("unit", "planning", "adapt", "composite") or any(k in field_names for k in ("adapt_score", "svi_score", "rr_priority_score"))
        rows.append(("Synthesis", "OK" if synthesis_ok else "WARN", "planning-unit/score hint"))
        return rows

    def _switch_page(self, idx):
        for i, page in enumerate(self.pages):
            page.setVisible(i == idx)

    def _open_algorithm(self, algorithm_id):
        if not _processing_provider_enabled():
            QMessageBox.information(
                self,
                "PlanX Urban Resilience",
                "Processing tools are hidden in QGIS 4. Use this dashboard as a panel-only overview.",
            )
            return
        processing.execAlgorithmDialog(algorithm_id)
