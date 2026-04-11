# -*- coding: utf-8 -*-
from qgis.core import QgsApplication

from .processing.urban_resilience_provider import PlanXUrbanResilienceProvider


class PlanXUrbanResiliencePlugin:
    def __init__(self):
        self.provider = None

    def initProcessing(self):
        self.provider = PlanXUrbanResilienceProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
