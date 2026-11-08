"""Pista B: selectores deterministas + juicio del modelo con evidencia obligatoria."""

import json
import re

import pytest
from conftest import ROOT, write_tree

from tec_review.agentic.candidates import select_candidates
from tec_review.agentic.interpret import Budget
from tec_review.agentic.track_b import Judge, quote_is_literal, region_lines
from tec_review.domain.models import LLMUsage
from tec_review.llm.fake import FakeLLM
from tec_review.rules.catalog import load_catalog

CATALOG = load_catalog(ROOT / "catalog", "universal")


def _long(name: str, n: int, extra: str = "") -> str:
    return (
        f"def {name}():\n{extra}"
        + "".join(f"    v{i} = {i}\n" for i in range(n))
        + "    return v0\n"
    )


SELECTOR_CASES = {
    "design.srp": (_long("enorme", 26), _long("corta", 8)),
    "design.dip.direct-instantiation": (
        "class Servicio:\n    def ejecutar(self):\n        repo = Repositorio()\n        return repo\n",
        ("class RepoFactory:\n    def create(self):\n        return Repositorio()\n\n\n"
        "class Otro:\n    def ruta(self, p):\n        return Path(p)\n"),
    ),
    "design.ocp.conditional-dispatch": (
        ("def tarifa(tipo):\n    if tipo == 'a':\n        return 1\n    elif tipo == 'b':\n        return 2\n"
        "    elif tipo == 'c':\n        return 3\n    elif tipo == 'd':\n        return 4\n    return 0\n"),
        "def tarifa(tipo):\n    if tipo == 'a':\n        return 1\n    return 0\n",
    ),
    "design.isp.fat-interface": (
        "from typing import Protocol\n\n\nclass Repo(Protocol):\n"
        + "".join(f"    def m{i}(self): ...\n" for i in range(6)),
        "from typing import Protocol\n\n\nclass Repo(Protocol):\n"
        + "".join(f"    def m{i}(self): ...\n" for i in range(3)),
    ),
    "design.lsp.contract-break": (
        ("class Base:\n    def pagar(self, importe):\n        return importe\n\n\n"
        "class Hija(Base):\n    def pagar(self):\n        raise NotImplementedError\n"),
        ("class Base:\n    def pagar(self, importe):\n        return importe\n\n\n"
        "class Hija(Base):\n    def pagar(self, importe):\n        return importe * 2\n"),
    ),
    "design.thin-entrypoints": (
        "@app.post('/pagos')\n" + _long("crear_pago", 13),
        "@app.post('/pagos')\ndef crear_pago():\n    return servicio.crear()\n",
    ),
    "config.startup-validation": (
        "import os\n\n\ndef conectar():\n    return os.getenv('DB_URL')\n",
        "import os\n\nDB_URL = os.getenv('DB_URL')\n",
    ),
    "resilience.retry-backoff": (
        "import requests\n\n\ndef bajar(u):\n    return requests.get(u, timeout=5)\n",
        "import requests\n\n\n@retry(times=3)\ndef bajar(u):\n    return requests.get(u, timeout=5)\n",
    ),
    "resilience.resource-release": (
        "def leer(p):\n    f = open(p)\n    datos = f.read()\n    return datos\n",
        "def leer(p):\n    with open(p) as f:\n        return f.read()\n",
    ),
    "llm.output-to-sink": (
        ("import subprocess\n\n\ndef ejecutar(client, q):\n"
        "    r = client.chat.completions.create(model='m', messages=q, max_tokens=50)\n"
        "    return subprocess.run(r.text, shell=True)\n"),
        "def preguntar(client, q):\n    return client.chat.completions.create(model='m', messages=q, max_tokens=5)\n",
    ),
    "llm.secrets-in-prompt": (
        "system_prompt = f'Usa la clave {api_key} para todo'\n",
        "system_prompt = f'Hola {nombre}'\n",
    ),
    "llm.unbounded-consumption": (
        "def preguntar(client, q):\n    return client.messages.create(model='m', messages=q)\n",
        "def preguntar(client, q):\n    return client.messages.create(model='m', messages=q, max_tokens=500)\n",
    ),
}


