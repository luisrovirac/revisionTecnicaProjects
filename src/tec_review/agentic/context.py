"""ContextBundle: contexto curado por código (RAG estructurado por clave, sin embeddings).

Recuperación determinista: rule_id -> cita + safe_path; ubicación -> fragmento numerado.
El modelo nunca recibe "todo el código" ni accede al sistema de archivos.
"""

from __future__ import annotations

from pathlib import Path

from tec_review.domain.models import ContextBundle, Hallazgo
from tec_review.facts.inventory import read_lines
from tec_review.rules.catalog import Rule

MAX_SPAN_LINES = 60
REDACTED = "[contenido sensible omitido: evidencia redactada por la herramienta]"


def _snippet(root: Path, h: Hallazgo, context_lines: int) -> dict[int, str]:
    if h.sensitive:
        return {h.location.start_line or 1: h.evidence or REDACTED}
    try:
        lines = read_lines(root, h.location.path)
    except OSError:
        return {}
    start = h.location.start_line or 1
    end = min(h.location.end_line or start, start + MAX_SPAN_LINES)
    first, last = max(1, start - context_lines), min(len(lines), end + context_lines)
    return {n: lines[n - 1] for n in range(first, last + 1)}


def build_bundle(h: Hallazgo, rule: Rule, root: Path, context_lines: int) -> ContextBundle:
    source = rule.primary_source
    return ContextBundle(
        fingerprint=h.fingerprint, rule_id=rule.id, rule_title=rule.title,
        rule_quote=source.quote, rule_ref=f"{source.doc} — {source.ref}",
        safe_path=rule.safe_path, path=h.location.path, message=h.message, symbol=h.symbol,
        lines=_snippet(root, h, context_lines),
    )
