# -*- coding: utf-8 -*-
"""Shared base behaviour for all Urban Resilience Processing algorithms."""


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
