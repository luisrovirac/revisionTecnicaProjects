"""Catálogo de reglas: contrato del sistema. El LLM solo puede citar reglas que existen aquí."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from tec_review.domain.models import Dimension, Severity

CheckKind = Literal["ast", "tool_rule", "path", "regex", "graph", "duplication", "sandbox", "agent"]


class Source(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    doc: str
    ref: str
    quote: str = Field(min_length=10)


class Check(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    kind: CheckKind
    tool: str | None = None
    codes: list[str] = []
    metric: str | None = None
    threshold: float | None = None


class Rule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
    title: str
    category: Dimension
    severity: Severity | Literal["inherit"]
    languages: list[str]
    scope: list[str]
    check: Check
    sources: list[Source] = Field(min_length=1)
    safe_path: str = Field(min_length=20)
    agent_required: bool
    evidence_required: list[str] = []

    @property
    def primary_source(self) -> Source:
        return self.sources[0]


class Ruleset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    documents: list[str]
    exclude_rules: list[str] = []


class Catalog:
    """Reglas activas de un ruleset, indexadas por id y por (herramienta, código)."""

    def __init__(self, ruleset: Ruleset, rules: list[Rule]) -> None:
        self.ruleset = ruleset
        self.rules: dict[str, Rule] = {r.id: r for r in rules}
        self._tool_index = {
            (r.check.tool, code): r for r in rules if r.check.kind == "tool_rule"
            for code in r.check.codes
        }

    def get(self, rule_id: str) -> Rule | None:
        return self.rules.get(rule_id)

    def for_tool_code(self, tool: str, code: str) -> Rule | None:
        return self._tool_index.get((tool, code))

    def by_kind(self, kind: CheckKind) -> list[Rule]:
        return [r for r in self.rules.values() if r.check.kind == kind]


def load_all_rules(catalog_dir: Path) -> list[Rule]:
    rules: list[Rule] = []
    for path in sorted((catalog_dir / "rules").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        rules.extend(Rule.model_validate(item) for item in data)
    ids = [r.id for r in rules]
    duplicated = {i for i in ids if ids.count(i) > 1}
    if duplicated:
        raise ValueError(f"IDs de regla duplicados en el catálogo: {sorted(duplicated)}")
    return rules


def load_catalog(catalog_dir: Path, ruleset_name: str) -> Catalog:
    ruleset_file = catalog_dir / f"ruleset.{ruleset_name}.yaml"
    if not ruleset_file.is_file():
        raise ValueError(f"Ruleset desconocido: {ruleset_name!r} (no existe {ruleset_file})")
    ruleset = Ruleset.model_validate(yaml.safe_load(ruleset_file.read_text(encoding="utf-8")))
    active = [
        r for r in load_all_rules(catalog_dir)
        if r.id not in ruleset.exclude_rules and r.primary_source.doc in ruleset.documents
    ]
    return Catalog(ruleset, active)
