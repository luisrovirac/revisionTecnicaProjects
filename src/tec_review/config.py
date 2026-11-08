"""Configuración del operador: se carga y valida una vez al inicio (fail fast).

Nunca se lee configuración del proyecto auditado que pueda relajar criterios (I10).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
Level = Literal["quick", "standard", "deep"]
TOP_N_BY_LEVEL: dict[str, int | None] = {"quick": 10, "standard": 40, "deep": None}


class ConfigError(Exception):
    """Configuración inválida: el mensaje nombra la variable afectada."""


class Settings(BaseModel):
    catalog_dir: Path
    rules_docs_dir: Path
    ruleset: str = "universal"
    level: Level = "standard"
    use_llm: bool = True
    llm_url: str = "http://localhost:8001"
    llm_role: str = "tool_coder"  # modelo no razonador: JSON fiable (ADR 0003)
    llm_model: str | None = None
    llm_timeout_s: float = Field(default=180.0, gt=0)
    llm_max_tokens: int = Field(default=1200, gt=0)
    token_budget: int = Field(default=60_000, gt=0)
    secureprojects_bin: Path | None = None
    secureprojects_timeout_s: float = Field(default=900.0, gt=0)
    telemetry_enabled: bool = False
    telemetry_url: str = "http://localhost:8005"
    context_lines: int = Field(default=8, ge=0)
    run_tests: bool = False
    critical_modules: list[str] = []
    track_b: bool = False
    track_b_max_per_rule: int = Field(default=6, ge=1)

    @property
    def track_b_enabled(self) -> bool:
        return self.track_b or self.level == "deep"

    @property
    def top_n(self) -> int | None:
        return TOP_N_BY_LEVEL[self.level]

    def fingerprint(self) -> str:
        payload = self.model_dump_json(exclude={"secureprojects_bin", "telemetry_url"})
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(f"TEC_REVIEW_{name}")
    return value if value not in (None, "") else default


def _resolve_secureprojects() -> Path | None:
    explicit = _env("SECUREPROJECTS_BIN")
    if explicit:
        return Path(explicit)
    found = shutil.which("secureprojects")
    return Path(found) if found else None


def _from_env() -> dict[str, object]:
    """Valores leídos de TEC_REVIEW_*, con sus valores por defecto."""
    return {
        "catalog_dir": Path(_env("CATALOG_DIR", str(PROJECT_ROOT / "catalog"))),
        "rules_docs_dir": Path(_env("RULES_DIR", str(PROJECT_ROOT / "Rules"))),
        "llm_url": _env("LLM_URL", "http://localhost:8001"),
        "llm_role": _env("LLM_ROLE", "tool_coder"),
        "llm_model": _env("LLM_MODEL"),
        "llm_timeout_s": _env("LLM_TIMEOUT_S", "180"),
        "token_budget": _env("TOKEN_BUDGET", "60000"),
        "secureprojects_bin": _resolve_secureprojects(),
        "secureprojects_timeout_s": _env("SECUREPROJECTS_TIMEOUT_S", "900"),
        "telemetry_url": _env("TELEMETRY_URL", "http://localhost:8005"),
        "critical_modules": [g.strip() for g in (_env("CRITICAL_MODULES", "") or "").split(",") if g.strip()],
    }


def load_settings(**overrides: object) -> Settings:
    """Combina entorno (TEC_REVIEW_*) y opciones de CLI. Lanza ConfigError si algo no valida."""
    base = _from_env()
    base.update({k: v for k, v in overrides.items() if v is not None})
    try:
        settings = Settings.model_validate(base)
    except ValidationError as exc:
        raise ConfigError(f"Configuración inválida:\n{exc}") from exc
    if not settings.catalog_dir.is_dir():
        raise ConfigError(f"TEC_REVIEW_CATALOG_DIR no existe: {settings.catalog_dir}")
    return settings
