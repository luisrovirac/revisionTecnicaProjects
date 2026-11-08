from pathlib import Path

import pytest

from tec_review.config import load_settings
from tec_review.facts.adapters.ruff import RuffAnalyzer
from tec_review.facts.duplication import DuplicationAnalyzer
from tec_review.facts.inventory import build_inventory
from tec_review.facts.normalize import normalize
from tec_review.facts.paths import PathRulesAnalyzer
from tec_review.facts.patterns import PatternAnalyzer
from tec_review.facts.python_ast import PythonAstAnalyzer
from tec_review.facts.python_graph import PythonGraphAnalyzer
from tec_review.facts.typescript_ast import TypeScriptAnalyzer
from tec_review.rules.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def catalog_dir() -> Path:
    return ROOT / "catalog"


@pytest.fixture
def rules_docs_dir() -> Path:
    return ROOT / "Rules"


def write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def deterministic_analyzers(catalog):
    rules = list(catalog.rules.values())
    return [PathRulesAnalyzer(rules), PythonAstAnalyzer(rules), TypeScriptAnalyzer(rules),
            PatternAnalyzer(rules), PythonGraphAnalyzer(rules), DuplicationAnalyzer(rules),
            RuffAnalyzer(rules)]


def findings_for(root: Path, ruleset: str = "devsaxaiflow"):
    """Capa determinista completa (sin SecureProjects) sobre un árbol de archivos."""
    catalog = load_catalog(ROOT / "catalog", ruleset)
    inventory = build_inventory(root)
    facts = []
    for analyzer in deterministic_analyzers(catalog):
        facts.extend(analyzer.run(inventory.root, inventory.files).facts)
    findings, _ = normalize(facts, catalog, inventory.root)
    return findings


@pytest.fixture
def settings(tmp_path):
    return load_settings(token_budget=10_000)
