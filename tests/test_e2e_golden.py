"""Extremo a extremo con LLM falso: read-only, reproducible, degradable y trazable."""

import json
import shutil

import pytest

from conftest import FIXTURES, ROOT, deterministic_analyzers
from tec_review.config import load_settings
from tec_review.facts.inventory import PathGuard, PathGuardError
from tec_review.llm.fake import FakeLLM, grounded_answer
from tec_review.pipeline import Dependencies, RunState, run_pipeline
from tec_review.report.view import DISCLAIMER
from tec_review.rules.catalog import load_catalog
from tec_review.telemetry.client import NullTelemetry

SEEDED = FIXTURES / "repos" / "seeded"


def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _run(target, out_dir, llm=None, run_id="run-1", track_b=False):
    settings = load_settings(use_llm=llm is not None, ruleset="devsaxaiflow", track_b=track_b)
    catalog = load_catalog(ROOT / "catalog", settings.ruleset)
    out_dir.mkdir(parents=True)
    deps = Dependencies(analyzers=deterministic_analyzers(catalog), llm=llm, telemetry=NullTelemetry())
    state = RunState(settings=settings, catalog=catalog, target=target, run_id=run_id, out_dir=out_dir)
    return run_pipeline(state, deps)


@pytest.fixture
def seeded_copy(tmp_path):
    return shutil.copytree(SEEDED, tmp_path / "seeded")


def test_full_run_produces_all_artifacts_and_leaves_target_untouched(seeded_copy, tmp_path):
    before = _snapshot(seeded_copy)
    state = _run(seeded_copy, tmp_path / "out", llm=FakeLLM())
    assert _snapshot(seeded_copy) == before  # I1
    names = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"report.md", "report.json", "facts.json", "interpretations.json", "manifest.json",
            "triage.json"} <= names
    assert all(i.status == "confirmed" for i in state.interpretations.values())


def test_report_contains_disclaimer_rule_citation_and_safe_path(seeded_copy, tmp_path):
    _run(seeded_copy, tmp_path / "out", llm=FakeLLM())
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert DISCLAIMER in report
    assert "Si una función supera las **20 líneas**" in report
    assert "Safe path:" in report and "NO aplicado" in report
    assert "Reglas no evaluadas" in report


def test_deterministic_facts_are_byte_identical_between_runs(seeded_copy, tmp_path):
    _run(seeded_copy, tmp_path / "a", run_id="a")
    _run(seeded_copy, tmp_path / "b", run_id="b")
    assert (tmp_path / "a" / "facts.json").read_bytes() == (tmp_path / "b" / "facts.json").read_bytes()


def test_llm_failure_still_produces_deterministic_report(seeded_copy, tmp_path):
    state = _run(seeded_copy, tmp_path / "out", llm=FakeLLM(fail=True))
    assert state.scorecard is not None
    assert {i.status for i in state.interpretations.values()} == {"unverifiable"}
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm"]["failed_calls"] == manifest["llm"]["calls"] > 0


def test_manifest_records_provenance_and_quality_metrics(seeded_copy, tmp_path):
    _run(seeded_copy, tmp_path / "out", llm=FakeLLM())
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert {t["name"] for t in manifest["tools"]} >= {"ruff", "tec-review-ast"}
    assert manifest["llm"]["models_used"] == ["fake-model"]
    assert manifest["metrics"]["hallucination_rate"] == 0.0
    assert manifest["llm"]["prompt_template_hash"]


def test_without_llm_nothing_is_interpreted(seeded_copy, tmp_path):
    state = _run(seeded_copy, tmp_path / "out")
    assert state.interpretations == {}
    assert len(state.findings) == 14


def test_output_inside_target_is_rejected(seeded_copy):
    with pytest.raises(PathGuardError):
        PathGuard(seeded_copy).check_writable(seeded_copy / "out" / "run")


def _both_tracks(messages):
    """Pista A: respuesta anclada. Pista B: el modelo no ve violación."""
    user = messages[1].content
    if '"candidate_id"' in user:
        cid = user.split('"candidate_id": "', 1)[1].split('"', 1)[0]
        return json.dumps({"candidate_id": cid, "violates": False})
    return grounded_answer(messages)


def test_track_b_counts_judgment_rules_as_evaluated_without_touching_the_score(seeded_copy, tmp_path):
    plain = _run(seeded_copy, tmp_path / "a", llm=FakeLLM(_both_tracks), run_id="a")
    judged = _run(seeded_copy, tmp_path / "b", llm=FakeLLM(_both_tracks), run_id="b", track_b=True)
    assert judged.scorecard.score == plain.scorecard.score  # I5
    assert judged.scorecard.verdict == plain.scorecard.verdict
    assert "design.srp" in judged.coverage.evaluated and "design.srp" not in plain.coverage.evaluated
    assert judged.judgments and all(j.status == "dismissed" for j in judged.judgments)
    assert (tmp_path / "b" / "judgments.json").is_file()
    assert "Hallazgos de juicio (Pista B)" in (tmp_path / "b" / "report.md").read_text(encoding="utf-8")


def test_track_b_without_llm_is_declared_unavailable(seeded_copy, tmp_path):
    state = _run(seeded_copy, tmp_path / "out", track_b=True)
    [gap] = [g for g in state.coverage.gaps if g.rule_id == "design.srp"]
    assert gap.reason == "tool_unavailable" and "Sin LLM" in gap.detail
