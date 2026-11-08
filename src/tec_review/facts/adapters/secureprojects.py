"""Adaptador de SecureProjects (ADR 0002): la capa de seguridad se delega, no se reimplementa.

Se invoca el binario de SecureProjects (no código del target, I2) y su informe se escribe en un
directorio temporal fuera del target (I1). El estado de triage que traiga el informe se ignora:
una supresión definida en el repo auditado no puede ocultar un hallazgo (I10).
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tec_review.domain.models import Location, RawFact, Severity, ToolRun
from tec_review.domain.ports import AnalyzerResult
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


class SecureProjectsAnalyzer:
    name = TOOL

    def __init__(self, binary: Path | None, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.binary, self.timeout_s = binary, timeout_s

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
            result = run_tool(cmd, timeout_s=self.timeout_s)
            if result.returncode not in (0, 1):
                raise ToolExecutionError(
                    f"secureprojects terminó con código {result.returncode}: {result.stderr[:300]}"
                )
            return (Path(out_dir) / "secureprojects-report.json").read_text(encoding="utf-8")
