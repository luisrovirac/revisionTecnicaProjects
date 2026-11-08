"""CLI: comandos de introspección, revisión determinista y errores de uso (código 2)."""

import json

import pytest
from conftest import FIXTURES
from typer.testing import CliRunner

from tec_review.cli import EXIT_TOOL_ERROR, app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    """Sin SecureProjects ni servicios: la CLI debe degradar, no fallar."""
    monkeypatch.setenv("TEC_REVIEW_SECUREPROJECTS_BIN", str(tmp_path / "no-existe.exe"))
    monkeypatch.setenv("TEC_REVIEW_LLM_URL", "http://127.0.0.1:9")


def test_rules_list_shows_catalog_rules():
    result = runner.invoke(app, ["rules", "list"])
    assert result.exit_code == 0
    assert "py.func.max-lines" in result.output


def test_rules_show_prints_rule_as_json():
    result = runner.invoke(app, ["rules", "show", "py.func.max-lines"])
    assert result.exit_code == 0
    assert json.loads(result.output)["id"] == "py.func.max-lines"


def test_rules_show_unknown_rule_fails():
    result = runner.invoke(app, ["rules", "show", "no.existe"])
    assert result.exit_code == EXIT_TOOL_ERROR


def test_review_no_llm_writes_report_outside_target(tmp_path):
    out = tmp_path / "out"
    target = FIXTURES / "repos" / "seeded"
    result = runner.invoke(app, ["review", str(target), "--no-llm", "--out", str(out)])
    assert result.exit_code == 0, result.output
    [run_dir] = list(out.iterdir())
    assert {"report.md", "report.json", "facts.json", "manifest.json"} <= {
        p.name for p in run_dir.iterdir()
    }
    assert "Veredicto:" in result.output


def test_review_rejects_out_dir_inside_target(tmp_path):
    (tmp_path / "app.py").write_text("X = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["review", str(tmp_path), "--no-llm", "--out", str(tmp_path / "o")])
    assert result.exit_code == EXIT_TOOL_ERROR
    assert not (tmp_path / "o").exists()


def test_review_missing_path_fails(tmp_path):
    result = runner.invoke(app, ["review", str(tmp_path / "nada"), "--no-llm",
                                 "--out", str(tmp_path / "out")])
    assert result.exit_code == EXIT_TOOL_ERROR


def test_review_rejects_unknown_ruleset(tmp_path):
    result = runner.invoke(app, ["review", str(FIXTURES / "repos" / "clean"), "--no-llm",
                                 "--ruleset", "inventado", "--out", str(tmp_path / "out")])
    assert result.exit_code == EXIT_TOOL_ERROR
