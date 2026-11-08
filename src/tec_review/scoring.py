"""Scoring determinista (I5). El modelo redacta y ordena; nunca altera el número.

penalización_dim = Σ_regla  peso_sev × media(confianza × alcance) × log1p(n_regla)
score_dim = clamp(100 − penalización, 0, 100);  score = Σ score_dim × peso_dim / 100
Pesos provisionales: se calibran en el Paso 1 con repos de referencia (C9).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from tec_review.domain.models import (
    DIMENSION_WEIGHT,
    SEVERITY_WEIGHT,
    Dimension,
    Hallazgo,
    Severity,
)

Verdict = Literal["GO", "CONDITIONAL", "NO-GO"]
ConfidenceLevel = Literal["alta", "media", "baja"]


class DimensionScore(BaseModel):
    dimension: Dimension
    weight: int
    score: float
    findings: int


class Scorecard(BaseModel):
    score: float
    verdict: Verdict
    confidence: ConfidenceLevel
    coverage_ratio: float
    dimensions: list[DimensionScore]
    by_severity: dict[str, int]


def _penalty(findings: list[Hallazgo]) -> float:
    groups: dict[tuple[str, Severity], list[Hallazgo]] = defaultdict(list)
    for h in findings:
        groups[(h.rule_id, h.severity)].append(h)
    total = 0.0
    for (_, severity), items in groups.items():
        factor = sum(h.confidence * h.scope_factor for h in items) / len(items)
        total += SEVERITY_WEIGHT[severity] * factor * math.log1p(len(items))
    return total


def confidence_level(coverage_ratio: float) -> ConfidenceLevel:
    if coverage_ratio >= 0.7:
        return "alta"
    return "media" if coverage_ratio >= 0.4 else "baja"


def verdict_for(score: float, findings: list[Hallazgo]) -> Verdict:
    severities = {h.severity for h in findings}
    if Severity.CRITICAL in severities or score < 50:
        return "NO-GO"
    if Severity.HIGH in severities or score < 75:
        return "CONDITIONAL"
    return "GO"


def score(findings: list[Hallazgo], coverage_ratio: float) -> Scorecard:
    dims = []
    for dimension, weight in DIMENSION_WEIGHT.items():
        subset = [h for h in findings if h.dimension == dimension]
        value = max(0.0, min(100.0, 100.0 - _penalty(subset)))
        dims.append(DimensionScore(dimension=dimension, weight=weight, score=round(value, 1),
                                   findings=len(subset)))
    total = round(sum(d.score * d.weight for d in dims) / 100, 1)
    by_severity = {s.value: sum(1 for h in findings if h.severity == s) for s in Severity}
    return Scorecard(score=total, verdict=verdict_for(total, findings),
                     confidence=confidence_level(coverage_ratio),
                     coverage_ratio=round(coverage_ratio, 3), dimensions=dims,
                     by_severity=by_severity)
