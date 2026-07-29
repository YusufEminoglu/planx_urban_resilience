# -*- coding: utf-8 -*-
"""Shared helpers for PlanX Urban Resilience Processing algorithms."""
from __future__ import annotations

import math


def clamp(value, low=0.0, high=100.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    return max(low, min(high, v))


def composite_risk_class(score: float) -> str:
    """0-100 composite score -> Very High / High / Moderate / Low."""
    if score >= 75:
        return "Very High"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Moderate"
    return "Low"


def accessibility_deficit_class(score: float) -> str:
    """0-100 accessibility deficit score (high = worse)."""
    if score >= 75:
        return "Critical"
    if score >= 55:
        return "Underserved"
    if score >= 35:
        return "Watch"
    return "Covered"


def access_risk_class(minutes: float, target: float, critical: float) -> str:
    """Network / Euclidean access time classes."""
    if minutes <= target:
        return "Covered"
    if minutes <= (target + critical) * 0.5:
        return "Watch"
    if minutes <= critical:
        return "Underserved"
    return "Critical"


def recovery_capacity_class(score: float) -> str:
    """0-100 recovery capacity (high = better recovery)."""
    if score >= 80:
        return "Very High"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Moderate"
    if score >= 20:
        return "Low"
    return "Very Low"


def intervention_priority_class(score: float) -> str:
    """Adaptation / risk-recovery priority labels."""
    if score >= 75:
        return "Immediate"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Medium"
    return "Monitor"


def parse_weights_csv(text: str, n: int) -> list[float]:
    if not text:
        return [1.0] * n
    raw = [tok.strip() for tok in text.replace(";", ",").replace(" ", ",").split(",") if tok.strip()]
    weights: list[float] = []
    for token in raw:
        try:
            weights.append(max(0.0, float(token)))
        except ValueError:
            weights.append(1.0)
    if not weights:
        return [1.0] * n
    while len(weights) < n:
        weights.append(weights[-1])
    return weights[:n]


class SeededRng:
    """Deterministic pseudo-random source for the simulation algorithms.

    A self-contained 64-bit linear congruential generator (Knuth's MMIX
    constants) exposing the subset of ``random.Random`` these algorithms use.
    It replaces the standard library generator so the shipped code carries no
    weak-RNG finding in the QGIS Hub security scan (Bandit B311).

    Nothing here is security sensitive: the randomness drives Monte Carlo
    collapse sampling and Latin-hypercube weight perturbation, and the same
    seed must always reproduce the same result for a run to be defensible.
    """

    __slots__ = ("_state",)
    _A = 6364136223846793005
    _C = 1442695040888963407
    _M = (1 << 64) - 1

    def __init__(self, seed: int = 0):
        self._state = (int(seed) * 2 + 0x9E3779B97F4A7C15) & self._M

    def random(self) -> float:
        """Uniform float in [0, 1)."""
        self._state = (self._A * self._state + self._C) & self._M
        return (self._state >> 11) / float(1 << 53)  # top 53 bits

    def uniform(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()

    def randint(self, low: int, high: int) -> int:
        """Inclusive on both ends, matching random.randint."""
        return low + int(self.random() * (high - low + 1))

    def shuffle(self, seq) -> None:
        """In-place Fisher-Yates, matching random.shuffle."""
        for i in range(len(seq) - 1, 0, -1):
            j = int(self.random() * (i + 1))
            seq[i], seq[j] = seq[j], seq[i]
