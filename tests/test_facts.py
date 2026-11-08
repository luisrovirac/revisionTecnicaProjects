"""Capa determinista: inventario, guarda de rutas, AST, adaptadores y normalización."""

import json

import pytest

from conftest import FIXTURES, findings_for, write_tree
from tec_review.domain.models import Severity
from tec_review.facts.adapters.ruff import parse_ruff_output
from tec_review.facts.adapters.secureprojects import (
    SecureProjectsAnalyzer,
    SecureProjectsSchemaError,
    parse_report,
)
from tec_review.facts.inventory import PathGuard, PathGuardError, build_inventory
from tec_review.facts.python_ast import code_lines

SP_REPORT = (FIXTURES / "secureprojects" / "report.json").read_text(encoding="utf-8")


def test_inventory_respects_gitignore_excluded_dirs_and_binaries(tmp_path):
    write_tree(tmp_path, {".gitignore": "secreto/\n*.log\n", "a.py": "x = 1\n",
                          "secreto/b.py": "y = 2\n", "app.log": "z\n",
                          "node_modules/c.js": "1\n", ".github/w.yml": "on: push\n"})
    (tmp_path / "img.bin").write_bytes(b"\x00\x01\x02")
    inventory = build_inventory(tmp_path)
    assert inventory.files == [".github/w.yml", ".gitignore", "a.py"]
    assert inventory.languages == {"python": 1}
    assert inventory.skipped_binary == 1


def test_path_guard_blocks_writes_inside_target_and_allows_outside(tmp_path):
    target = tmp_path / "proyecto"
    target.mkdir()
    guard = PathGuard(target)
    with pytest.raises(PathGuardError):
        guard.check_writable(target / "out")
    with pytest.raises(PathGuardError):
        guard.check_writable(target)
    assert guard.check_writable(tmp_path / "fuera") == (tmp_path / "fuera").resolve()


def test_code_lines_excludes_comments_and_blanks():
    source = "def f():\n    # comentario\n\n    return (1 +\n            2)\n"
    assert code_lines(source) == {1, 4, 5}


def test_seeded_repo_findings_are_located_exactly():
    found = {(h.rule_id, h.location.path, h.location.start_line)
             for h in findings_for(FIXTURES / "repos" / "seeded")}
    assert found == {
        ("py.func.max-lines", "src/app/service.py", 4),
        ("py.import-in-method", "src/app/service.py", 30),
        ("any.class.max-public-methods", "src/app/service.py", 35),
        ("any.bare-except", "src/app/main.py", 7),
        ("any.bare-except", "src/app/main.py", 17),
        ("py.no-print", "src/app/main.py", 9),
        ("any.tests.location", "src/app/test_helpers.py", None),
        ("any.tests.location", "tests/util_test.py", None),
        ("any.tests.missing", "src/app/service.py", 1),
        ("llm.prompt-injection", "src/app/clients.py", 7),
        ("any.hardcoded-config", "src/app/clients.py", 5),
        ("any.import.cycle", "src/app/billing.py", 1),
        ("any.duplication.ratio", "src/app/billing.py", 8),
        ("ts.no-any", "web/api.ts", 5),
    }


def test_clean_repo_has_zero_findings_restraint():
    assert findings_for(FIXTURES / "repos" / "clean") == []


def test_fingerprints_are_stable_and_ignore_line_numbers(tmp_path):
    code = "def f():\n    print('x')\n"
    first = findings_for(write_tree(tmp_path / "a", {"m.py": code}))
    moved = findings_for(write_tree(tmp_path / "b", {"m.py": "\n\n\n" + code}))
    assert [h.fingerprint for h in first] == [h.fingerprint for h in moved]


def test_ruff_parser_ignores_files_outside_inventory(tmp_path):
    raw = json.dumps([{"code": "T201", "filename": str(tmp_path / "m.py"), "message": "print",
                       "location": {"row": 2, "column": 5}, "end_location": {"row": 2, "column": 9}},
                      {"code": "T201", "filename": str(tmp_path / "ajeno.py"), "message": "print",
                       "location": {"row": 1, "column": 1}, "end_location": {"row": 1, "column": 2}}])
    facts = parse_ruff_output(raw, tmp_path, "0.17.4", {"m.py"})
    assert [(f.location.path, f.location.start_line) for f in facts] == [("m.py", 2)]


def test_secureprojects_report_parsing_keeps_target_triaged_findings():
    version, facts, dropped = parse_report(SP_REPORT)
    by_identity = {f.identity: f for f in facts}
    assert version == "1.2.3"
    assert dropped == 1  # el hallazgo DAST no tiene ubicación en código
    assert set(by_identity) == {"aaa", "bbb", "ccc"}  # "ccc" estaba 'accepted' en el repo: I10
    assert by_identity["bbb"].sensitive is True
    assert by_identity["aaa"].severity_hint == Severity.HIGH


def test_secureprojects_rejects_unknown_schema_major():
    with pytest.raises(SecureProjectsSchemaError):
        parse_report(SP_REPORT.replace('"schemaVersion": "1.0.0"', '"schemaVersion": "2.0.0"'))


def test_secureprojects_missing_binary_is_reported_not_raised(tmp_path):
    result = SecureProjectsAnalyzer(None).run(tmp_path, [])
    assert result.run.status == "unavailable"
    assert result.facts == []


def test_strongly_connected_finds_only_multi_node_cycles():
    from tec_review.facts.python_graph import strongly_connected

    edges = {"a": ["b"], "b": ["c", "a"], "c": ["c"], "d": ["e"], "e": ["f"], "f": ["d"], "g": []}
    assert strongly_connected(sorted("gfedcba"), edges) == [["a", "b"], ["d", "e", "f"]]
