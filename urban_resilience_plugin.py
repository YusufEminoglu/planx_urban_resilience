# -*- coding: utf-8 -*-
import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

try:  # Qt5: QtWidgets / Qt6: QtGui
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # QGIS 4 / Qt6 without shim
    from qgis.PyQt.QtGui import QAction

from .processing.urban_resilience_provider import PlanXUrbanResilienceProvider
from .urban_resilience_dock import UrbanResilienceDock


class PlanXUrbanResiliencePlugin:
    def __init__(self, iface=None):
        self.iface = iface
        self.provider = None
        self.action = None
        self.dock = None

    def initProcessing(self):
        if self.provider is not None:
            return
        self.provider = PlanXUrbanResilienceProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        if not self.iface:
            return
        icon = self.provider.icon() if self.provider else QIcon(
            os.path.join(os.path.dirname(__file__), "icons", "plugin.svg")
        )
        self.dock = UrbanResilienceDock(self.iface)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.action = QAction(icon, "PlanX Urban Resilience", self.iface.mainWindow())
        self.action.setToolTip("Show the PlanX Urban Resilience panel")
        self.action.triggered.connect(self.show_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&PlanX Urban Resilience", self.action)

    def show_dock(self):
        self.dock.show()
        self.dock.raise_()

    def unload(self):
        if self.iface and self.action:
            self.iface.removePluginMenu("&PlanX Urban Resilience", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.iface and self.dock:
            self.iface.removeDockWidget(self.dock)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
