"""Triage determinista: decide qué hallazgos reciben juicio del modelo (planInicial §7.2).

prioridad = peso_severidad × confianza × factor_alcance × radio_impacto
En el Paso 0 el radio de impacto es 1 (el índice de llamadores llega en el Paso 2).
"""

from __future__ import annotations

from tec_review.domain.models import SEVERITY_WEIGHT, Hallazgo


def priority(h: Hallazgo, impact_radius: float = 1.0) -> float:
    return SEVERITY_WEIGHT[h.severity] * h.confidence * h.scope_factor * impact_radius


def rank(findings: list[Hallazgo]) -> list[Hallazgo]:
    """Orden total y estable: prioridad descendente, desempate por fingerprint."""
    return sorted(findings, key=lambda h: (-priority(h), h.fingerprint))


def select_for_interpretation(findings: list[Hallazgo], top_n: int | None) -> list[Hallazgo]:
    candidates = [h for h in rank(findings) if priority(h) > 0]
    return candidates if top_n is None else candidates[:top_n]
