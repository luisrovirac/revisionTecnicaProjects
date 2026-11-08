"""Protocolo de tres casos por regla (planInicial §5.3), para cada regla determinista evaluable.

caso 1: debe dispararla -> exactamente un hallazgo de esa regla, en la línea correcta
caso 2: contraejemplo seguro -> cero hallazgos de esa regla
caso 3: cambio no relacionado -> cero hallazgos de esa regla
"""

import pytest

from conftest import FIXTURES, findings_for, write_tree

# Material adversarial: vive en un fixture identificado como tal (safe_path de llm.prompt-injection).
ADVERSARIAL = (FIXTURES / "adversarial" / "prompt_injection.md").read_text(encoding="utf-8")

_DUP = (
    "def procesar(registros):\n"
    "    salida = []\n"
    "    for registro in registros:\n"
    "        nombre = registro.get('nombre', '').strip().lower()\n"
    "        importe = float(registro.get('importe', 0)) * 1.21\n"
    "        salida.append({'nombre': nombre, 'importe': round(importe, 2)})\n"
    "    return salida\n"
)
UNRELATED = {"src/pkg/otro.py": "VALOR = 1\n\n\ndef sumar(a, b):\n    return a + b\n"}


def _body(n: int) -> str:
    return "".join(f"    x{i} = {i}\n" for i in range(n)) + "    return x0\n"


CASES = {
    "py.func.max-lines": (
        {"src/pkg/m.py": "def larga():\n" + _body(20)},  # 21 líneas lógicas
        1,
        {"src/pkg/m.py": 'def justa():\n    """Doc.\n\n    Larga.\n    """\n    # comentario\n\n'
                         + _body(19)},  # 20 líneas: docstring, comentario y blanco no cuentan
    ),
    "any.class.max-public-methods": (
        {"src/pkg/m.py": "class C:\n" + "".join(f"    def m{i}(self):\n        return {i}\n"
                                               for i in range(6))},
        1,
        {"src/pkg/m.py": "class C:\n" + "".join(f"    def m{i}(self):\n        return {i}\n"
                                               for i in range(5))
                         + "    def _privado(self):\n        return 0\n"},
    ),
    "any.class.max-lines": (
        {"src/pkg/m.py": "class C:\n" + "".join(f"    a{i} = {i}\n" for i in range(101))},
        1,
        {"src/pkg/m.py": 'class C:\n    """Doc."""\n' + "".join(f"    a{i} = {i}\n" for i in range(100))},
    ),
    "py.import-in-method": (
        {"src/pkg/m.py": "def f():\n    import requests\n    return requests\n"},
        2,
        {"src/pkg/m.py": "import requests\n\n\ndef f():\n    import json\n    return json, requests\n"},
    ),
    "any.bare-except": (
        {"src/pkg/m.py": "def f():\n    try:\n        return 1\n    except:\n        return 0\n"},
        4,
        {"src/pkg/m.py": "import logging\n\n\ndef f():\n    try:\n        return 1\n"
                         "    except Exception:\n        logging.exception('x')\n        raise\n"},
    ),
    "py.no-print": (
        {"src/pkg/m.py": "def f():\n    print('hola')\n"},
        2,
        {"src/pkg/m.py": "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
                         "def f():\n    logger.info('hola')\n"},
    ),
    "any.tests.location": (
        {"src/pkg/test_algo.py": "def test_x():\n    assert True\n"},
        None,  # regla de ruta: sin línea
        {"tests/test_algo.py": "def test_x():\n    assert True\n",
         "tests/conftest.py": "\n"},
    ),
    "any.hardcoded-config": (
        {"src/pkg/cliente.py": "import os\n\nURL = 'https://api.pagos.internal/v1'\n"},
        3,
        {"src/pkg/config.py": "import os\n\nURL = os.environ.get('URL', 'https://api.local/v1')\n",
         "src/pkg/doc.py": '"""Ver https://docs.pagos.internal/guia."""\n\nNS = "http://www.w3.org/2000/svg"\n'},
    ),
    "llm.prompt-injection": (
        {"docs/notas.md": ADVERSARIAL},
        3,
        {"tests/fixtures/adversarial/caso.md": ADVERSARIAL,
         "docs/notas.md": "Las instrucciones del despliegue están en el README.\n"},
    ),
    "any.import.cycle": (
        {"pkg/__init__.py": "", "pkg/a.py": "from pkg import b\n", "pkg/b.py": "from pkg import a\n"},
        1,
        {"pkg/__init__.py": "", "pkg/a.py": "from pkg import b\n",
         "pkg/b.py": "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pkg import a\n"},
    ),
    "any.tests.missing": (
        {"src/pkg/motor.py": "def calcular():\n" + _body(30)},
        1,
        {"src/pkg/motor.py": "def calcular():\n" + _body(30),
         "tests/test_integracion.py": "from pkg.motor import calcular\n\n\ndef test_c():\n"
                                      "    assert calcular() == 0\n"},
    ),
    "any.duplication.ratio": (
        {"src/pkg/a.py": _DUP, "src/pkg/b.py": _DUP.replace("procesar", "tratar")},
        1,  # el bloque empieza en "(" tras el nombre, que es lo único distinto
        {"src/pkg/a.py": _DUP, "src/pkg/b.py": "def otra(x):\n    return [y * 2 for y in x if y]\n"},
    ),
    "ts.no-any": (
        {"web/api.ts": "export const x = 1;\nexport function f(d: any): string {\n  return String(d);\n}\n"},
        2,
        {"web/api.ts": "// any en comentario\nexport function f(d: unknown): string {\n  return 'any';\n}\n"},
    ),
}


def _of_rule(findings, rule_id):
    return [h for h in findings if h.rule_id == rule_id]


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_case_1_triggers_exactly_once_on_the_right_line(rule_id, tmp_path):
    files, expected_line, _ = CASES[rule_id]
    hits = _of_rule(findings_for(write_tree(tmp_path, files)), rule_id)
    assert len(hits) == 1
    assert hits[0].location.start_line == expected_line


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_case_2_safe_counterexample_produces_nothing(rule_id, tmp_path):
    _, _, safe = CASES[rule_id]
    assert _of_rule(findings_for(write_tree(tmp_path, safe)), rule_id) == []


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_case_3_unrelated_change_produces_nothing(rule_id, tmp_path):
    assert _of_rule(findings_for(write_tree(tmp_path, UNRELATED)), rule_id) == []
