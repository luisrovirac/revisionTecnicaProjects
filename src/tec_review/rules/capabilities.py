"""Qué puede evaluar realmente cada tipo de check, y en qué lenguajes.

"Soportado" nunca significa "bien analizado" (planInicial §6.2): si un evaluador solo cubre
Python y el proyecto también tiene Go, la regla queda evaluada *parcialmente* y el reporte lo dice.
"""

from __future__ import annotations

from tec_review.domain.models import Gap, ToolRun
from tec_review.rules.catalog import Rule

C_LIKE = frozenset({"typescript", "javascript", "java", "go", "rust", "php", "kotlin", "swift",
                    "csharp"})
PYTHON = frozenset({"python"})
ALL_LANGUAGES = None  # el evaluador es agnóstico del lenguaje

# Analizadores "virtuales" que se registran como ToolRun para decidir la cobertura.
SANDBOX_TOOL = "e2bcito"
TRACK_B_TOOL = "track-b"

AST_METRICS: dict[str, frozenset[str]] = {
    "function_logical_lines": PYTHON,
    "class_public_methods": PYTHON,
    "class_logical_lines": PYTHON,
    "non_stdlib_import_in_function": PYTHON,
    "ts_explicit_any": frozenset({"typescript"}),
}
REGEX_SETS: dict[str, frozenset[str] | None] = {
    "hardcoded_config": PYTHON | C_LIKE,
    "prompt_injection": ALL_LANGUAGES,
}
KIND_LANGUAGES: dict[str, frozenset[str]] = {
    "path": PYTHON,
    "graph": PYTHON,
    "duplication": PYTHON | C_LIKE,
}
IMPLEMENTED_TOOLS = {"ruff", "secureprojects"}


def _run_ok(runs: dict[str, ToolRun], name: str) -> bool:
    run = runs.get(name)
    return run is not None and run.status == "ok"


def _gap(rule: Rule, reason: str, detail: str) -> Gap:
    return Gap(rule_id=rule.id, reason=reason, detail=detail)


def _tool_support(rule: Rule, runs: dict[str, ToolRun]):
    tool = rule.check.tool
    if tool not in IMPLEMENTED_TOOLS:
        return None, _gap(rule, "capability_missing", f"Adaptador de {tool} no implementado.")
    if _run_ok(runs, tool):
        return ALL_LANGUAGES, None
    run = runs.get(tool)
    return None, _gap(rule, "tool_unavailable", f"{tool}: {run.detail if run else 'no ejecutado'}")


def _virtual_support(rule: Rule, runs: dict[str, ToolRun]):
    if rule.check.kind == "agent":
        if _run_ok(runs, TRACK_B_TOOL):
            return PYTHON, None
        if TRACK_B_TOOL in runs:
            return None, _gap(rule, "tool_unavailable", f"Pista B: {runs[TRACK_B_TOOL].detail}")
        return None, _gap(rule, "track_b_disabled",
                          "Regla de juicio (Pista B): se activa con --track-b o --level deep.")
    if _run_ok(runs, SANDBOX_TOOL):
        return PYTHON, None
    run = runs.get(SANDBOX_TOOL)
    detail = run.detail if run else "Requiere --run-tests (sandbox e2bcito)."
    return None, _gap(rule, "tool_unavailable" if run else "capability_missing", detail)


def support(rule: Rule, runs: dict[str, ToolRun]) -> tuple[frozenset[str] | None, Gap | None]:
    """(lenguajes soportados o None = todos, Gap si la regla no puede evaluarse)."""
    kind = rule.check.kind
    if kind == "tool_rule":
        return _tool_support(rule, runs)
    if kind in ("agent", "sandbox"):
        return _virtual_support(rule, runs)
    if kind == "ast":
        langs = AST_METRICS.get(rule.check.metric or "")
    elif kind == "regex":
        set_name = getattr(rule.check, "pattern_set", None)
        if set_name not in REGEX_SETS:
            return None, _gap(rule, "capability_missing", f"Conjunto de patrones desconocido: {set_name}")
        return REGEX_SETS[set_name], None
    else:
        langs = KIND_LANGUAGES.get(kind)
    if langs is None:
        return None, _gap(rule, "capability_missing", f"Evaluador '{kind}' no implementado.")
    return langs, None
