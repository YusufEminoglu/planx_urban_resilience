# -*- coding: utf-8 -*-
"""Shared base behaviour for all Urban Resilience Processing algorithms."""

import os

from qgis.PyQt.QtGui import QIcon

PLUGIN_DIR = os.path.dirname(os.path.dirname(__file__))

#: Canonical (display_name, group_id, color_start, color_end) per hazard
#: domain. group_id matches the pre-existing "planx_urban_resilience_<domain>"
#: strings so the toolbox tree identity does not change. display_name is now
#: the SAME across every algorithm sharing a domain (previously a few files
#: drifted, e.g. "5 - Emergency" vs "5 - Emergency: accessibility and
#: coverage", splitting one domain into two labels for the same group id).
GROUP_DEMO = ("0 - Demo and QA", "planx_urban_resilience_demo", "#64748B", "#94A3B8")
GROUP_SEISMIC = ("1 - Seismic: Debris and Logistics", "planx_urban_resilience_seismic", "#92400E", "#D97706")
GROUP_HEAT = ("2 - Heat: Comfort and Exposure", "planx_urban_resilience_heat", "#C2410C", "#F97316")
GROUP_FLOOD = ("3 - Flood & Coastal: Pluvial and SLR Susceptibility", "planx_urban_resilience_flood", "#1D4ED8", "#38BDF8")
GROUP_SOCIAL = ("4 - Social: Vulnerability and Equity", "planx_urban_resilience_social", "#6D28D9", "#A78BFA")
GROUP_EMERGENCY = ("5 - Emergency: Accessibility and Coverage", "planx_urban_resilience_emergency", "#B91C1C", "#EF4444")
GROUP_AIR = ("6 - Air: Exposure Screening", "planx_urban_resilience_air", "#0E7490", "#22D3EE")
GROUP_DROUGHT = ("7 - Drought & Wildfire: Green and WUI Stress", "planx_urban_resilience_drought", "#A16207", "#EAB308")
GROUP_SYNTHESIS = ("8 - Synthesis: Adaptation Priorities", "planx_urban_resilience_synthesis", "#0F766E", "#14B8A6")
GROUP_REPORT = ("9 - Report and QA", "planx_urban_resilience_reporting", "#334155", "#64748B")

#: Ordered for display (dock tree, docs) - matches the historic 0..9 prefix.
ALL_GROUPS = (
    GROUP_DEMO, GROUP_SEISMIC, GROUP_HEAT, GROUP_FLOOD, GROUP_SOCIAL,
    GROUP_EMERGENCY, GROUP_AIR, GROUP_DROUGHT, GROUP_SYNTHESIS, GROUP_REPORT,
)


class GroupMixin:
    """Mixin providing a shared group identity + per-tool icon.

    Usage::

        from .._mixins import GROUP_SEISMIC, GroupMixin, HelpUrlMixin

        class MyAlgo(HelpUrlMixin, GroupMixin, QgsProcessingAlgorithm):
            GROUP = GROUP_SEISMIC
            ICON = "tool_myalgo.png"
    """

    GROUP = GROUP_REPORT
    #: per-tool icon filename under icons/ (falls back to the plugin icon)
    ICON = ""

    def group(self):
        return self.GROUP[0]

    def groupId(self):
        return self.GROUP[1]

    def icon(self):
        if self.ICON:
            path = os.path.join(PLUGIN_DIR, "icons", self.ICON)
            if os.path.exists(path):
                return QIcon(path)
        path = os.path.join(PLUGIN_DIR, "icons", "plugin.svg")
        return QIcon(path) if os.path.exists(path) else super().icon()


class HelpUrlMixin:
    """Mixin that provides the standard helpUrl for every algorithm.

    Usage — change::

        class MyAlgo(QgsProcessingAlgorithm):
            ...

    to::

        from .._mixins import HelpUrlMixin

        class MyAlgo(HelpUrlMixin, QgsProcessingAlgorithm):
            ...

    The HELP_URL class attribute can be overridden per algorithm.
    """

    DOC_BASE_URL = "https://yusufeminoglu.github.io/planx_urban_resilience/URBAN_RESILIENCE_REFERENCE_MANUAL.html"

    def helpUrl(self):
        return self.DOC_BASE_URL + "#" + self.name()
