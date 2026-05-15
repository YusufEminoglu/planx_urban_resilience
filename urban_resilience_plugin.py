# -*- coding: utf-8 -*-
from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .dashboard import UrbanResilienceDashboard
from .processing.urban_resilience_provider import PlanXUrbanResilienceProvider


class PlanXUrbanResiliencePlugin:
    def __init__(self, iface=None):
        self.iface = iface
        self.provider = None
        self.action = None
        self.dialog = None

    def initProcessing(self):
        self.provider = PlanXUrbanResilienceProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        if not self.iface:
            return
        icon = self.provider.icon()
        self.action = QAction(icon, "PlanX Urban Resilience", self.iface.mainWindow())
        self.action.setToolTip("Open the PlanX Urban Resilience dashboard")
        self.action.triggered.connect(self.open_dashboard)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&PlanX Urban Resilience", self.action)

    def open_dashboard(self):
        if self.dialog is None:
            self.dialog = UrbanResilienceDashboard(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def unload(self):
        if self.iface and self.action:
            self.iface.removePluginMenu("&PlanX Urban Resilience", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
