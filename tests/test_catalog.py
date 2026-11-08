"""El catálogo es el contrato: citas literales, safe_path, IDs estables (planInicial §5)."""

import re
from pathlib import Path

import pytest

from tec_review.rules.catalog import load_all_rules, load_catalog

# Partes no normativas de baseForRules.md (C6): preámbulo y tabla-resumen final.
NORMATIVE_BOUNDS = {
    "baseForRules.md": ("# Reglas de Codificación y Ingeniería", "### Resumen de las Ampliaciones"),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normative_text(docs_dir: Path, doc: str) -> str:
    text = (docs_dir / doc).read_text(encoding="utf-8")
    start, end = NORMATIVE_BOUNDS.get(doc, (None, None))
    if start:
        text = text[text.index(start) : text.index(end)]
    return _normalize(text)


def test_catalog_v1_has_30_rules_split_18_deterministic_12_judgment(catalog_dir):
    rules = load_all_rules(catalog_dir)
    judgment = [r for r in rules if r.agent_required]
    assert len(rules) == 30
    assert len(judgment) == 12


def test_every_quote_exists_literally_in_normative_rules_text(catalog_dir, rules_docs_dir):
    for rule in load_all_rules(catalog_dir):
        for source in rule.sources:
            body = _normative_text(rules_docs_dir, source.doc)
            assert _normalize(source.quote) in body, f"{rule.id}: cita no encontrada en {source.doc}"


def test_judgment_rules_declare_required_evidence(catalog_dir):
    for rule in load_all_rules(catalog_dir):
        if rule.agent_required:
            assert rule.evidence_required, rule.id
            assert rule.check.kind == "agent", rule.id


def test_universal_excludes_rules_whose_only_source_is_rules_plus(catalog_dir):
    universal = load_catalog(catalog_dir, "universal")
    devsax = load_catalog(catalog_dir, "devsaxaiflow")
    assert universal.get("py.import-in-method") is None
    assert devsax.get("py.import-in-method") is not None
    assert len(devsax.rules) == 30


def test_tool_codes_resolve_to_rules(catalog_dir):
    catalog = load_catalog(catalog_dir, "universal")
    assert catalog.for_tool_code("ruff", "T201").id == "py.no-print"
    assert catalog.for_tool_code("secureprojects", "secret").id == "sec.secret-exposed"


def test_unknown_ruleset_fails_fast(catalog_dir):
    with pytest.raises(ValueError, match="Ruleset desconocido"):
        load_catalog(catalog_dir, "inexistente")
