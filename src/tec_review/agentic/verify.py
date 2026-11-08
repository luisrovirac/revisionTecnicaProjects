"""Verificación anti-alucinación, estructural y determinista (C10).

Una afirmación está "grounded" si todas sus líneas existen en el ContextBundle y cada
identificador entre `comillas invertidas` aparece literalmente en el bundle.
"""

from __future__ import annotations

import ast
import re

from pydantic import BaseModel

from tec_review.domain.models import Claim, ContextBundle, LLMInterpretation

IDENTIFIER = re.compile(r"`([^`\n]{1,80})`")
CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


class Verification(BaseModel):
    """`reasons` bloquea la publicación; las afirmaciones sin evidencia solo se descartan."""

    claims_total: int
    claims_grounded: int
    reasons: list[str]
    fix_valid: bool

    @property
    def confirmed(self) -> bool:
        return self.claims_grounded > 0 and not self.reasons


def _missing_identifiers(text: str, corpus: str) -> list[str]:
    return [ident for ident in IDENTIFIER.findall(text) if ident.strip() not in corpus]


def claim_is_grounded(claim: Claim, bundle: ContextBundle, corpus: str) -> bool:
    lines_ok = all(n in bundle.lines for n in claim.evidence_lines)
    return lines_ok and not _missing_identifiers(claim.text, corpus)


def fix_is_valid(fix: str, path: str) -> bool:
    """Los bloques de código Python del fix deben parsear. Nunca se aplican (solo se validan)."""
    if not path.endswith(".py"):
        return bool(fix.strip())
    for block in CODE_BLOCK.findall(fix):
        try:
            ast.parse(block)
        except SyntaxError:
            return False
    return bool(fix.strip())


def verify(output: LLMInterpretation, bundle: ContextBundle) -> Verification:
    corpus = bundle.text_corpus()
    reasons = []
    if output.fingerprint != bundle.fingerprint:
        reasons.append("fingerprint distinto del hallazgo")
    grounded = sum(claim_is_grounded(c, bundle, corpus) for c in output.claims)
    if grounded == 0:
        reasons.append("ninguna afirmación con evidencia válida")
    for field in ("explanation", "impact"):
        missing = _missing_identifiers(getattr(output, field), corpus)
        if missing:
            reasons.append(f"{field}: identificadores inexistentes {missing[:3]}")
    return Verification(claims_total=len(output.claims), claims_grounded=grounded,
                        reasons=reasons, fix_valid=fix_is_valid(output.fix, bundle.path))
