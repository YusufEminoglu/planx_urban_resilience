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

    HELP_URL = "https://github.com/YusufEminoglu/planx_urban_resilience"

    def helpUrl(self):
        return self.HELP_URL
