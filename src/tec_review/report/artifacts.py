"""Artefactos de salida: facts.json (reproducible), triage, interpretaciones, reporte y manifiesto."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tec_review import SCHEMA_VERSION, __version__
from tec_review.agentic.prompts import PROMPT_VERSION, template_hash
from tec_review.agentic.track_b import PROMPT_VERSION as TRACK_B_PROMPT
from tec_review.report.render import render_markdown
from tec_review.report.view import build_view, quality_metrics, track_b_metrics

if TYPE_CHECKING:
    from tec_review.pipeline import RunState


def write_json(out_dir: Path, name: str, data: Any) -> Path:
    path = out_dir / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)
                    + "\n", encoding="utf-8")
    return path


def write_facts(state: RunState) -> Path:
    """Sin marcas de tiempo ni rutas absolutas: igual commit + config + versiones => mismo archivo (I5)."""
    data = {
        "schema_version": SCHEMA_VERSION,
        "ruleset": state.catalog.ruleset.name,
        "tools": {r.name: {"version": r.version, "status": r.status} for r in state.tool_runs},
        "findings": [h.model_dump(mode="json") for h in state.findings],
        "gaps": [g.model_dump(mode="json") for g in state.coverage.gaps],
        "coverage": {"applicable": state.coverage.applicable, "evaluated": state.coverage.evaluated},
        "unmapped_facts": state.unmapped_facts,
    }
    return write_json(state.out_dir, "facts.json", data)


def write_interpretations(state: RunState) -> Path:
    data = {"prompt_version": PROMPT_VERSION, "prompt_template_hash": template_hash(),
            "interpretations": [i.model_dump(mode="json") for i in state.interpretations.values()]}
    return write_json(state.out_dir, "interpretations.json", data)


def write_judgments(state: RunState) -> Path:
    data = {"prompt_version": TRACK_B_PROMPT,
            "judgments": [j.model_dump(mode="json") for j in state.judgments]}
    return write_json(state.out_dir, "judgments.json", data)


def write_report(state: RunState) -> None:
    view = build_view(state)
    write_json(state.out_dir, "report.json", view.model_dump(mode="json"))
    (state.out_dir / "report.md").write_text(render_markdown(view), encoding="utf-8")


def write_manifest(state: RunState) -> Path:
    settings = state.settings.model_dump(mode="json", exclude={"secureprojects_bin"})
    data = {
        "schema_version": SCHEMA_VERSION, "tec_review_version": __version__,
        "run_id": state.run_id, "started_at": state.started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "target": str(state.target), "settings": settings,
        "settings_fingerprint": state.settings.fingerprint(),
        "tools": [r.model_dump(mode="json") for r in state.tool_runs],
        "warnings": state.warnings, "node_timings_ms": state.node_timings_ms,
        "llm": state.llm_usage.model_dump(mode="json") | {"prompt_template_hash": template_hash()},
        "metrics": quality_metrics(state).model_dump(mode="json"),
        "track_b": track_b_metrics(state).model_dump(mode="json"),
        "suppressions": [],
    }
    return write_json(state.out_dir, "manifest.json", data)
