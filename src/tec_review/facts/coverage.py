"""Cobertura de tests vía sandbox (check.kind: sandbox). Opt-in con --run-tests.

Se empaquetan solo los archivos del inventario (respeta .gitignore, sin .venv ni secretos
ignorados), se ejecuta pytest con pytest-cov dentro del sandbox y se lee coverage.json.
Se marcan los módulos importantes por debajo del umbral. Si TEC_REVIEW_CRITICAL_MODULES define
globs, solo esos.
"""

from __future__ import annotations

import io
import json
import tarfile
import time
from pathlib import Path, PurePosixPath

from tec_review.domain.models import Location, RawFact, ToolRun
from tec_review.domain.ports import AnalyzerResult, SandboxError, SandboxPort
from tec_review.facts.patterns import is_test_file
from tec_review.facts.python_ast import code_lines
from tec_review.rules.capabilities import SANDBOX_TOOL
from tec_review.rules.catalog import Rule

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
COVERAGE_FILE = ".tec-review-coverage.json"  # relativa al proyecto dentro del sandbox
IMPORTANT_MIN_LINES = 30
SCRIPT = f"""set -u
python -m pip install -q pytest pytest-cov >/dev/null 2>&1
if [ -f requirements.txt ]; then python -m pip install -q -r requirements.txt >/dev/null 2>&1; fi
if [ -f pyproject.toml ] || [ -f setup.py ]; then python -m pip install -q -e . >/dev/null 2>&1; fi
python -m pytest -q --cov=. --cov-report=json:{COVERAGE_FILE} -p no:cacheprovider
"""


def build_archive(root: Path, files: list[str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for rel in files:
            tar.add(root / rel, arcname=rel, recursive=False)
    data = buffer.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise SandboxError(f"El proyecto empaquetado supera {MAX_ARCHIVE_BYTES // 2**20} MB.")
    return data


def parse_coverage(raw: bytes) -> dict[str, float]:
    """coverage.json -> {ruta relativa: % de líneas cubiertas}."""
    data = json.loads(raw)
    return {path.replace("\\", "/").removeprefix("./"): float(info["summary"]["percent_covered"])
            for path, info in data.get("files", {}).items()}


class CoverageAnalyzer:
    name = SANDBOX_TOOL

    def __init__(self, rules: list[Rule], sandbox: SandboxPort, timeout_s: float = 900.0,
                 critical_globs: list[str] | None = None) -> None:
        self.rule = next((r for r in rules if r.check.kind == "sandbox"), None)
        self.sandbox, self.timeout_s, self.critical_globs = sandbox, timeout_s, critical_globs or []

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        try:
            percents = self._measure(root, files)
        except (SandboxError, ValueError, KeyError) as exc:
            return AnalyzerResult(run=ToolRun(name=self.name, status="error", detail=str(exc)[:300]))
        facts = self._facts(root, files, percents) if self.rule else []
        return AnalyzerResult.ok(self.name, self.sandbox.name, started, facts)

    def _measure(self, root: Path, files: list[str]) -> dict[str, float]:
        run = self.sandbox.execute(build_archive(root, files), SCRIPT, [COVERAGE_FILE], self.timeout_s)
        if COVERAGE_FILE not in run.files:
            raise SandboxError(f"pytest no generó cobertura (exit {run.exit_code}): {run.stdout[-300:]}")
        return parse_coverage(run.files[COVERAGE_FILE])

    def _in_scope(self, root: Path, rel: str) -> bool:
        if not rel.endswith(".py") or is_test_file(rel) or PurePosixPath(rel).name == "__init__.py":
            return False
        if self.critical_globs:
            return any(PurePosixPath(rel).match(g) for g in self.critical_globs)
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        return len(code_lines(source)) >= IMPORTANT_MIN_LINES

    def _facts(self, root: Path, files: list[str], percents: dict[str, float]) -> list[RawFact]:
        threshold = float(self.rule.check.threshold or 80)
        facts = []
        for rel in sorted(f for f in files if self._in_scope(root, f)):
            covered = percents.get(rel, 0.0)
            if covered < threshold:
                facts.append(RawFact(
                    tool=self.name, tool_version=self.sandbox.name, tool_rule=self.rule.id,
                    location=Location(path=rel, start_line=1, end_line=1), identity=rel,
                    message=f"Cobertura de líneas {covered:.0f}% (umbral {threshold:.0f}%)."))
        return facts
