"""Pista B, paso determinista: selectores de candidatos por regla (Python).

El modelo no recorre el repositorio. Cada regla de juicio tiene un selector barato y explicable
que propone regiones sospechosas; el modelo solo decide sobre esas regiones. Así el coste está
acotado y cada candidato tiene un motivo trazable (`hint`).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel

from tec_review.facts.patterns import is_config_module, is_test_file
from tec_review.facts.python_ast import code_lines, logical_lines

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
VALUE_TYPES = {
    "Path",
    "PurePosixPath",
    "Decimal",
    "UUID",
    "Counter",
    "OrderedDict",
    "Field",
    "BaseModel",
    "Enum",
    "Exception",
    "ValueError",
    "TypeError",
    "KeyError",
}
FACTORY_NAME = re.compile(r"^(?:create|build|make|from|new|get_or_create)_|factory", re.IGNORECASE)
ENTRYPOINT_DECORATORS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "route",
    "api_route",
    "websocket",
    "command",
    "callback",
    "task",
    "on_event",
    "handler",
    "listener",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "request", "send", "stream", "urlopen"}
HTTP_RECEIVERS = re.compile(r"requests|httpx|aiohttp|urllib|client|session", re.IGNORECASE)
LLM_CALL = re.compile(r"^(?:create|complete|completion|acompletion|chat|invoke|ainvoke|generate)$")
LLM_RECEIVER = re.compile(
    r"llm|openai|anthropic|chat|completions|messages|model|router", re.IGNORECASE
)
SINK_ATTRS = {
    "system",
    "popen",
    "run",
    "call",
    "check_output",
    "Popen",
    "execute",
    "executemany",
    "render_template_string",
}
SECRET_NAME = re.compile(r"key|token|secret|password|passwd|credential", re.IGNORECASE)
PROMPT_NAME = re.compile(r"prompt|system|instruction", re.IGNORECASE)
RESOURCE_OPENERS = {"open", "connect", "cursor", "socket"}
LIMIT_KEYWORDS = {"max_tokens", "max_output_tokens", "max_completion_tokens", "max_new_tokens"}


class Candidate(BaseModel):
    rule_id: str
    path: str
    start_line: int
    end_line: int
    symbol: str
    hint: str
    weight: int  # orden determinista: mayor primero

    @property
    def candidate_id(self) -> str:
        return f"{self.rule_id}@{self.path}:{self.start_line}"


class Module(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    path: str
    tree: ast.Module
    code: set[int]


def _call_name(call: ast.Call) -> tuple[str, str]:
    """(receptor, nombre) de una llamada: requests.get -> ('requests', 'get'); open -> ('', 'open')."""
    func = call.func
    if isinstance(func, ast.Name):
        return "", func.id
    if isinstance(func, ast.Attribute):
        return ast.unparse(func.value), func.attr
    return "", ""


def _calls(node: ast.AST) -> Iterator[ast.Call]:
    return (n for n in ast.walk(node) if isinstance(n, ast.Call))


def _scopes(tree: ast.Module) -> Iterator[tuple[str, ast.AST, ast.ClassDef | None]]:
    """(nombre cualificado, nodo, clase contenedora) de cada función y clase."""
    pending: list[tuple[str, ast.AST, ast.ClassDef | None]] = [("", tree, None)]
    while pending:
        prefix, node, owner = pending.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                yield name, child, owner
                next_owner = child if isinstance(child, ast.ClassDef) else owner
                pending.append((f"{name}.", child, next_owner))


def _functions(module: Module) -> Iterator[tuple[str, FunctionNode, ast.ClassDef | None]]:
    for name, node, owner in _scopes(module.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield name, node, owner


def _candidate(
    rule_id: str, module: Module, node: ast.AST, symbol: str, hint: str, weight: int | None = None
) -> Candidate:
    size = logical_lines(node, module.code) if hasattr(node, "body") else 1
    return Candidate(
        rule_id=rule_id,
        path=module.path,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        symbol=symbol,
        hint=hint,
        weight=size if weight is None else weight,
    )


def _quoted(items) -> str:
    return ", ".join(f"`{i}`" for i in items)


def _per_function(
    rule_id: str,
    module: Module,
    collect: Callable[[FunctionNode], list[str]],
    describe: Callable[[list[str]], str],
) -> list[Candidate]:
    """Un candidato por función con hallazgos según `collect`; el peso es cuántos hay."""
    found = []
    for name, node, _ in _functions(module):
        items = collect(node)
        if items:
            hint = describe(items)
            found.append(_candidate(rule_id, module, node, name, hint, weight=len(items)))
    return found


def _srp_hint(node: ast.AST, size: int) -> str | None:
    if not isinstance(node, ast.ClassDef):
        return f"Función de {size} líneas lógicas." if size >= 25 else None
    public = [n for n in node.body if isinstance(n, FunctionNode) and not n.name.startswith("_")]
    if len(public) >= 4 or size >= 60:
        return f"Clase con {len(public)} métodos públicos y {size} líneas lógicas."
    return None


def srp(module: Module) -> list[Candidate]:
    found = []
    for name, node, _ in _scopes(module.tree):
        hint = _srp_hint(node, logical_lines(node, module.code))
        if hint:
            found.append(_candidate("design.srp", module, node, name, hint))
    return found


def _instantiations(node: FunctionNode) -> list[str]:
    names = []
    for call in _calls(node):
        _, called = _call_name(call)
        if (
            called[:1].isupper()
            and called not in VALUE_TYPES
            and not called.endswith(("Error", "Exception", "Warning"))
        ):
            names.append(called)
    return sorted(set(names))


def dip(module: Module) -> list[Candidate]:
    found = []
    for name, node, owner in _functions(module):
        if owner is None or FACTORY_NAME.search(node.name) or FACTORY_NAME.search(owner.name):
            continue
        created = _instantiations(node)
        if created:
            hint = "Instancia dentro del método: " + ", ".join(f"`{c}`" for c in created) + "."
            found.append(
                _candidate(
                    "design.dip.direct-instantiation", module, node, name, hint, weight=len(created)
                )
            )
    return found


def _branch_count(node: ast.If) -> int:
    count, current = 1, node
    while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
        count, current = count + 1, current.orelse[0]
    return count


def ocp(module: Module) -> list[Candidate]:
    found = []
    for name, node, _ in _functions(module):
        chains = [n for n in ast.walk(node) if isinstance(n, ast.If) and _branch_count(n) >= 4]
        matches = [n for n in ast.walk(node) if isinstance(n, ast.Match) and len(n.cases) >= 4]
        widest = max(
            [_branch_count(c) for c in chains] + [len(m.cases) for m in matches], default=0
        )
        if widest:
            found.append(
                _candidate(
                    "design.ocp.conditional-dispatch",
                    module,
                    node,
                    name,
                    f"Cadena condicional de {widest} ramas.",
                    weight=widest,
                )
            )
    return found


def _is_interface(node: ast.ClassDef) -> bool:
    bases = {ast.unparse(b).split(".")[-1] for b in node.bases}
    metaclass = {ast.unparse(k.value) for k in node.keywords if k.arg == "metaclass"}
    return bool(bases & {"Protocol", "ABC"}) or any("ABCMeta" in m for m in metaclass)


def isp(module: Module) -> list[Candidate]:
    found = []
    for name, node, _ in _scopes(module.tree):
        if isinstance(node, ast.ClassDef) and _is_interface(node):
            methods = [
                n.name
                for n in node.body
                if isinstance(n, FunctionNode) and not n.name.startswith("__")
            ]
            if len(methods) >= 6:
                found.append(
                    _candidate(
                        "design.isp.fat-interface",
                        module,
                        node,
                        name,
                        f"Interfaz con {len(methods)} métodos.",
                        weight=len(methods),
                    )
                )
    return found


def _arity(node: FunctionNode) -> int:
    args = node.args
    return len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)


def _raises_not_implemented(node: FunctionNode) -> bool:
    return any(
        isinstance(n, ast.Raise) and "NotImplementedError" in ast.unparse(n.exc or n)
        for n in ast.walk(node)
    )


def lsp_index(modules: list[Module]) -> dict[str, dict[str, tuple[str, FunctionNode]]]:
    """Clase -> {método: (ruta, nodo)} para resolver bases definidas en el propio repo."""
    index: dict[str, dict[str, tuple[str, FunctionNode]]] = {}
    for module in modules:
        for _, node, _ in _scopes(module.tree):
            if isinstance(node, ast.ClassDef):
                index[node.name] = {
                    n.name: (module.path, n) for n in node.body if isinstance(n, FunctionNode)
                }
    return index


def _breaks_contract(method: FunctionNode, base: FunctionNode) -> bool:
    return _arity(method) != _arity(base) or (
        _raises_not_implemented(method) and not _raises_not_implemented(base)
    )


def _overrides(
    node: ast.ClassDef, index: dict
) -> Iterator[tuple[str, FunctionNode, str, FunctionNode]]:
    """(base, método, ruta de la base, método base) por cada método que sobrescribe uno del repo."""
    for base in (ast.unparse(b).split(".")[-1] for b in node.bases):
        known = index.get(base, {})
        for method in node.body:
            if isinstance(method, FunctionNode) and method.name in known:
                base_path, base_node = known[method.name]
                yield base, method, base_path, base_node


def lsp(module: Module, index: dict) -> list[Candidate]:
    found = []
    for name, node, _ in _scopes(module.tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base, method, base_path, base_node in _overrides(node, index):
            if _breaks_contract(method, base_node):
                hint = (
                    f"Sobrescribe `{base}.{method.name}` ({base_path}:{base_node.lineno}), "
                    f"firma base: `{ast.unparse(base_node.args)}`."
                )
                symbol = f"{name}.{method.name}"
                found.append(
                    _candidate("design.lsp.contract-break", module, method, symbol, hint, weight=2)
                )
    return found


def thin_entrypoints(module: Module) -> list[Candidate]:
    found = []
    for name, node, _ in _functions(module):
        decorators = {
            ast.unparse(d.func if isinstance(d, ast.Call) else d).split(".")[-1]
            for d in node.decorator_list
        }
        size = logical_lines(node, module.code)
        if decorators & ENTRYPOINT_DECORATORS and size >= 12:
            found.append(
                _candidate(
                    "design.thin-entrypoints",
                    module,
                    node,
                    name,
                    f"Punto de entrada de {size} líneas lógicas.",
                )
            )
    return found


def _env_reads(node: ast.AST) -> int:
    text = [ast.unparse(n) for n in ast.walk(node) if isinstance(n, (ast.Call, ast.Subscript))]
    return sum(
        1 for t in text if t.startswith(("os.getenv(", "os.environ.get(", "os.environ[", "getenv("))
    )


def startup_validation(module: Module) -> list[Candidate]:
    if is_config_module(module.path):
        return []
    return [
        _candidate(
            "config.startup-validation",
            module,
            node,
            name,
            f"Lee variables de entorno en tiempo de ejecución ({reads} lecturas).",
            weight=reads,
        )
        for name, node, _ in _functions(module)
        if (reads := _env_reads(node))
    ]


def _unretried_network_calls(node: FunctionNode) -> list[str]:
    decorators = " ".join(ast.unparse(d) for d in node.decorator_list).lower()
    if "retry" in decorators or "backoff" in decorators or "sleep" in ast.unparse(node):
        return []
    return [
        f"{r}.{c}"
        for r, c in map(_call_name, _calls(node))
        if c in HTTP_METHODS and HTTP_RECEIVERS.search(r)
    ]


def retry_backoff(module: Module) -> list[Candidate]:
    return _per_function(
        "resilience.retry-backoff",
        module,
        _unretried_network_calls,
        lambda calls: f"Llamadas de red sin reintento: {_quoted(sorted(set(calls))[:3])}.",
    )


def _with_calls(node: ast.AST) -> set[int]:
    return {
        id(item.context_expr)
        for n in ast.walk(node)
        if isinstance(n, (ast.With, ast.AsyncWith))
        for item in n.items
    }


def _unmanaged_resources(node: FunctionNode) -> list[str]:
    """Recursos abiertos que ni se gestionan con `with` ni se devuelven al llamador."""
    returned = {id(n.value) for n in ast.walk(node) if isinstance(n, ast.Return) and n.value}
    skip = _with_calls(node) | returned
    return [
        f"{r + '.' if r else ''}{c}"
        for call in _calls(node)
        if id(call) not in skip
        for r, c in [_call_name(call)]
        if c in RESOURCE_OPENERS
    ]


def resource_release(module: Module) -> list[Candidate]:
    return _per_function(
        "resilience.resource-release",
        module,
        _unmanaged_resources,
        lambda opened: f"Recurso abierto fuera de `with`: {_quoted(sorted(set(opened)))}.",
    )


def _llm_calls(node: ast.AST) -> list[ast.Call]:
    return [
        c
        for c in _calls(node)
        for r, n in [_call_name(c)]
        if LLM_CALL.match(n) and LLM_RECEIVER.search(r)
    ]


def _sinks_near_llm(node: FunctionNode) -> list[str]:
    if not _llm_calls(node):
        return []
    return [
        n
        for r, n in map(_call_name, _calls(node))
        if n in {"eval", "exec"} or (n in SINK_ATTRS and r)
    ]


def output_to_sink(module: Module) -> list[Candidate]:
    return _per_function(
        "llm.output-to-sink",
        module,
        _sinks_near_llm,
        lambda sinks: (
            f"Llamada a LLM y sumidero en la misma función: {_quoted(sorted(set(sinks)))}."
        ),
    )


def _prompt_fstring(node: ast.AST) -> tuple[str, ast.JoinedStr] | None:
    """(variable, f-string) si el nodo asigna un f-string a una variable con nombre de prompt."""
    if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(
        node.value, ast.JoinedStr
    ):
        return None
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names = [ast.unparse(t) for t in targets]
    return (names[0], node.value) if any(PROMPT_NAME.search(n) for n in names) else None


def _secret_interpolations(fstring: ast.JoinedStr) -> list[str]:
    names = {ast.unparse(v.value) for v in fstring.values if isinstance(v, ast.FormattedValue)}
    return sorted(n for n in names if SECRET_NAME.search(n) or "environ" in n or "getenv" in n)


def secrets_in_prompt(module: Module) -> list[Candidate]:
    found = []
    for node in ast.walk(module.tree):
        prompt = _prompt_fstring(node)
        suspicious = _secret_interpolations(prompt[1]) if prompt else []
        if suspicious:
            hint = f"Prompt interpolado con: {_quoted(suspicious)}."
            found.append(
                _candidate(
                    "llm.secrets-in-prompt", module, node, prompt[0], hint, weight=len(suspicious)
                )
            )
    return found


def _unbounded_llm_calls(node: FunctionNode) -> list[ast.Call]:
    return [c for c in _llm_calls(node) if not {k.arg for k in c.keywords} & LIMIT_KEYWORDS]


def unbounded_consumption(module: Module) -> list[Candidate]:
    return _per_function(
        "llm.unbounded-consumption",
        module,
        _unbounded_llm_calls,
        lambda calls: f"{len(calls)} llamada(s) a LLM sin `max_tokens`.",
    )


SELECTORS: dict[str, Callable[[Module], list[Candidate]]] = {
    "design.srp": srp,
    "design.dip.direct-instantiation": dip,
    "design.ocp.conditional-dispatch": ocp,
    "design.isp.fat-interface": isp,
    "design.thin-entrypoints": thin_entrypoints,
    "config.startup-validation": startup_validation,
    "resilience.retry-backoff": retry_backoff,
    "resilience.resource-release": resource_release,
    "llm.output-to-sink": output_to_sink,
    "llm.secrets-in-prompt": secrets_in_prompt,
    "llm.unbounded-consumption": unbounded_consumption,
}


def load_modules(root: Path, files: list[str]) -> list[Module]:
    modules = []
    for rel in files:
        if not rel.endswith(".py") or is_test_file(rel):
            continue
        source = (root / rel).read_text(encoding="utf-8", errors="replace")
        try:
            modules.append(Module(path=rel, tree=ast.parse(source), code=code_lines(source)))
        except (SyntaxError, ValueError):
            continue
    return modules


def select_candidates(
    root: Path, files: list[str], rule_ids: list[str], max_per_rule: int
) -> dict[str, list[Candidate]]:
    """Candidatos por regla, ordenados (peso desc, ruta, línea) y recortados al tope."""
    modules = load_modules(root, files)
    index = lsp_index(modules) if "design.lsp.contract-break" in rule_ids else {}
    result = {}
    for rule_id in sorted(rule_ids):
        found = []
        for module in modules:
            if rule_id == "design.lsp.contract-break":
                found += lsp(module, index)
            elif rule_id in SELECTORS:
                found += SELECTORS[rule_id](module)
        found.sort(key=lambda c: (-c.weight, c.path, c.start_line))
        result[rule_id] = found[:max_per_rule]
    return result
