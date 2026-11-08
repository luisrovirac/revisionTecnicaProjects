"""Tipos del dominio. Los hechos (Hallazgo) son inmutables; el modelo solo produce Interpretacion."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FROZEN = ConfigDict(frozen=True, extra="forbid")


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_WEIGHT: dict[Severity, int] = {
    Severity.CRITICAL: 40,
    Severity.HIGH: 15,
    Severity.MEDIUM: 5,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


class Dimension(str, Enum):
    SECURITY = "security"
    TESTING = "testing"
    DESIGN = "design"
    MAINTAINABILITY = "maintainability"
    CONFIG = "config"


DIMENSION_WEIGHT: dict[Dimension, int] = {
    Dimension.SECURITY: 30,
    Dimension.TESTING: 20,
    Dimension.DESIGN: 20,
    Dimension.MAINTAINABILITY: 20,
    Dimension.CONFIG: 10,
}

GapReason = Literal[
    "tool_unavailable", "capability_missing", "parse_error", "excluded", "track_b_disabled"
]


class Location(BaseModel):
    model_config = FROZEN
    path: str  # relativo a la raíz del target, con "/"
    start_line: int | None = None
    end_line: int | None = None


class Provenance(BaseModel):
    model_config = FROZEN
    tool: str
    tool_version: str
    original_rule: str


class RawFact(BaseModel):
    """Salida de un analizador antes de mapearla al catálogo."""

    model_config = FROZEN
    tool: str
    tool_version: str
    tool_rule: str
    location: Location
    message: str
    symbol: str | None = None
    severity_hint: Severity | None = None
    confidence: float = 1.0
    identity: str = ""  # contenido estable para el fingerprint (sin número de línea)
    evidence: str = ""  # evidencia ya redactada por la herramienta (si la aporta)
    sensitive: bool = False  # True: nunca copiar líneas de código fuente (p. ej. secretos)


class Hallazgo(BaseModel):
    """Hecho determinista. Inmutable (I4): el LLM nunca lo modifica."""

    model_config = FROZEN
    fingerprint: str
    rule_id: str
    title: str
    severity: Severity
    dimension: Dimension
    location: Location
    message: str
    symbol: str | None = None
    evidence: str = ""
    confidence: float = 1.0
    scope_factor: float = 1.0
    sensitive: bool = False
    provenance: Provenance


class Gap(BaseModel):
    model_config = FROZEN
    rule_id: str
    reason: GapReason
    detail: str = ""


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    evidence_lines: list[int] = Field(min_length=1)


class LLMInterpretation(BaseModel):
    """Esquema de salida del modelo (I3): sin archivo, línea, severidad ni regla."""

    model_config = ConfigDict(extra="forbid")
    fingerprint: str
    explanation: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    fix: str = ""
    priority: int = Field(ge=1, le=5)
    claims: list[Claim] = Field(min_length=1)


InterpretationStatus = Literal["confirmed", "unverifiable", "skipped_budget"]


class Interpretacion(BaseModel):
    model_config = FROZEN
    fingerprint: str
    status: InterpretationStatus
    explanation: str
    impact: str
    fix: str = ""
    fix_valid: bool = False
    priority: int | None = None
    claims_total: int = 0
    claims_grounded: int = 0
    rejection_reasons: tuple[str, ...] = ()
    model_used: str = ""
    prompt_hash: str = ""


class ContextBundle(BaseModel):
    """Contexto curado por código para un hallazgo. El LLM no ve nada más."""

    model_config = FROZEN
    fingerprint: str
    rule_id: str
    rule_title: str
    rule_quote: str
    rule_ref: str
    safe_path: str
    path: str
    message: str
    symbol: str | None = None
    lines: dict[int, str]

    def text_corpus(self) -> str:
        parts = [self.rule_id, self.rule_quote, self.safe_path, self.message, self.path,
                 self.symbol or ""]
        return "\n".join(parts + list(self.lines.values()))


class ToolRun(BaseModel):
    name: str
    version: str = ""
    status: Literal["ok", "unavailable", "error"]
    detail: str = ""
    duration_ms: int = 0


class LLMUsage(BaseModel):
    adapter: str = "none"
    models_used: list[str] = Field(default_factory=list)
    calls: int = 0
    failed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: float = 0.0
    prompt_template_hash: str = ""
