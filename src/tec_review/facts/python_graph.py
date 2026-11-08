"""Grafo de imports de Python (check.kind: graph).

- import_cycle: componentes fuertemente conexos de tamaño > 1 entre imports de nivel de módulo.
  Los imports bajo `if TYPE_CHECKING:` y dentro de funciones no cuentan (no crean ciclo en carga).
- module_without_test: módulo importante (>= 30 líneas lógicas y alguna definición pública) que
  ningún test alcanza por imports, directa o transitivamente, ni tiene un test_<módulo>.py.
"""

from __future__ import annotations

import ast
import time
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from tec_review import __version__
from tec_review.domain.models import Location, RawFact
from tec_review.domain.ports import AnalyzerResult
from tec_review.facts.patterns import is_test_file
from tec_review.facts.python_ast import code_lines
from tec_review.rules.catalog import Rule

TOOL = "tec-review-graph"
IMPORTANT_MIN_LINES = 30
NOT_IMPORTANT = {"__init__", "__main__", "conftest", "setup", "manage"}


class Edge(BaseModel):
    source: str
    target: str
    line: int


class ModuleInfo(BaseModel):
    name: str
    path: str
    is_package: bool
    logical_lines: int = 0
    has_public_defs: bool = False


def module_name(rel: str) -> tuple[str, bool]:
    parts = list(PurePosixPath(rel).with_suffix("").parts)
    if parts and parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
        (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def module_level_imports(body: list[ast.stmt]):
    """Imports ejecutados al cargar el módulo (incluye if/try, excluye TYPE_CHECKING y funciones)."""
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If) and not _is_type_checking(node):
            yield from module_level_imports(node.body + node.orelse)
        elif isinstance(node, ast.Try):
            yield from module_level_imports(node.body + node.orelse + node.finalbody
                                            + [s for h in node.handlers for s in h.body])


class _Resolver:
    def __init__(self, modules: dict[str, ModuleInfo]) -> None:
        self.modules = modules

    def _longest_known(self, dotted: str) -> str | None:
        parts = dotted.split(".")
        for size in range(len(parts), 0, -1):
            candidate = ".".join(parts[:size])
            if candidate in self.modules:
                return candidate
        return None

    def _base_package(self, current: ModuleInfo, level: int) -> str:
        parts = current.name.split(".") if current.name else []
        if not current.is_package:
            parts = parts[:-1]
        return ".".join(parts[: len(parts) - (level - 1)] if level > 1 else parts)

    def targets(self, current: ModuleInfo, node: ast.Import | ast.ImportFrom) -> list[str]:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            base = self._base_package(current, node.level) if node.level else ""
            module = ".".join(p for p in (base, node.module or "") if p)
            names = [f"{module}.{a.name}" if module else a.name for a in node.names] or [module]
        found = {t for n in names if (t := self._longest_known(n)) and t != current.name}
        return sorted(found)


