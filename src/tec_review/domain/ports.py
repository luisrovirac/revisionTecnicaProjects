"""Puertos del dominio. El núcleo depende de estas abstracciones, nunca de un proveedor."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from tec_review.domain.models import RawFact, ToolRun


class AnalyzerResult(BaseModel):
    run: ToolRun
    facts: list[RawFact] = []
    warnings: list[str] = []

    @classmethod
    def ok(cls, name: str, version: str, started: float, facts: list[RawFact],
           warnings: list[str] | None = None) -> AnalyzerResult:
        """Ejecución correcta; `started` es el `time.perf_counter()` del inicio."""
        elapsed = int((time.perf_counter() - started) * 1000)
        run = ToolRun(name=name, version=version, status="ok", duration_ms=elapsed)
        return cls(run=run, facts=facts, warnings=warnings or [])


class Analyzer(Protocol):
    name: str

    def run(self, root: Path, files: list[str]) -> AnalyzerResult: ...


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    content: str
    model_used: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_ms: float = 0.0


class LLMError(Exception):
    """Fallo del proveedor LLM. El pipeline degrada, nunca se cae (I9)."""


class LLMPort(Protocol):
    name: str

    def complete(self, messages: list[LLMMessage], max_tokens: int) -> LLMResponse: ...


class TelemetryPort(Protocol):
    def publish(self, event_type: str, **payload: object) -> None: ...


class SandboxRun(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    files: dict[str, bytes] = {}


class SandboxError(Exception):
    """El sandbox no está disponible o falló. La cobertura pasa a Gap, nada más (I9)."""


class SandboxPort(Protocol):
    """Único camino para ejecutar código del target (I2). Adaptador real: e2bcito (ADR 0004)."""

    name: str

    def execute(self, archive: bytes, script: str, fetch: list[str], timeout_s: float) -> SandboxRun:
        """Ejecuta `script` en el directorio del proyecto desempaquetado.

        Las rutas de `fetch` son relativas a ese directorio y son las claves de `SandboxRun.files`.
        """
        ...
