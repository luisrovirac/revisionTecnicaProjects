"""Orquestador: workflow determinista con un único loop agéntico acotado (interpret).

inventory -> collect -> normalize -> triage -> interpret(+verify) -> judge (Pista B)
          -> coverage -> score -> render
Cada nodo es una función (RunState, Dependencies) -> RunState y persiste su artefacto.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tec_review.agentic.candidates import select_candidates
from tec_review.agentic.context import build_bundle
from tec_review.agentic.interpret import Budget, Interpreter, fallback
from tec_review.agentic.track_b import PROMPT_VERSION as TRACK_B_PROMPT
from tec_review.agentic.track_b import Judge, Judgment
from tec_review.config import Settings
from tec_review.domain.models import Hallazgo, Interpretacion, LLMUsage, RawFact, ToolRun
from tec_review.domain.ports import Analyzer, LLMPort, ProgressPort, TelemetryPort
from tec_review.facts.inventory import Inventory, build_inventory
from tec_review.facts.normalize import Coverage, compute_coverage, normalize
from tec_review.progress import NullProgress
from tec_review.report import artifacts
from tec_review.rules.capabilities import TRACK_B_TOOL
from tec_review.rules.catalog import Catalog
from tec_review.scoring import Scorecard, score
from tec_review.triage import select_for_interpretation


@dataclass(frozen=True)
class Dependencies:
    """Colaboradores inyectados desde la composición raíz (cli.py)."""

    analyzers: list[Analyzer]
    llm: LLMPort | None
    telemetry: TelemetryPort
    progress: ProgressPort = field(default_factory=NullProgress)


class RunState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    settings: Settings
    catalog: Catalog
    target: Path
    run_id: str
    out_dir: Path
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inventory: Inventory | None = None
    tool_runs: list[ToolRun] = []
    warnings: list[str] = []
    raw_facts: list[RawFact] = []
    findings: list[Hallazgo] = []
    unmapped_facts: int = 0
    coverage: Coverage | None = None
    selected: list[str] = []
    interpretations: dict[str, Interpretacion] = {}
    judgments: list[Judgment] = []
    llm_usage: LLMUsage = LLMUsage()
    scorecard: Scorecard | None = None
    node_timings_ms: dict[str, int] = {}


Node = Callable[[RunState, Dependencies], RunState]


def inventory_node(state: RunState, deps: Dependencies) -> RunState:
    return state.model_copy(update={"inventory": build_inventory(state.target)})


def collect_node(state: RunState, deps: Dependencies) -> RunState:
    runs, facts, warnings = [], [], list(state.warnings)
    total = len(deps.analyzers)
    for i, analyzer in enumerate(deps.analyzers, start=1):
        deps.progress.step(analyzer.name, i, total)
        result = analyzer.run(state.inventory.root, state.inventory.files)
        deps.progress.note(f"{analyzer.name}: {result.run.status}, {len(result.facts)} hechos "
                           f"({result.run.duration_ms} ms)", level="detail")
        runs.append(result.run)
        facts.extend(result.facts)
        warnings.extend(result.warnings)
        deps.telemetry.publish("analyzer_done", node=analyzer.name, status=result.run.status,
                               facts=len(result.facts))
    return state.model_copy(update={"tool_runs": runs, "raw_facts": facts, "warnings": warnings})


def normalize_node(state: RunState, deps: Dependencies) -> RunState:
    findings, unmapped = normalize(state.raw_facts, state.catalog, state.inventory.root)
    return state.model_copy(update={"findings": findings, "unmapped_facts": unmapped})


def triage_node(state: RunState, deps: Dependencies) -> RunState:
    top_n = state.settings.top_n if deps.llm else 0
    selected = [h.fingerprint for h in select_for_interpretation(state.findings, top_n)]
    updated = state.model_copy(update={"selected": selected})
    artifacts.write_json(state.out_dir, "triage.json", {"top_n": top_n, "selected": selected})
    return updated


def interpret_node(state: RunState, deps: Dependencies) -> RunState:
    if deps.llm is None or not state.selected:
        return state
    usage = state.llm_usage.model_copy(update={"adapter": deps.llm.name})
    interpreter = Interpreter(deps.llm, state.settings.llm_max_tokens, _budget(state, usage), usage)
    by_fp = {h.fingerprint: h for h in state.findings}
    results = {}
    total = len(state.selected)
    for i, fp in enumerate(state.selected, start=1):
        h = by_fp[fp]
        deps.progress.step(f"{h.rule_id} en {h.location.path}", i, total)
        results[fp] = _interpret_one(h, state, interpreter)
        deps.telemetry.publish("llm_call", node="interpret", status=results[fp].status,
                               tokens=usage.prompt_tokens + usage.completion_tokens)
    updated = state.model_copy(update={"interpretations": results, "llm_usage": usage})
    artifacts.write_interpretations(updated)
    return updated


def _interpret_one(h: Hallazgo, state: RunState, interpreter: Interpreter) -> Interpretacion:
    rule = state.catalog.get(h.rule_id)
    bundle = build_bundle(h, rule, state.inventory.root, state.settings.context_lines)
    try:
        return interpreter.interpret(h, bundle)
    except Exception as exc:  # noqa: BLE001 - red de seguridad I9: degradar, nunca abortar
        return fallback(h, bundle, "unverifiable", [f"error interno: {exc.__class__.__name__}"])


def _budget(state: RunState, usage: LLMUsage) -> Budget:
    return Budget(limit=state.settings.token_budget, used=usage.prompt_tokens + usage.completion_tokens)


def judge_node(state: RunState, deps: Dependencies) -> RunState:
    """Pista B: selectores deterministas proponen regiones; el modelo juzga con evidencia."""
    if not state.settings.track_b_enabled:
        return state
    if deps.llm is None:
        run = ToolRun(name=TRACK_B_TOOL, status="unavailable", detail="Sin LLM disponible.")
        return state.model_copy(update={"tool_runs": [*state.tool_runs, run]})
    rules = {r.id: r for r in state.catalog.by_kind("agent")}
    candidates = select_candidates(state.inventory.root, state.inventory.files, sorted(rules),
                                   state.settings.track_b_max_per_rule)
    usage = state.llm_usage.model_copy(update={"adapter": deps.llm.name})
    judge = Judge(deps.llm, state.settings.llm_max_tokens, _budget(state, usage), usage)
    pending = [(rid, c) for rid in sorted(candidates) for c in candidates[rid]]
    judgments = []
    for i, (rid, c) in enumerate(pending, start=1):
        deps.progress.step(f"{rid} en {c.path}", i, len(pending))
        judgments.append(judge.judge(state.inventory.root, c, rules[rid]))
    run = ToolRun(name=TRACK_B_TOOL, version=TRACK_B_PROMPT, status="ok",
                  detail=f"{len(judgments)} candidatos juzgados")
    updated = state.model_copy(update={"judgments": judgments, "llm_usage": usage,
                                       "tool_runs": [*state.tool_runs, run]})
    artifacts.write_judgments(updated)
    return updated


def coverage_node(state: RunState, deps: Dependencies) -> RunState:
    coverage = compute_coverage(state.catalog, state.inventory, state.tool_runs)
    updated = state.model_copy(update={"coverage": coverage})
    artifacts.write_facts(updated)
    return updated


def score_node(state: RunState, deps: Dependencies) -> RunState:
    return state.model_copy(update={"scorecard": score(state.findings, state.coverage.ratio)})


def render_node(state: RunState, deps: Dependencies) -> RunState:
    artifacts.write_report(state)
    return state


NODES: list[tuple[str, Node]] = [
    ("inventory", inventory_node), ("collect", collect_node), ("normalize", normalize_node),
    ("triage", triage_node), ("interpret", interpret_node), ("judge", judge_node),
    ("coverage", coverage_node), ("score", score_node), ("render", render_node),
]


STAGE_LABELS: dict[str, str] = {
    "inventory": "Inventariando archivos",
    "collect": "Ejecutando analizadores",
    "normalize": "Normalizando hechos contra reglas",
    "triage": "Priorizando hallazgos",
    "interpret": "Interpretando hallazgos con LLM",
    "judge": "Juicio Pista B (LLM)",
    "coverage": "Calculando cobertura de reglas",
    "score": "Calculando puntuación",
    "render": "Generando reporte",
}


def stage_summary(name: str, state: RunState, deps: Dependencies) -> str:
    """Resumen de una línea de lo que produjo un paso, para mostrarlo al usuario."""
    if name == "inventory":
        return f"{len(state.inventory.files)} archivos"
    if name == "collect":
        return f"{len(state.tool_runs)} analizadores, {len(state.raw_facts)} hechos"
    if name == "normalize":
        return f"{len(state.findings)} hallazgos"
    if name == "triage":
        return f"{len(state.selected)} seleccionados para el LLM" if deps.llm else "sin LLM"
    if name == "interpret":
        if deps.llm is None:
            return "omitido: sin LLM"
        if not state.selected:
            return "omitido: nada que interpretar"
        tokens = state.llm_usage.prompt_tokens + state.llm_usage.completion_tokens
        return f"{len(state.interpretations)} interpretados, {tokens} tokens"
    if name == "judge":
        if not state.settings.track_b_enabled:
            return "omitido: Pista B desactivada"
        if deps.llm is None:
            return "omitido: sin LLM"
        return f"{len(state.judgments)} candidatos juzgados"
    if name == "coverage":
        return f"{len(state.coverage.evaluated)}/{len(state.coverage.applicable)} reglas evaluadas"
    if name == "score":
        return f"{state.scorecard.verdict}, {state.scorecard.score}/100"
    if name == "render":
        return "report.md, report.json, facts.json"
    return ""


def run_pipeline(state: RunState, deps: Dependencies) -> RunState:
    timings: dict[str, int] = {}
    total = len(NODES)
    for index, (name, node) in enumerate(NODES, start=1):
        deps.progress.stage_start(index, total, name, STAGE_LABELS.get(name, name))
        started = time.perf_counter()
        state = node(state, deps)
        timings[name] = int((time.perf_counter() - started) * 1000)
        state = state.model_copy(update={"node_timings_ms": dict(timings)})
        deps.telemetry.publish("node_done", node=name, duration_ms=timings[name])
        deps.progress.stage_end(name, timings[name], stage_summary(name, state, deps))
    artifacts.write_manifest(state)
    return state
