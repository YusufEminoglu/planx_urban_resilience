# -*- coding: utf-8 -*-
import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

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
            os.path.join(os.path.dirname(__file__), "icons", "icon.png")
        )
        self.dock = UrbanResilienceDock(self.iface)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        # toggleViewAction() is the dock's own checkable show/hide action -
        # clicking it again hides the panel, and it stays in sync if the
        # user closes the dock via its own [x] button too (same behaviour
        # as every native QGIS panel toggle icon).
        self.action = self.dock.toggleViewAction()
        self.action.setIcon(icon)
        self.action.setToolTip("Show or hide the PlanX Urban Resilience panel")
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&PlanX Urban Resilience", self.action)

    def unload(self):
        if self.iface and self.action:
            self.iface.removePluginMenu("&PlanX Urban Resilience", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.iface and self.dock:
            self.iface.removeDockWidget(self.dock)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
