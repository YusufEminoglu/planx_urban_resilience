# -*- coding: utf-8 -*-
"""Pure-logic unit tests for statistical cores used by PlanX Urban Resilience.

These tests require NO QGIS — they can be run by plain pytest:
    python -m pytest tests/test_stats_logic.py -q
"""
from __future__ import annotations

import math
import pytest


# ── BH-FDR (Benjamini-Hochberg) ────────────────────────────────────
# Direct copy of the implementation from processing/synthesis/hotspot_analysis.py
# and processing/synthesis/lisa_local_moran.py, kept here so a pure-logic
# regression is caught without needing QGIS.


def _bh_fdr(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values; NaN entries stay NaN."""
    indexed = [(p, i) for i, p in enumerate(pvalues) if not math.isnan(p)]
    adjusted = [float("nan")] * len(pvalues)
    m = len(indexed)
    if m == 0:
        return adjusted
    indexed.sort()
    running_min = 1.0
    for rank in range(m, 0, -1):
        p, orig_idx = indexed[rank - 1]
        running_min = min(running_min, p * m / rank)
        adjusted[orig_idx] = min(running_min, 1.0)
    return adjusted


class TestBHFDR:
    def test_textbook_case(self):
        """BH on textbook p-values: 0.001, 0.01, 0.05, 0.1, 0.5."""
        pvals = [0.001, 0.01, 0.05, 0.1, 0.5]
        adj = _bh_fdr(pvals)
        # With m=5: rank 5: 0.5*5/5=0.5 → min=0.5
        #             rank 4: 0.1*5/4=0.125 → min=0.125
        #             rank 3: 0.05*5/3=0.0833 → min=0.0833
        #             rank 2: 0.01*5/2=0.025 → min=0.025
        #             rank 1: 0.001*5/1=0.005 → min=0.005
        expected = [0.005, 0.025, 0.08333333, 0.125, 0.5]
        for a, e in zip(adj, expected):
            assert math.isclose(a, e, rel_tol=1e-6), f"{a} != {e}"

    def test_nan_passthrough(self):
        """NaN values stay NaN in output."""
        pvals = [0.01, float("nan"), 0.05, float("nan")]
        adj = _bh_fdr(pvals)
        assert math.isnan(adj[1])
        assert math.isnan(adj[3])
        assert not math.isnan(adj[0])
        assert not math.isnan(adj[2])

    def test_all_nan(self):
        """All NaN input → all NaN output."""
        pvals = [float("nan"), float("nan")]
        adj = _bh_fdr(pvals)
        assert all(math.isnan(a) for a in adj)

    def test_empty(self):
        """Empty input → empty output."""
        assert _bh_fdr([]) == []

    def test_single_value(self):
        """Single p-value should adjust to itself (capped at 1.0)."""
        adj = _bh_fdr([0.03])
        assert math.isclose(adj[0], 0.03, rel_tol=1e-9)

    def test_all_significant(self):
        """When all p-values are very small, adjusted values stay small."""
        pvals = [1e-6, 1e-5, 1e-4, 1e-3]
        adj = _bh_fdr(pvals)
        for a in adj:
            assert a <= 0.004  # 1e-3 * 4/1 = 0.004 is the worst case

    def test_all_ones(self):
        """All p-values = 1.0 should adjust to 1.0."""
        pvals = [1.0, 1.0, 1.0, 1.0, 1.0]
        adj = _bh_fdr(pvals)
        for a in adj:
            assert math.isclose(a, 1.0, rel_tol=1e-9)

    def test_descending_input(self):
        """BH still correct when p-values are given in descending order."""
        pvals = [0.5, 0.1, 0.05, 0.01, 0.001]
        adj = _bh_fdr(pvals)
        expected = [0.5, 0.125, 0.08333333, 0.025, 0.005]
        for a, e in zip(adj, expected):
            assert math.isclose(a, e, rel_tol=1e-6)


# ── LISA / Local Moran's I helper functions ─────────────────────────


def _norm_cdf(z: float) -> float:
    """Standard normal CDF using erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _two_sided_p(z: float) -> float:
    return 2.0 * (1.0 - _norm_cdf(abs(z)))


class TestLISAHelpers:
    def test_norm_cdf_known_values(self):
        """Norm CDF vs standard table values."""
        assert math.isclose(_norm_cdf(0.0), 0.5, rel_tol=1e-9)
        assert math.isclose(_norm_cdf(1.0), 0.841344746, rel_tol=1e-6)
        assert math.isclose(_norm_cdf(1.96), 0.975002, rel_tol=1e-5)
        assert math.isclose(_norm_cdf(-1.0), 0.158655254, rel_tol=1e-6)
        assert _norm_cdf(10.0) > 0.9999
        assert _norm_cdf(-10.0) < 0.0001

    def test_two_sided_p_known_values(self):
        """Two-sided p from z, known textbook values."""
        # z=0 → p≈1.0
        assert math.isclose(_two_sided_p(0.0), 1.0, rel_tol=1e-9)
        # z=1.96 → p≈0.05 (the 95% critical value)
        assert math.isclose(_two_sided_p(1.96), 0.05, rel_tol=1e-2)
        # z=2.576 → p≈0.01 (the 99% critical value)
        assert math.isclose(_two_sided_p(2.576), 0.01, rel_tol=1e-2)
        # z negative → same p as positive
        assert math.isclose(_two_sided_p(-1.96), _two_sided_p(1.96), rel_tol=1e-9)


# ── Scoring helpers from synthesis algorithms ──────────────────────


def _minmax_score(values: list[float], invert: bool = False) -> list[float]:
    """Min-max normalise a list of values to 0-100."""
    lo, hi = min(values), max(values)
    if math.isclose(hi, lo):
        return [50.0] * len(values)
    rng = hi - lo
    scaled = [(v - lo) / rng * 100.0 for v in values]
    if invert:
        scaled = [100.0 - s for s in scaled]
    return scaled


class TestMinMaxScore:
    def test_basic_normalisation(self):
        vals = [10.0, 20.0, 30.0, 40.0]
        scores = _minmax_score(vals)
        assert math.isclose(scores[0], 0.0, rel_tol=1e-9)
        assert math.isclose(scores[-1], 100.0, rel_tol=1e-9)
        assert math.isclose(scores[1], 100.0 / 3, rel_tol=1e-6)

    def test_all_same(self):
        """All values equal → return 50.0 for every entry."""
        vals = [5.0, 5.0, 5.0]
        scores = _minmax_score(vals)
        for s in scores:
            assert math.isclose(s, 50.0, rel_tol=1e-9)

    def test_invert(self):
        """Inverted: low input → high score."""
        vals = [10.0, 20.0, 30.0]
        scores = _minmax_score(vals, invert=True)
        assert math.isclose(scores[0], 100.0, rel_tol=1e-9)
        assert math.isclose(scores[-1], 0.0, rel_tol=1e-9)

    def test_single_value(self):
        scores = _minmax_score([42.0])
        assert math.isclose(scores[0], 50.0, rel_tol=1e-9)

    def test_negative_values(self):
        vals = [-10.0, 0.0, 10.0]
        scores = _minmax_score(vals)
        assert math.isclose(scores[0], 0.0, rel_tol=1e-9)
        assert math.isclose(scores[1], 50.0, rel_tol=1e-9)
        assert math.isclose(scores[2], 100.0, rel_tol=1e-9)


# ── WCAG contrast ratio (also used by the GUI harness) ─────────────


def srgb_to_linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(r: float, g: float, b: float) -> float:
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)


