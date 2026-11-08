"""Adaptador de ruff (versión fijada en pyproject).

`--isolated` ignora la configuración del proyecto auditado (I10: el target no puede desactivar
reglas) y `--no-cache` evita escribir `.ruff_cache` dentro del target (I1).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tec_review.domain.models import Location, RawFact, ToolRun
from tec_review.domain.ports import AnalyzerResult
from tec_review.facts.adapters.process import ToolExecutionError, run_tool
from tec_review.rules.catalog import Rule

TOOL = "ruff"
TIMEOUT_S = 300.0


class _RuffPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")
    row: int
    column: int


class _RuffItem(BaseModel):
    """Parse, don't validate: el JSON de ruff se convierte en un tipo antes de usarse."""

    model_config = ConfigDict(extra="ignore")
    code: str | None
    filename: str
    message: str
    location: _RuffPosition
    end_location: _RuffPosition


def parse_ruff_output(raw: str, root: Path, version: str, known: set[str]) -> list[RawFact]:
    items = [_RuffItem.model_validate(i) for i in json.loads(raw or "[]")]
    facts = []
    for item in items:
        rel = Path(item.filename).resolve().relative_to(root.resolve()).as_posix()
        if item.code is None or rel not in known:
            continue
        location = Location(path=rel, start_line=item.location.row, end_line=item.end_location.row)
        facts.append(RawFact(tool=TOOL, tool_version=version, tool_rule=item.code,
                             location=location, message=item.message, identity=item.code))
    return facts


class RuffAnalyzer:
    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        self.codes = sorted({c for r in rules if r.check.tool == TOOL for c in r.check.codes})
        self._base = [sys.executable, "-m", "ruff"]

    def version(self) -> str:
        result = run_tool([*self._base, "--version"], timeout_s=30)
        return result.stdout.strip().removeprefix("ruff ").strip()

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        try:
            version = self.version()
            raw = self._check(root)
        except ToolExecutionError as exc:
            return AnalyzerResult(run=ToolRun(name=TOOL, status="error", detail=str(exc)))
        facts = parse_ruff_output(raw, root, version, set(files))
        return AnalyzerResult.ok(TOOL, version, started, facts)

    def _check(self, root: Path) -> str:
        cmd = [*self._base, "check", "--isolated", "--no-cache", "--exit-zero",
               "--output-format", "json", "--select", ",".join(self.codes), str(root)]
        result = run_tool(cmd, timeout_s=TIMEOUT_S)
        if result.returncode != 0:
            raise ToolExecutionError(f"ruff terminó con código {result.returncode}: {result.stderr[:300]}")
        return result.stdout
