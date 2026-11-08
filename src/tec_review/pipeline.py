"""Orquestador: workflow determinista con un único loop agéntico acotado (interpret).

inventory -> collect -> normalize -> triage -> interpret(+verify) -> judge (Pista B)
          -> coverage -> score -> render
Cada nodo es una función (RunState, Dependencies) -> RunState y persiste su artefacto.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tec_review.agentic.context import build_bundle
from tec_review.agentic.candidates import select_candidates
from tec_review.agentic.interpret import Budget, Interpreter, fallback
from tec_review.agentic.track_b import PROMPT_VERSION as TRACK_B_PROMPT
from tec_review.agentic.track_b import Judge, Judgment
from tec_review.config import Settings
from tec_review.domain.models import Hallazgo, Interpretacion, LLMUsage, RawFact, ToolRun
from tec_review.domain.ports import Analyzer, LLMPort, TelemetryPort
from tec_review.facts.inventory import Inventory, build_inventory
from tec_review.facts.normalize import Coverage, compute_coverage, normalize
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


class RunState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    settings: Settings
    catalog: Catalog
    target: Path
    run_id: str
    out_dir: Path
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    for analyzer in deps.analyzers:
        result = analyzer.run(state.inventory.root, state.inventory.files)
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
    for fp in state.selected:
        results[fp] = _interpret_one(by_fp[fp], state, interpreter)
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
    judgments = [judge.judge(state.inventory.root, c, rules[rid])
                 for rid in sorted(candidates) for c in candidates[rid]]
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


def run_pipeline(state: RunState, deps: Dependencies) -> RunState:
    timings: dict[str, int] = {}
    for name, node in NODES:
        started = time.perf_counter()
        state = node(state, deps)
        timings[name] = int((time.perf_counter() - started) * 1000)
        state = state.model_copy(update={"node_timings_ms": dict(timings)})
        deps.telemetry.publish("node_done", node=name, duration_ms=timings[name])
    artifacts.write_manifest(state)
    return state
