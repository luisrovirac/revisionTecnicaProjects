"""Adaptador de SecureProjects (ADR 0002): la capa de seguridad se delega, no se reimplementa.

Se invoca el binario de SecureProjects (no código del target, I2) y su informe se escribe en un
directorio temporal fuera del target (I1). El estado de triage que traiga el informe se ignora:
una supresión definida en el repo auditado no puede ocultar un hallazgo (I10).
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tec_review.domain.models import Location, RawFact, Severity, ToolRun
from tec_review.domain.ports import AnalyzerResult, ProgressPort
from tec_review.facts.adapters.process import ToolExecutionError, run_tool

TOOL = "secureprojects"
DEFAULT_TIMEOUT_S = 900.0
SUPPORTED_SCHEMA_MAJOR = "1"
CONFIDENCE = {"high": 1.0, "medium": 0.7, "low": 0.4}
SEVERITY = {s.value: s for s in Severity} | {"unknown": Severity.MEDIUM}


class _SpLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str | None = None
    startLine: int | None = None
    endLine: int | None = None


class _SpFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fingerprint: str
    title: str
    category: str
    severity: str
    confidence: str = "medium"
    ruleId: str = ""
    location: _SpLocation | None = None
    evidence: str = ""
    remediation: str = ""


class _SpTool(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: str = ""


class _SpReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schemaVersion: str
    tool: _SpTool
    findings: list[_SpFinding] = []


class SecureProjectsSchemaError(ValueError):
    """El informe no tiene una versión de esquema soportada."""


def _to_fact(finding: _SpFinding, version: str) -> RawFact | None:
    loc = finding.location
    if loc is None or not loc.path:  # p. ej. DAST: sin ubicación en el código
        return None
    message = finding.title + (f" — {finding.remediation}" if finding.remediation else "")
    return RawFact(
        tool=TOOL, tool_version=version, tool_rule=finding.category,
        location=Location(path=loc.path.replace("\\", "/"), start_line=loc.startLine,
                          end_line=loc.endLine),
        message=message, severity_hint=SEVERITY.get(finding.severity.lower(), Severity.MEDIUM),
        confidence=CONFIDENCE.get(finding.confidence.lower(), 0.7),
        identity=finding.fingerprint, evidence=finding.evidence,
        sensitive=finding.category == "secret",
    )


def parse_report(raw: str) -> tuple[str, list[RawFact], int]:
    """Devuelve (versión de la herramienta, hechos, nº de hallazgos sin ubicación descartados)."""
    report = _SpReport.model_validate(json.loads(raw))
    if report.schemaVersion.split(".")[0] != SUPPORTED_SCHEMA_MAJOR:
        raise SecureProjectsSchemaError(f"schemaVersion no soportada: {report.schemaVersion}")
    converted = [_to_fact(f, report.tool.version) for f in report.findings]
    facts = [f for f in converted if f is not None]
    return report.tool.version, facts, len(converted) - len(facts)


_STEP = re.compile(r"^\[(?P<clock>\d+:\d+(?::\d+)?)\]\s+(?P<msg>.*)$")
_PLAN = re.compile(r"Ejecutando (?P<n>\d+) de \d+ analizadores: (?P<names>.+)$")
_START = re.compile(r"^->\s*(?P<name>[\w.-]+): iniciando")
_DONE = re.compile(r"^\[(?P<k>\d+)/(?P<n>\d+)\]\s*(?P<name>[\w.-]+):")


class ScanProgress:
    """Traduce el log de SecureProjects (stderr) a progreso legible en tec-review.

    SecureProjects anuncia sus fases y sus herramientas internas ("-> trivy: iniciando",
    "[4/6] semgrep: ok, ..."). Se reenvía cada línea y se mantiene qué sigue en curso.
    """

    def __init__(self, progress: ProgressPort) -> None:
        self.progress = progress
        self.running: list[str] = []
        self.done = 0
        self.total: int | None = None

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line or line.startswith("report written"):
            return
        if line.startswith("{"):
            self._json_log(line)
            return
        match = _STEP.match(line)
        msg = match["msg"].strip() if match else line
        clock = f"[{match['clock']}] " if match else ""
        self._track(msg)
        self.progress.note(f"secureprojects {clock}{msg}", level="detail")
        self.progress.activity(self.describe(msg), self.done if self.total else None, self.total)

    def describe(self, last: str) -> str:
        if self.running:
            return f"en curso: {', '.join(self.running)}"
        return last

    def _track(self, msg: str) -> None:
        if plan := _PLAN.search(msg):
            self.total = int(plan["n"])
        elif start := _START.match(msg):
            if start["name"] not in self.running:
                self.running.append(start["name"])
        elif done := _DONE.match(msg):
            self.done, self.total = int(done["k"]), int(done["n"])
            if done["name"] in self.running:
                self.running.remove(done["name"])

    def _json_log(self, line: str) -> None:
        try:
            entry = json.loads(line)
        except ValueError:
            return
        scanner = f"{entry['scanner']}: " if entry.get("scanner") else ""
        level = "warn" if str(entry.get("level", "")).upper() in {"WARN", "ERROR"} else "detail"
        self.progress.note(f"secureprojects {scanner}{entry.get('msg', '')}", level=level)


class SecureProjectsAnalyzer:
    name = TOOL

    def __init__(self, binary: Path | None, timeout_s: float = DEFAULT_TIMEOUT_S,
                 progress: ProgressPort | None = None) -> None:
        self.binary, self.timeout_s, self.progress = binary, timeout_s, progress

    def available(self) -> bool:
        return self.binary is not None and self.binary.is_file()

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        if not self.available():
            detail = "Binario no encontrado. Define TEC_REVIEW_SECUREPROJECTS_BIN."
            return AnalyzerResult(run=ToolRun(name=TOOL, status="unavailable", detail=detail))
        started = time.perf_counter()
        try:
            version, facts, dropped = parse_report(self._scan(root))
        except (ToolExecutionError, SecureProjectsSchemaError, ValueError) as exc:
            return AnalyzerResult(run=ToolRun(name=TOOL, status="error", detail=str(exc)[:500]))
        known = set(files)
        facts = [f for f in facts if f.location.path in known or f.tool_rule == "dependency-vuln"]
        warnings = [f"{dropped} hallazgos de SecureProjects sin ubicación en código"] if dropped else []
        return AnalyzerResult.ok(TOOL, version, started, facts, warnings)

    def _scan(self, root: Path) -> str:
        with tempfile.TemporaryDirectory(prefix="tec-review-sp-") as out_dir:
            cmd = [str(self.binary), "scan", str(root), "-f", "json", "-o", out_dir,
                   "--offline", "--safe", "--fail-on", "none"]
            on_line = ScanProgress(self.progress).feed if self.progress is not None else None
            result = run_tool(cmd, timeout_s=self.timeout_s, on_stderr_line=on_line)
            if result.returncode not in (0, 1):
                raise ToolExecutionError(
                    f"secureprojects terminó con código {result.returncode}: {result.stderr[:300]}"
                )
            return (Path(out_dir) / "secureprojects-report.json").read_text(encoding="utf-8")
