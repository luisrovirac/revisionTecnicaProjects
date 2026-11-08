"""Hechos crudos -> Hallazgo tipado vía catálogo, y cálculo de gaps/cobertura."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from tec_review.domain.models import Gap, Hallazgo, Provenance, RawFact, Severity, ToolRun
from tec_review.facts.inventory import Inventory, read_lines
from tec_review.rules.capabilities import support
from tec_review.rules.catalog import Catalog, Rule

INTERNAL_TOOLS = {"tec-review-ast", "tec-review-paths", "tec-review-ts", "tec-review-regex",
                  "tec-review-graph", "tec-review-dup", "e2bcito", "track-b"}
LOW_IMPACT_DIRS = {"tests", "test", "docs", "examples", "fixtures"}
LOW_IMPACT_FACTOR = 0.3


class Coverage(BaseModel):
    applicable: list[str]
    evaluated: list[str]
    gaps: list[Gap]
    partial: dict[str, list[str]] = {}  # regla evaluada -> lenguajes presentes sin evaluador

    @property
    def ratio(self) -> float:
        return len(self.evaluated) / len(self.applicable) if self.applicable else 0.0


def _rule_for(fact: RawFact, catalog: Catalog) -> Rule | None:
    if fact.tool in INTERNAL_TOOLS:
        return catalog.get(fact.tool_rule)
    return catalog.for_tool_code(fact.tool, fact.tool_rule)


def _scope_factor(path: str) -> float:
    parts = set(PurePosixPath(path).parts[:-1])
    return LOW_IMPACT_FACTOR if parts & LOW_IMPACT_DIRS else 1.0


class _SourceCache:
    def __init__(self, root: Path) -> None:
        self.root, self._cache = root, {}

    def line(self, rel: str, number: int | None) -> str:
        if number is None:
            return ""
        if rel not in self._cache:
            try:
                self._cache[rel] = read_lines(self.root, rel)
            except OSError:
                self._cache[rel] = []
        lines = self._cache[rel]
        return lines[number - 1].strip()[:200] if 0 < number <= len(lines) else ""


def _fingerprint(rule_id: str, fact: RawFact, evidence: str, seen: dict[str, int]) -> str:
    content = evidence if fact.tool not in INTERNAL_TOOLS and not fact.sensitive else ""
    key = "|".join([rule_id, fact.location.path, fact.symbol or "", fact.identity, content])
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    seen[digest] = seen.get(digest, 0) + 1
    return digest if seen[digest] == 1 else f"{digest}-{seen[digest]}"


def to_hallazgo(fact: RawFact, rule: Rule, evidence: str, fingerprint: str) -> Hallazgo:
    severity = rule.severity if rule.severity != "inherit" else (fact.severity_hint or Severity.MEDIUM)
    return Hallazgo(
        fingerprint=fingerprint, rule_id=rule.id, title=rule.title, severity=severity,
        dimension=rule.category, location=fact.location, message=fact.message,
        symbol=fact.symbol, evidence=evidence, confidence=fact.confidence,
        scope_factor=_scope_factor(fact.location.path), sensitive=fact.sensitive,
        provenance=Provenance(tool=fact.tool, tool_version=fact.tool_version,
                              original_rule=fact.tool_rule),
    )


def normalize(facts: list[RawFact], catalog: Catalog, root: Path) -> tuple[list[Hallazgo], int]:
    """Devuelve hallazgos ordenados de forma estable y el nº de hechos sin regla en el catálogo."""
    ordered = sorted(facts, key=lambda f: (f.location.path, f.location.start_line or 0,
                                           f.tool, f.tool_rule, f.identity))
    source, seen, findings, unmapped = _SourceCache(root), {}, [], 0
    for fact in ordered:
        rule = _rule_for(fact, catalog)
        if rule is None:
            unmapped += 1
            continue
        evidence = fact.evidence if (fact.sensitive or fact.evidence) else \
            source.line(fact.location.path, fact.location.start_line)
        findings.append(to_hallazgo(fact, rule, evidence, _fingerprint(rule.id, fact, evidence, seen)))
    return sorted(findings, key=lambda h: h.fingerprint), unmapped


def _is_applicable(rule: Rule, inventory: Inventory) -> bool:
    if "any" in rule.languages:
        return bool(inventory.languages)
    return any(lang in inventory.languages for lang in rule.languages)


def _relevant_languages(rule: Rule, inventory: Inventory) -> set[str]:
    present = set(inventory.languages)
    return present if "any" in rule.languages else present & set(rule.languages)


def compute_coverage(catalog: Catalog, inventory: Inventory, runs: list[ToolRun]) -> Coverage:
    by_name = {r.name: r for r in runs}
    applicable = sorted(r.id for r in catalog.rules.values() if _is_applicable(r, inventory))
    evaluated, gaps, partial = [], [], {}
    for rule_id in applicable:
        rule = catalog.rules[rule_id]
        langs, gap = support(rule, by_name)
        relevant = _relevant_languages(rule, inventory)
        if gap is None and langs is not None and not (relevant & langs):
            gap = Gap(rule_id=rule_id, reason="capability_missing",
                      detail=f"Sin evaluador para: {', '.join(sorted(relevant))}.")
        if gap:
            gaps.append(gap)
            continue
        evaluated.append(rule_id)
        if langs is not None and relevant - langs:
            partial[rule_id] = sorted(relevant - langs)
    return Coverage(applicable=applicable, evaluated=evaluated, gaps=gaps, partial=partial)
