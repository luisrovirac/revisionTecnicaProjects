"""Métricas de forma para Python con `ast` + `tokenize` (sin ejecutar código del target).

Definición operativa de "línea lógica" (C8): línea del cuerpo con al menos un token de código,
excluyendo blancos, comentarios y docstring. La firma y los decoradores no cuentan.
"""

from __future__ import annotations

import ast
import io
import sys
import time
import tokenize
from pathlib import Path

from tec_review import __version__
from tec_review.domain.models import Location, RawFact
from tec_review.domain.ports import AnalyzerResult
from tec_review.rules.catalog import Rule

TOOL = "tec-review-ast"
NON_CODE_TOKENS = {
    tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
    tokenize.ENCODING, tokenize.ENDMARKER,
}
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def code_lines(source: str) -> set[int]:
    lines: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in NON_CODE_TOKENS:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    return lines


def _has_docstring(body: list[ast.stmt]) -> bool:
    first = body[0] if body else None
    return isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
        and isinstance(first.value.value, str)


def logical_lines(node: ast.ClassDef | FunctionNode, lines_with_code: set[int]) -> int:
    body = node.body[1:] if _has_docstring(node.body) else node.body
    if not body:
        return 0
    start, end = body[0].lineno, node.end_lineno or body[-1].lineno
    return sum(1 for n in range(start, end + 1) if n in lines_with_code)


class _Collector(ast.NodeVisitor):
    """Recorre el módulo guardando el nombre cualificado de cada función y clase."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.functions: list[tuple[str, FunctionNode]] = []
        self.classes: list[tuple[str, ast.ClassDef]] = []
        self.imports_in_functions: list[tuple[str, ast.Import | ast.ImportFrom]] = []
        self._function_depth = 0

    def _visit_scope(self, node, bucket) -> None:
        self.stack.append(node.name)
        bucket.append((".".join(self.stack), node))
        is_function = not isinstance(node, ast.ClassDef)
        self._function_depth += is_function
        self.generic_visit(node)
        self._function_depth -= is_function
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node, self.functions)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node, self.classes)

    def visit_Import(self, node: ast.Import) -> None:
        if self._function_depth:
            self.imports_in_functions.append((".".join(self.stack), node))

    visit_ImportFrom = visit_Import


def _non_stdlib_modules(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        if node.level:  # import relativo: siempre del propio proyecto
            return ["." * node.level + (node.module or "")]
        names = [node.module or ""]
    else:
        names = [alias.name for alias in node.names]
    return [n for n in names if n.split(".")[0] not in sys.stdlib_module_names]


class PythonAstAnalyzer:
    """Evalúa las reglas `check.kind: ast` del catálogo sobre archivos Python."""

    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        self.rules = {r.check.metric: r for r in rules if r.check.kind == "ast"}

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        facts, warnings = [], []
        for rel in (f for f in files if f.endswith(".py")):
            try:
                facts.extend(self._analyze_file(root, rel))
            except (SyntaxError, ValueError, tokenize.TokenError) as exc:
                warnings.append(f"parse_error {rel}: {exc.__class__.__name__}")
        return AnalyzerResult.ok(TOOL, __version__, started, facts, warnings)

    def _analyze_file(self, root: Path, rel: str) -> list[RawFact]:
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        collector = _Collector()
        collector.visit(ast.parse(source, filename=rel))
        lines_with_code = code_lines(source)
        facts = self._function_facts(rel, collector, lines_with_code)
        facts += self._class_facts(rel, collector, lines_with_code)
        facts += self._import_facts(rel, collector)
        return facts

    def _fact(self, metric: str, rel: str, node: ast.AST, symbol: str, message: str,
              identity: str) -> RawFact:
        rule = self.rules[metric]
        location = Location(path=rel, start_line=node.lineno, end_line=node.end_lineno)
        return RawFact(tool=TOOL, tool_version=__version__, tool_rule=rule.id,
                       location=location, message=message, symbol=symbol, identity=identity)

    def _function_facts(self, rel, collector, lines_with_code) -> list[RawFact]:
        metric = "function_logical_lines"
        if metric not in self.rules:
            return []
        threshold = int(self.rules[metric].check.threshold or 0)
        facts = []
        for symbol, node in collector.functions:
            count = logical_lines(node, lines_with_code)
            if count > threshold:
                msg = f"La función `{symbol}` tiene {count} líneas lógicas (umbral {threshold})."
                facts.append(self._fact(metric, rel, node, symbol, msg, symbol))
        return facts

    def _class_facts(self, rel, collector, lines_with_code) -> list[RawFact]:
        facts = []
        for symbol, node in collector.classes:
            facts += self._class_methods_fact(rel, symbol, node)
            facts += self._class_lines_fact(rel, symbol, node, lines_with_code)
        return facts

    def _class_methods_fact(self, rel, symbol, node: ast.ClassDef) -> list[RawFact]:
        rule = self.rules.get("class_public_methods")
        if not rule:
            return []
        public = [n.name for n in node.body
                  if isinstance(n, FunctionNode) and not n.name.startswith("_")]
        threshold = int(rule.check.threshold or 0)
        if len(public) <= threshold:
            return []
        msg = (f"La clase `{symbol}` expone {len(public)} métodos públicos (umbral {threshold}): "
               + ", ".join(f"`{p}`" for p in public) + ".")
        return [self._fact("class_public_methods", rel, node, symbol, msg, symbol)]

    def _class_lines_fact(self, rel, symbol, node, lines_with_code) -> list[RawFact]:
        rule = self.rules.get("class_logical_lines")
        if not rule:
            return []
        count, threshold = logical_lines(node, lines_with_code), int(rule.check.threshold or 0)
        if count <= threshold:
            return []
        msg = f"La clase `{symbol}` tiene {count} líneas lógicas (umbral {threshold})."
        return [self._fact("class_logical_lines", rel, node, symbol, msg, symbol)]

    def _import_facts(self, rel, collector) -> list[RawFact]:
        metric = "non_stdlib_import_in_function"
        if metric not in self.rules:
            return []
        facts = []
        for symbol, node in collector.imports_in_functions:
            for module in _non_stdlib_modules(node):
                msg = f"`{symbol}` importa `{module}` dentro de la función."
                facts.append(self._fact(metric, rel, node, symbol, msg, f"{symbol}:{module}"))
        return facts
