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


def access_risk_class(minutes: float, target: float, critical: float) -> str:
    """Network / Euclidean access time classes."""
    if minutes <= target:
        return "Covered"
    if minutes <= (target + critical) * 0.5:
        return "Watch"
    if minutes <= critical:
        return "Underserved"
    return "Critical"


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
