"""Reglas basadas en rutas (check.kind: path)."""

from __future__ import annotations

import time
from pathlib import PurePosixPath

from tec_review import __version__
from tec_review.domain.models import Location, RawFact
from tec_review.domain.ports import AnalyzerResult
from tec_review.rules.catalog import Rule

TOOL = "tec-review-paths"


def test_location_problem(rel: str) -> str | None:
    """Devuelve el problema de ubicación de un archivo de test Python, o None si es correcto."""
    path = PurePosixPath(rel)
    if path.suffix != ".py":
        return None
    is_prefixed = path.name.startswith("test_")
    if path.name.endswith("_test.py") and not is_prefixed:
        return f"`{path.name}` es un test sin prefijo `test_`."
    if is_prefixed and "tests" not in path.parts[:-1]:
        return f"`{path.name}` está fuera de un directorio `tests/`."
    return None


class PathRulesAnalyzer:
    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        self.rule = next((r for r in rules if r.check.metric == "test_file_location"), None)

    def run(self, root, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        facts = [] if self.rule is None else [
            RawFact(tool=TOOL, tool_version=__version__, tool_rule=self.rule.id,
                    location=Location(path=rel), message=problem, identity=rel)
            for rel in files if (problem := test_location_problem(rel))
        ]
        return AnalyzerResult.ok(TOOL, __version__, started, facts)
