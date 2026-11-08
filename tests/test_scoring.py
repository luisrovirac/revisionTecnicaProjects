"""Scoring y triage deterministas (I5)."""

from tec_review.domain.models import Dimension, Hallazgo, Location, Provenance, Severity
from tec_review.scoring import confidence_level, score
from tec_review.triage import rank, select_for_interpretation


def _h(fp: str, severity: Severity, rule: str = "r.x", path: str = "src/m.py",
       dimension: Dimension = Dimension.MAINTAINABILITY, scope: float = 1.0) -> Hallazgo:
    return Hallazgo(fingerprint=fp, rule_id=rule, title="t", severity=severity, dimension=dimension,
                    location=Location(path=path, start_line=1), message="m", scope_factor=scope,
                    provenance=Provenance(tool="t", tool_version="1", original_rule="x"))


def test_no_findings_is_go_with_full_score():
    card = score([], coverage_ratio=1.0)
    assert (card.score, card.verdict) == (100.0, "GO")


def test_any_critical_is_no_go_and_any_high_is_conditional():
    assert score([_h("a", Severity.CRITICAL, dimension=Dimension.SECURITY)], 1.0).verdict == "NO-GO"
    assert score([_h("a", Severity.HIGH, dimension=Dimension.SECURITY)], 1.0).verdict == "CONDITIONAL"


def test_many_minor_findings_weigh_less_than_one_critical():
    lows = [_h(f"l{i}", Severity.LOW) for i in range(100)]
    critical = [_h("c", Severity.CRITICAL)]
    assert score(lows, 1.0).score > score(critical, 1.0).score


def test_findings_in_tests_weigh_less():
    prod = score([_h("a", Severity.MEDIUM)], 1.0).score
    in_tests = score([_h("a", Severity.MEDIUM, scope=0.3)], 1.0).score
    assert in_tests > prod


def test_confidence_reflects_coverage_not_score():
    assert confidence_level(0.2) == "baja"
    assert score([], coverage_ratio=0.2).confidence == "baja"


def test_triage_orders_by_priority_and_breaks_ties_by_fingerprint():
    items = [_h("b", Severity.LOW), _h("a", Severity.LOW), _h("z", Severity.HIGH)]
    assert [h.fingerprint for h in rank(items)] == ["z", "a", "b"]
    assert [h.fingerprint for h in select_for_interpretation(items, 1)] == ["z"]


def test_triage_never_selects_info_findings():
    assert select_for_interpretation([_h("i", Severity.INFO)], None) == []