class _Tarjan:
    """Tarjan iterativo (sin recursión, para grafos grandes)."""

    def __init__(self, edges: dict[str, list[str]]) -> None:
        self.edges = edges
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.stack: list[str] = []
        self.on_stack: set[str] = set()
        self.components: list[list[str]] = []

    def visit(self, root: str) -> None:
        work: list[tuple[str, Iterator[str]]] = []
        self._enter(root, work)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is None:
                self._leave(node, work)
            elif child not in self.index:
                self._enter(child, work)
            elif child in self.on_stack:
                self.low[node] = min(self.low[node], self.index[child])

    def _enter(self, node: str, work: list[tuple[str, Iterator[str]]]) -> None:
        self.index[node] = self.low[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        work.append((node, iter(self.edges.get(node, []))))

    def _leave(self, node: str, work: list[tuple[str, Iterator[str]]]) -> None:
        work.pop()
        if work:
            parent = work[-1][0]
            self.low[parent] = min(self.low[parent], self.low[node])
        if self.low[node] == self.index[node]:
            self._pop_component(node)

    def _pop_component(self, root: str) -> None:
        component = []
        while True:
            member = self.stack.pop()
            self.on_stack.discard(member)
            component.append(member)
            if member == root:
                break
        if len(component) > 1:
            self.components.append(sorted(component))


def strongly_connected(nodes: list[str], edges: dict[str, list[str]]) -> list[list[str]]:
    """Componentes fuertemente conexos con más de un nodo, en orden determinista."""
    tarjan = _Tarjan(edges)
    for node in nodes:
        if node not in tarjan.index:
            tarjan.visit(node)
    return sorted(tarjan.components)


class PythonGraphAnalyzer:
    name = TOOL

    def __init__(self, rules: list[Rule]) -> None:
        by_metric = {r.check.metric: r for r in rules if r.check.kind == "graph"}
        self.cycle_rule = by_metric.get("import_cycle")
        self.missing_test_rule = by_metric.get("module_without_test")

    def run(self, root: Path, files: list[str]) -> AnalyzerResult:
        started = time.perf_counter()
        modules, trees, warnings = self._load(root, [f for f in files if f.endswith(".py")])
        edges = self._edges(modules, trees)
        facts = self._cycle_facts(modules, edges) + self._missing_test_facts(modules, edges, files)
        return AnalyzerResult.ok(TOOL, __version__, started, facts, warnings)

    def _load(self, root: Path, py_files: list[str]):
        modules, trees, warnings = {}, {}, []
        for rel in py_files:
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                warnings.append(f"parse_error {rel}: grafo")
                continue
            name, is_package = module_name(rel)
            public = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                         and not n.name.startswith("_") for n in tree.body)
            modules[name] = ModuleInfo(name=name, path=rel, is_package=is_package,
                                       logical_lines=len(code_lines(source)), has_public_defs=public)
            trees[name] = tree
        return modules, trees, warnings

    def _edges(self, modules: dict[str, ModuleInfo], trees: dict[str, ast.Module]) -> list[Edge]:
        resolver = _Resolver(modules)
        edges = []
        for name, tree in sorted(trees.items()):
            for node in module_level_imports(tree.body):
                edges += [Edge(source=name, target=t, line=node.lineno)
                          for t in resolver.targets(modules[name], node)]
        return edges

    def _cycle_facts(self, modules, edges: list[Edge]) -> list[RawFact]:
        if self.cycle_rule is None:
            return []
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge.source, []).append(edge.target)
        facts = []
        for component in strongly_connected(sorted(modules), adjacency):
            members = set(component)
            first = next(e for e in edges if e.source == component[0] and e.target in members)
            message = "Ciclo de imports entre: " + " → ".join(f"`{m}`" for m in component) + "."
            facts.append(RawFact(tool=TOOL, tool_version=__version__, tool_rule=self.cycle_rule.id,
                                 location=Location(path=modules[component[0]].path,
                                                   start_line=first.line, end_line=first.line),
                                 message=message, identity="|".join(component)))
        return facts

    def _reachable_from_tests(self, modules, edges: list[Edge]) -> set[str]:
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge.source, set()).add(edge.target)
        pending = [m.name for m in modules.values() if is_test_file(m.path)]
        seen = set(pending)
        while pending:
            for target in adjacency.get(pending.pop(), ()):
                if target not in seen:
                    seen.add(target)
                    pending.append(target)
        return seen

    def _missing_test_facts(self, modules, edges, files: list[str]) -> list[RawFact]:
        if self.missing_test_rule is None:
            return []
        reached = self._reachable_from_tests(modules, edges)
        test_stems = {PurePosixPath(f).stem.removeprefix("test_") for f in files if is_test_file(f)}
        facts = []
        for info in sorted(modules.values(), key=lambda m: m.path):
            stem = PurePosixPath(info.path).stem
            important = (info.logical_lines >= IMPORTANT_MIN_LINES and info.has_public_defs
                         and stem not in NOT_IMPORTANT and not is_test_file(info.path))
            if important and info.name not in reached and stem not in test_stems:
                message = (f"El módulo `{info.name}` ({info.logical_lines} líneas lógicas) no tiene "
                           f"tests que lo importen ni un `test_{stem}.py`.")
                facts.append(RawFact(tool=TOOL, tool_version=__version__,
                                     tool_rule=self.missing_test_rule.id,
                                     location=Location(path=info.path, start_line=1, end_line=1),
                                     message=message, identity=info.name))
        return facts
