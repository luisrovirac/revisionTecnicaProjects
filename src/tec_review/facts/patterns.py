"""Reglas por patrones (check.kind: regex): configuración fija e inyección de prompts.

- hardcoded_config: literales de cadena con URL, IP o ruta absoluta. En Python se usan los nodos
  `ast.Constant` (excluye comentarios y docstrings); en lenguajes tipo C, literales entre comillas
  en líneas que no son comentario. Excepciones legítimas: módulos de configuración y tests.
- prompt_injection: frases que intentan dar órdenes a un LLM, en cualquier archivo de texto.
  Excepción legítima: material adversarial identificado como tal (fixtures, red team).
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path, PurePosixPath

from tec_review import __version__
from tec_review.domain.models import Location, RawFact
from tec_review.domain.ports import AnalyzerResult
from tec_review.facts.inventory import LANGUAGE_BY_EXT, read_lines
from tec_review.facts.paths import test_location_problem
from tec_review.rules.capabilities import C_LIKE
from tec_review.rules.catalog import Rule

TOOL = "tec-review-regex"
URL = re.compile(r"\b(?:https?|wss?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|s?ftp)://[^\s'\"`<>]+",
                 re.IGNORECASE)
IP = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?::\d{2,5})?$")
ABS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/(?:home|Users|var|etc|opt|srv|mnt|tmp)/)")
DOC_HOSTS = re.compile(r"://(?:[\w.-]*\.)?(?:w3\.org|json-schema\.org|example\.(?:com|org|net)|"
                       r"schemas?\.[\w.-]+|xmlns\.[\w.-]+|purl\.org|opensource\.org)\b", re.IGNORECASE)
URL_CREDENTIALS = re.compile(r"(://[^:/\s]+):[^@/\s]+@")
C_STRING = re.compile(r"\"((?:[^\"\\\n]|\\.){6,})\"|'((?:[^'\\\n]|\\.){6,})'|`([^`\n]{6,})`")
C_COMMENT_START = ("//", "/*", "*", "#")
CONFIG_MODULE = re.compile(r"(?:^|[_.-])(?:config|configuration|settings|conf|env)(?:$|[_.-])")
INJECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts?|rules)",
    r"\bdisregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|system)\s+(?:instructions|prompts?)",
    r"\bignora\s+(?:todas\s+)?(?:las\s+)?instrucciones\s+(?:anteriores|previas)",
    r"\bolvida\s+(?:todas\s+)?(?:tus|las)\s+instrucciones",
    r"\byou\s+are\s+now\s+(?:in\s+)?(?:developer|dan|jailbreak)\s+mode",
    r"\b(?:reveal|print|show)\s+(?:your|the)\s+system\s+prompt",
    r"\b(?:ai|llm)\s+(?:reviewer|agent|assistant)s?\b.{0,40}\b(?:approve|do\s+not\s+report|no\s+reportes)",
)]
ADVERSARIAL_MARKERS = ("fixtures", "adversarial", "redteam", "red_team", "injection")


def is_config_module(rel: str) -> bool:
    return bool(CONFIG_MODULE.search(PurePosixPath(rel).stem.lower()))


def is_test_file(rel: str) -> bool:
    path = PurePosixPath(rel)
    return "tests" in path.parts[:-1] or path.name.startswith("test_") \
        or test_location_problem(rel) is not None


def config_problem(literal: str) -> str | None:
    """Devuelve el tipo de valor fijo encontrado en el literal, o None."""
    text = literal.strip()
    url = URL.search(text)
    if url and not DOC_HOSTS.search(url.group(0)):
        return "URL"
    if IP.match(text) and not text.startswith(("0.0.0.0", "255.")):
        return "IP"
    return "ruta absoluta" if ABS_PATH.match(text) else None


def _redact(literal: str) -> str:
    return URL_CREDENTIALS.sub(r"\1:****@", literal)[:120]


def _python_literals(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(getattr(node.body[0], "value", None), ast.Constant)}
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def _c_like_literals(lines: list[str]) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith(C_COMMENT_START):
            continue
        found += [(number, next(g for g in m.groups() if g)) for m in C_STRING.finditer(line)]
    return found


class PatternAnalyzer:
    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        by_set = {getattr(r.check, "pattern_set", None): r for r in rules if r.check.kind == "regex"}
        self.config_rule = by_set.get("hardcoded_config")
        self.injection_rule = by_set.get("prompt_injection")

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        facts, warnings = [], []
        for rel in files:
            try:
                facts += self._config_facts(root, rel) + self._injection_facts(root, rel)
            except (SyntaxError, ValueError, OSError) as exc:
                warnings.append(f"parse_error {rel}: {exc.__class__.__name__}")
        return AnalyzerResult.ok(TOOL, __version__, started, facts, warnings)

    def _fact(self, rule: Rule, rel: str, line: int, message: str, identity: str) -> RawFact:
        return RawFact(tool=TOOL, tool_version=__version__, tool_rule=rule.id,
                       location=Location(path=rel, start_line=line, end_line=line),
                       message=message, identity=identity)

    def _config_facts(self, root: Path, rel: str) -> list[RawFact]:
        language = LANGUAGE_BY_EXT.get(PurePosixPath(rel).suffix)
        if self.config_rule is None or is_config_module(rel) or is_test_file(rel):
            return []
        if language == "python":
            literals = _python_literals((root / rel).read_text(encoding="utf-8", errors="replace"))
        elif language in C_LIKE:
            literals = _c_like_literals(read_lines(root, rel))
        else:
            return []
        return [self._fact(self.config_rule, rel, line,
                           f"{kind} fija en el código: `{_redact(value)}`.", _redact(value))
                for line, value in literals if (kind := config_problem(value))]

    def _injection_facts(self, root: Path, rel: str) -> list[RawFact]:
        lowered = rel.lower()
        if self.injection_rule is None or any(m in lowered for m in ADVERSARIAL_MARKERS):
            return []
        facts = []
        for number, line in enumerate(read_lines(root, rel), start=1):
            match = next((m for p in INJECTION_PATTERNS if (m := p.search(line))), None)
            if match:
                facts.append(self._fact(self.injection_rule, rel, number,
                                        f"Texto que intenta dar órdenes a un LLM: «{match.group(0)}».",
                                        match.group(0).lower()))
        return facts
