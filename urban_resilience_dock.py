# -*- coding: utf-8 -*-
"""PlanX Urban Resilience dock: a docked Processing launcher.

Replaces the old modal dashboard with a QGIS-native panel - a QTreeWidget
grouped by hazard domain (each domain keeps its own colour, matching
processing/_mixins.py's GROUP_* palette), one icon per tool, double-click to
run, right-click for documentation. Mirrors the sibling planx plugin's
studio_dock.py.
"""
from __future__ import annotations

import os

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QBrush, QColor, QDesktopServices, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsApplication

from .processing._mixins import ALL_GROUPS, HelpUrlMixin

PLUGIN_DIR = os.path.dirname(__file__)
PROVIDER_ID = "planx_urban_resilience"
DOC_BASE_URL = HelpUrlMixin.DOC_BASE_URL

# Every colour used below is pinned explicitly (never inherited from the
# host QPalette) - QGIS4/Qt6 hosts a dark palette by default and unpinned
# widgets render white-on-white, a bug this plugin already hit once in the
# old dashboard.py and had to fix.
_QSS = """
QWidget#urbanResilienceDockBody { background: #f4f7fb; }
QLabel#urbanResilienceHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1f2937, stop:1 #374151);
    color: white; font-weight: bold; font-size: 13px;
    padding: 10px 12px; border-radius: 6px;
}
QLabel#urbanResilienceHint { color: #64748b; font-size: 11px; }
QLineEdit#urbanResilienceSearch {
    background: #ffffff; color: #243044;
    border: 1px solid #cbd5e1; border-radius: 6px;
    padding: 5px 8px;
}
QLineEdit#urbanResilienceSearch:focus { border: 1px solid #0f766e; }
QTreeWidget {
    background: #ffffff; color: #243044;
    border: 1px solid #d8e0ea; border-radius: 6px;
    font-size: 12px; outline: 0;
}
QTreeWidget::item { padding: 3px 2px; }
QTreeWidget::item:selected { background: #e6f4f2; color: #0f766e; }
QPushButton#urbanResilienceDocBtn {
    background: #0f766e; color: white; font-weight: bold;
    border: none; border-radius: 4px; padding: 6px 12px;
}
QPushButton#urbanResilienceDocBtn:hover { background: #0d9488; }
QToolTip {
    background: #102027; color: #ffffff;
    border: 1px solid #102027; padding: 4px 6px;
}
"""


def _swatch_icon(hex_color: str, size: int = 12) -> QIcon:
    """A small solid-colour square used as the group-header icon."""
    pix = QPixmap(size, size)
    pix.fill(QColor(hex_color))
    return QIcon(pix)


class UrbanResilienceDock(QDockWidget):
    """Browses the planx_urban_resilience provider and launches algorithms."""

    def __init__(self, iface):
        super().__init__("PlanX Urban Resilience")
        self.iface = iface
        self.setObjectName("PlanXUrbanResilienceDock")

        body = QWidget()
        body.setObjectName("urbanResilienceDockBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("PlanX Urban Resilience")
        header.setObjectName("urbanResilienceHeader")
        layout.addWidget(header)

        hint = QLabel("Double-click a tool to run it. Right-click for documentation.")
        hint.setObjectName("urbanResilienceHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        doc_row = QHBoxLayout()
        doc_btn = QPushButton("\U0001F4D6 Open Reference Manual")
        doc_btn.setObjectName("urbanResilienceDocBtn")
        doc_btn.setToolTip("Open the comprehensive academic reference manual (GitHub Pages)")
        doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DOC_BASE_URL)))
        doc_row.addWidget(doc_btn)
        layout.addLayout(doc_row)

        self.search = QLineEdit()
        self.search.setObjectName("urbanResilienceSearch")
        self.search.setPlaceholderText("Search tools...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._launch)
        layout.addWidget(self.tree, 1)

        body.setStyleSheet(_QSS)
        self.setWidget(body)

        self._populate()

    # ------------------------------------------------------------------ #
    def _populate(self):
        self.tree.clear()
        provider = QgsApplication.processingRegistry().providerById(PROVIDER_ID)
        if provider is None:
            self.tree.addTopLevelItem(
                QTreeWidgetItem(["PlanX Urban Resilience provider not loaded"]))
            return
        fallback = QIcon(os.path.join(PLUGIN_DIR, "icons", "plugin.svg"))
        by_group_id = {}
        for alg in provider.algorithms():
            by_group_id.setdefault(alg.groupId(), []).append(alg)
        for display_name, group_id, color1, _color2 in ALL_GROUPS:
            algs = by_group_id.get(group_id, [])
            if not algs:
                continue
            parent = QTreeWidgetItem([display_name])
            parent.setIcon(0, _swatch_icon(color1))
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setForeground(0, QBrush(QColor(color1)))
            self.tree.addTopLevelItem(parent)
            for alg in sorted(algs, key=lambda a: a.displayName()):
                item = QTreeWidgetItem([alg.displayName()])
                try:
                    icon = alg.icon()
                except Exception:
                    icon = fallback
                item.setIcon(0, icon if not icon.isNull() else fallback)
                item.setToolTip(0, alg.shortHelpString())
                item.setData(0, Qt.ItemDataRole.UserRole, alg.id())
                parent.addChild(item)
            parent.setExpanded(True)

    # ------------------------------------------------------------------ #
    def _launch(self, item, _column):
        alg_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not alg_id:
            return
        try:
            import processing
            processing.execAlgorithmDialog(alg_id, {})
        except Exception as exc:
            self.iface.messageBar().pushWarning(
                "PlanX Urban Resilience", f"Could not open tool: {exc}")

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        alg_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not alg_id:
            return
        alg = QgsApplication.processingRegistry().algorithmById(alg_id)
        if alg is None:
            return
        menu = QMenu(self)
        help_action = menu.addAction("View Documentation")
        help_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(alg.helpUrl())))
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ #
    def _filter(self, text: str):
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                visible = not needle or needle in child.text(0).lower()
                child.setHidden(not visible)
                any_visible = any_visible or visible
            group_item.setHidden(not any_visible)
            if needle:
                group_item.setExpanded(True)