def _candidates(tmp_path, rule_id, source):
    write_tree(tmp_path, {"src/app/modulo.py": source})
    return select_candidates(tmp_path, ["src/app/modulo.py"], [rule_id], max_per_rule=5)[rule_id]


def test_every_judgment_rule_has_a_selector_case():
    agent_rules = {r.id for r in CATALOG.by_kind("agent")}
    assert agent_rules == set(SELECTOR_CASES)


@pytest.mark.parametrize("rule_id", sorted(SELECTOR_CASES))
def test_selector_proposes_the_suspicious_region(rule_id, tmp_path):
    assert len(_candidates(tmp_path, rule_id, SELECTOR_CASES[rule_id][0])) == 1


@pytest.mark.parametrize("rule_id", sorted(SELECTOR_CASES))
def test_selector_ignores_the_safe_counterexample(rule_id, tmp_path):
    assert _candidates(tmp_path, rule_id, SELECTOR_CASES[rule_id][1]) == []


# --- juez -----------------------------------------------------------------------------------

LINE_RE = re.compile(r"^\s*(\d+) \| (.*)$", re.MULTILINE)


def _answer(violates=True, quote=None, field="instantiation_site", line=None, explanation=None):
    def responder(messages):
        user = messages[1].content
        cid = re.search(r'"candidate_id": "([^"]+)"', user).group(1)
        rows = {int(n): t for n, t in LINE_RE.findall(user)}
        target = line or next(n for n, t in rows.items() if "Repositorio()" in t)
        return json.dumps(
            {
                "candidate_id": cid,
                "violates": violates,
                "explanation": explanation or "El método crea `Repositorio` en vez de recibirlo.",
                "impact": "Impide sustituirlo en tests.",
                "fix": "Inyectarlo por constructor.",
                "evidence": [
                    {"field": field, "lines": [target], "quote": quote or rows[target].strip()}
                ]
                if violates
                else [],
            }
        )

    return responder


def _judge(tmp_path, responder):
    rule = CATALOG.get("design.dip.direct-instantiation")
    [candidate] = _candidates(tmp_path, rule.id, SELECTOR_CASES[rule.id][0])
    judge = Judge(FakeLLM(responder), 500, Budget(limit=10_000), LLMUsage())
    return judge.judge(tmp_path, candidate, rule)


def test_judgment_with_literal_evidence_is_published(tmp_path):
    judgment = _judge(tmp_path, _answer())
    assert judgment.status == "published"
    assert judgment.finding.provenance.tool == "track-b"
    assert judgment.finding.location.start_line == 3
    assert judgment.finding.confidence < 1.0


def test_model_saying_no_violation_is_dismissed(tmp_path):
    assert _judge(tmp_path, _answer(violates=False)).status == "dismissed"


def test_invented_quote_is_rejected(tmp_path):
    judgment = _judge(tmp_path, _answer(quote="repo = RepositorioMagico()"))
    assert judgment.status == "rejected"
    assert any("literalmente" in r for r in judgment.reasons)


def test_missing_required_evidence_field_is_rejected(tmp_path):
    judgment = _judge(tmp_path, _answer(field="otra_cosa"))
    assert judgment.status == "rejected"
    assert any("falta evidencia" in r for r in judgment.reasons)


def test_lines_outside_region_are_rejected(tmp_path):
    assert _judge(tmp_path, _answer(line=99, quote="x = 1")).status == "rejected"


def test_invented_identifier_in_explanation_is_rejected(tmp_path):
    judgment = _judge(tmp_path, _answer(explanation="Usa `ServicioFantasma` sin inyectar."))
    assert judgment.status == "rejected"


def test_region_is_capped(tmp_path):
    write_tree(tmp_path, {"m.py": _long("f", 200)})
    [candidate] = select_candidates(tmp_path, ["m.py"], ["design.srp"], 1)["design.srp"]
    assert len(region_lines(tmp_path, candidate)) == 80


def test_multiline_quote_of_non_contiguous_lines_is_literal():
    sources = ["def a(self):", "x = 1", "def b(self):"]
    assert quote_is_literal("def b(self):\n    def a(self):", sources)
    assert not quote_is_literal("def b(self):\n    def c(self):", sources)
