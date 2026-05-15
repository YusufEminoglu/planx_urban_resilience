# -*- coding: utf-8 -*-
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .accessibility.emergency_accessibility import EmergencyAccessibilityAlgorithm
from .flood.pluvial_flood_susceptibility import PluvialFloodSusceptibilityAlgorithm
from .heat.urban_heat_comfort import UrbanHeatComfortRiskAlgorithm
from .seismic.monte_carlo_debris import UrbanResilienceSeismicAnalystV2
from .social.social_vulnerability_index import SocialVulnerabilityIndexAlgorithm


class PlanXUrbanResilienceProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(UrbanResilienceSeismicAnalystV2())
        self.addAlgorithm(UrbanHeatComfortRiskAlgorithm())
        self.addAlgorithm(PluvialFloodSusceptibilityAlgorithm())
        self.addAlgorithm(SocialVulnerabilityIndexAlgorithm())
        self.addAlgorithm(EmergencyAccessibilityAlgorithm())

    def id(self):
        return "planx_urban_resilience"

    def name(self):
        return "PlanX: Urban Resilience"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "plugin.svg")
        return QIcon(icon_path)
