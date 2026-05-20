# -*- coding: utf-8 -*-
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .accessibility.emergency_accessibility import EmergencyAccessibilityAlgorithm
from .accessibility.network_accessibility import NetworkEmergencyAccessibilityAlgorithm
from .accessibility.network_criticality import NetworkCriticalityAlgorithm
from .accessibility.evacuation_simulation import EvacuationTimeSimulationAlgorithm
from .air.air_quality_exposure import AirQualityExposureAlgorithm
from .demo.synthetic_dataset import SyntheticResilienceDatasetAlgorithm
from .drought.green_infrastructure_stress import GreenInfrastructureStressAlgorithm
from .flood.pluvial_flood_susceptibility import PluvialFloodSusceptibilityAlgorithm
from .heat.urban_heat_comfort import UrbanHeatComfortRiskAlgorithm
from .reporting.apply_symbology import ApplyResilienceSymbologyAlgorithm
from .reporting.resilience_report import ResilienceReportAlgorithm
from .reporting.scenario_comparison import ScenarioComparisonAlgorithm
from .reporting.scenario_template import ScenarioTemplateAlgorithm
from .reporting.studio_brief import StudioBriefAlgorithm
from .seismic.monte_carlo_debris import UrbanResilienceSeismicAnalystV2
from .social.social_vulnerability_index import SocialVulnerabilityIndexAlgorithm
from .synthesis.adaptation_priority_synthesis import AdaptationPrioritySynthesisAlgorithm
from .synthesis.multi_hazard_composite import MultiHazardCompositeAlgorithm
from .synthesis.equity_adjusted_priority import EquityAdjustedPriorityAlgorithm
from .synthesis.climate_projection_overlay import ClimateProjectionOverlayAlgorithm
from .synthesis.recovery_capacity_index import RecoveryCapacityIndexAlgorithm
from .reporting.time_series_tracker import ResilienceTimeSeriesAlgorithm
from .reporting.pdf_atlas import ResiliencePdfAtlasAlgorithm
from .reporting.evacuation_arrival_summary import EvacuationArrivalSummaryAlgorithm
from .synthesis.scenario_sensitivity import ScenarioSensitivityAlgorithm
from .synthesis.risk_recovery_priority import RiskRecoveryPriorityAlgorithm
from .synthesis.join_scores_to_units import JoinScoresToPlanningUnitsAlgorithm
from .synthesis.hotspot_analysis import HotSpotAnalysisAlgorithm
from .synthesis.population_weighted_exposure import PopulationWeightedExposureAlgorithm
from .reporting.bivariate_symbology import BivariateSymbologyAlgorithm
from .reporting.recommended_actions import RecommendedActionsAlgorithm
from .synthesis.lisa_local_moran import LisaLocalMoranAlgorithm
from .synthesis.cost_benefit import CostBenefitAnalyzerAlgorithm
from .synthesis.critical_infrastructure_exposure import CriticalInfrastructureExposureAlgorithm
from .accessibility.seismic_cascade import SeismicCascadeAlgorithm


class PlanXUrbanResilienceProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(SyntheticResilienceDatasetAlgorithm())
        self.addAlgorithm(UrbanResilienceSeismicAnalystV2())
        self.addAlgorithm(UrbanHeatComfortRiskAlgorithm())
        self.addAlgorithm(PluvialFloodSusceptibilityAlgorithm())
        self.addAlgorithm(SocialVulnerabilityIndexAlgorithm())
        self.addAlgorithm(EmergencyAccessibilityAlgorithm())
        self.addAlgorithm(NetworkEmergencyAccessibilityAlgorithm())
        self.addAlgorithm(AirQualityExposureAlgorithm())
        self.addAlgorithm(GreenInfrastructureStressAlgorithm())
        self.addAlgorithm(AdaptationPrioritySynthesisAlgorithm())
        self.addAlgorithm(MultiHazardCompositeAlgorithm())
        self.addAlgorithm(EquityAdjustedPriorityAlgorithm())
        self.addAlgorithm(NetworkCriticalityAlgorithm())
        self.addAlgorithm(EvacuationTimeSimulationAlgorithm())
        self.addAlgorithm(ClimateProjectionOverlayAlgorithm())
        self.addAlgorithm(RecoveryCapacityIndexAlgorithm())
        self.addAlgorithm(RiskRecoveryPriorityAlgorithm())
        self.addAlgorithm(JoinScoresToPlanningUnitsAlgorithm())
        self.addAlgorithm(ResilienceTimeSeriesAlgorithm())
        self.addAlgorithm(ResiliencePdfAtlasAlgorithm())
        self.addAlgorithm(EvacuationArrivalSummaryAlgorithm())
        self.addAlgorithm(ScenarioSensitivityAlgorithm())
        self.addAlgorithm(ScenarioComparisonAlgorithm())
        self.addAlgorithm(ScenarioTemplateAlgorithm())
        self.addAlgorithm(ResilienceReportAlgorithm())
        self.addAlgorithm(StudioBriefAlgorithm())
        self.addAlgorithm(ApplyResilienceSymbologyAlgorithm())
        self.addAlgorithm(HotSpotAnalysisAlgorithm())
        self.addAlgorithm(PopulationWeightedExposureAlgorithm())
        self.addAlgorithm(BivariateSymbologyAlgorithm())
        self.addAlgorithm(RecommendedActionsAlgorithm())
        self.addAlgorithm(LisaLocalMoranAlgorithm())
        self.addAlgorithm(CostBenefitAnalyzerAlgorithm())
        self.addAlgorithm(CriticalInfrastructureExposureAlgorithm())
        self.addAlgorithm(SeismicCascadeAlgorithm())

    def id(self):
        return "planx_urban_resilience"

    def name(self):
        return "PlanX: Urban Resilience"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "plugin.svg")
        return QIcon(icon_path)
