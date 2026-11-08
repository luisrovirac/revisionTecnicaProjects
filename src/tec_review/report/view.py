"""Vista del reporte: une hallazgos (hechos) con interpretaciones (modelo) sin mezclarlos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from tec_review import SCHEMA_VERSION
from tec_review.domain.models import Gap, Hallazgo, Interpretacion, Severity
from tec_review.scoring import Scorecard
from tec_review.triage import rank

if TYPE_CHECKING:
    from tec_review.pipeline import RunState

DISCLAIMER = (
    "Un análisis sin hallazgos no significa que el código esté libre de errores o de "
    "vulnerabilidades. Este informe cubre las reglas y los lenguajes indicados en el anexo, "
    "con las limitaciones allí declaradas."
)
SEVERITY_ORDER = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1,
                  Severity.INFO: 0}
EFFORT = {Severity.CRITICAL: "M (½–1 día)", Severity.HIGH: "M (½–1 día)",
          Severity.MEDIUM: "S (1–3 h)", Severity.LOW: "XS (< 1 h)", Severity.INFO: "XS (< 1 h)"}


class QualityMetrics(BaseModel):
    interpreted: int = 0
    confirmed: int = 0
    unverifiable: int = 0
    skipped_budget: int = 0
    claims_total: int = 0
    claims_grounded: int = 0
    confirmed_rate: float | None = None
    hallucination_rate: float | None = None


class TrackBMetrics(BaseModel):
    enabled: bool = False
    candidates: int = 0
    published: int = 0
    dismissed: int = 0
    rejected: int = 0
    errors: int = 0
    skipped_budget: int = 0
    rejection_rate: float | None = None  # rechazados por verificación / propuestos por el modelo


class JudgmentView(BaseModel):
    rule_id: str
    title: str
    severity: Severity
    path: str
    start_line: int
    symbol: str
    explanation: str
    impact: str
    fix: str
    evidence: list[dict]
    rule_quote: str
    rule_ref: str
    safe_path: str
    model_used: str


class FindingView(BaseModel):
    finding: Hallazgo
    rule_quote: str
    rule_ref: str
    safe_path: str
    interpretation: Interpretacion | None = None


class SprintTask(BaseModel):
    rule_id: str
    title: str
    severity: Severity
    occurrences: int
    effort: str
    files: list[str]


class ReportView(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    target: str
    ruleset: str
    level: str
    llm_enabled: bool
    scorecard: Scorecard
    disclaimer: str = DISCLAIMER
    coverage_applicable: int
    coverage_evaluated: int
    detailed: list[FindingView]
    others: list[FindingView]
    sprint: list[SprintTask]
    gaps: list[Gap]
    tools: list[dict]
    warnings: list[str]
    metrics: QualityMetrics
    track_b: TrackBMetrics
    judgments: list[JudgmentView]
    rejected_judgments: list[dict]
    partial: dict[str, list[str]]
    llm: dict
    node_timings_ms: dict[str, int]


def quality_metrics(state: RunState) -> QualityMetrics:
    items = list(state.interpretations.values())
    counts = {s: sum(1 for i in items if i.status == s)
              for s in ("confirmed", "unverifiable", "skipped_budget")}
    attempted = counts["confirmed"] + counts["unverifiable"]
    total = sum(i.claims_total for i in items)
    grounded = sum(i.claims_grounded for i in items)
    return QualityMetrics(
        interpreted=len(items), confirmed=counts["confirmed"],
        unverifiable=counts["unverifiable"], skipped_budget=counts["skipped_budget"],
        claims_total=total, claims_grounded=grounded,
        confirmed_rate=round(counts["confirmed"] / attempted, 3) if attempted else None,
        hallucination_rate=round((total - grounded) / total, 3) if total else None,
    )


def track_b_metrics(state: RunState) -> TrackBMetrics:
    if not state.settings.track_b_enabled:
        return TrackBMetrics()
    counts = {s: sum(1 for j in state.judgments if j.status == s)
              for s in ("published", "dismissed", "rejected", "error", "skipped_budget")}
    proposed = counts["published"] + counts["rejected"]
    return TrackBMetrics(enabled=True, candidates=len(state.judgments), errors=counts["error"],
                         published=counts["published"], dismissed=counts["dismissed"],
                         rejected=counts["rejected"], skipped_budget=counts["skipped_budget"],
                         rejection_rate=round(counts["rejected"] / proposed, 3) if proposed else None)


def _judgment_views(state: RunState) -> list[JudgmentView]:
    views = []
    for j in (j for j in state.judgments if j.status == "published"):
        h, rule = j.finding, state.catalog.get(j.finding.rule_id)
        views.append(JudgmentView(
            rule_id=h.rule_id, title=h.title, severity=h.severity, path=h.location.path,
            start_line=h.location.start_line or 1, symbol=h.symbol or "", explanation=j.explanation,
            impact=j.impact, fix=j.fix, evidence=[e.model_dump() for e in j.evidence],
            rule_quote=rule.primary_source.quote,
            rule_ref=f"{rule.primary_source.doc} — {rule.primary_source.ref}",
            safe_path=rule.safe_path, model_used=j.model_used))
    return sorted(views, key=lambda v: (-SEVERITY_ORDER[v.severity], v.path, v.start_line))


def _finding_view(h: Hallazgo, state: RunState) -> FindingView:
    rule = state.catalog.get(h.rule_id)
    source = rule.primary_source
    return FindingView(finding=h, rule_quote=source.quote, rule_ref=f"{source.doc} — {source.ref}",
                       safe_path=rule.safe_path,
                       interpretation=state.interpretations.get(h.fingerprint))


def _sprint(ranked: list[Hallazgo]) -> list[SprintTask]:
    tasks: dict[str, SprintTask] = {}
    for h in ranked:
        task = tasks.get(h.rule_id)
        if task is None:
            tasks[h.rule_id] = SprintTask(rule_id=h.rule_id, title=h.title, severity=h.severity,
                                          occurrences=1, effort=EFFORT[h.severity],
                                          files=[h.location.path])
            continue
        task.occurrences += 1
        if h.location.path not in task.files:
            task.files.append(h.location.path)
    return list(tasks.values())


def _detailed_fingerprints(state: RunState, ranked: list[Hallazgo]) -> set[str]:
    if state.selected:
        return set(state.selected)
    top_n = state.settings.top_n or len(ranked)
    return {h.fingerprint for h in ranked[:top_n]}


def build_view(state: RunState) -> ReportView:
    ranked = rank(state.findings)
    detailed_fps = _detailed_fingerprints(state, ranked)
    views = [_finding_view(h, state) for h in ranked]
    return ReportView(
        run_id=state.run_id, target=str(state.target), ruleset=state.catalog.ruleset.name,
        level=state.settings.level, llm_enabled=state.settings.use_llm, scorecard=state.scorecard,
        coverage_applicable=len(state.coverage.applicable),
        coverage_evaluated=len(state.coverage.evaluated),
        detailed=[v for v in views if v.finding.fingerprint in detailed_fps],
        others=[v for v in views if v.finding.fingerprint not in detailed_fps],
        sprint=_sprint(ranked), gaps=state.coverage.gaps,
        tools=[r.model_dump(mode="json") for r in state.tool_runs], warnings=state.warnings,
        metrics=quality_metrics(state), track_b=track_b_metrics(state),
        judgments=_judgment_views(state),
        rejected_judgments=[{"candidate": j.candidate.candidate_id, "reasons": j.reasons}
                            for j in state.judgments if j.status == "rejected"],
        partial=state.coverage.partial, llm=state.llm_usage.model_dump(mode="json"),
        node_timings_ms=state.node_timings_ms,
    )