def contrast_ratio(l1: float, l2: float) -> float:
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class TestContrast:
    def test_black_on_white(self):
        """#000 on #FFF → ratio ~21:1."""
        lum_black = relative_luminance(0.0, 0.0, 0.0)
        lum_white = relative_luminance(1.0, 1.0, 1.0)
        cr = contrast_ratio(lum_black, lum_white)
        assert math.isclose(cr, 21.0, rel_tol=0.01)

    def test_white_on_white(self):
        """#FFF on #FFF → ratio = 1.0."""
        lum = relative_luminance(1.0, 1.0, 1.0)
        cr = contrast_ratio(lum, lum)
        assert math.isclose(cr, 1.0, rel_tol=1e-9)

    def test_dark_text_on_white_card(self):
        """#243044 on #FFFFFF → ratio ~7.8:1 (our dashboard QLabel)."""
        lum_text = relative_luminance(0x24 / 255, 0x30 / 255, 0x44 / 255)
        lum_card = relative_luminance(1.0, 1.0, 1.0)
        cr = contrast_ratio(lum_text, lum_card)
        assert cr > 7.0  # well above WCAG AA (4.5)

    def test_teal_button_white_text(self):
        """#FFFFFF on #0F766E → ratio ~5.4:1 (our primary button)."""
        lum_text = relative_luminance(1.0, 1.0, 1.0)
        lum_teal = relative_luminance(0x0F / 255, 0x76 / 255, 0x6E / 255)
        cr = contrast_ratio(lum_text, lum_teal)
        assert cr > 4.5  # meets WCAG AA
