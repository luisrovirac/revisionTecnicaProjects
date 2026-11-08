"""CLI y composición raíz: el único lugar donde se ensamblan las implementaciones concretas."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from tec_review import __version__
from tec_review.config import ConfigError, Settings, load_settings
from tec_review.facts.adapters.ruff import RuffAnalyzer
from tec_review.facts.adapters.secureprojects import SecureProjectsAnalyzer
from tec_review.facts.inventory import PathGuard, PathGuardError
from tec_review.domain.models import ToolRun
from tec_review.domain.ports import AnalyzerResult
from tec_review.facts.coverage import CoverageAnalyzer
from tec_review.facts.duplication import DuplicationAnalyzer
from tec_review.facts.paths import PathRulesAnalyzer
from tec_review.facts.patterns import PatternAnalyzer
from tec_review.facts.python_graph import PythonGraphAnalyzer
from tec_review.facts.python_ast import PythonAstAnalyzer
from tec_review.facts.typescript_ast import TypeScriptAnalyzer
from tec_review.llm.router_adapter import LlmRouterAdapter
from tec_review.pipeline import Dependencies, RunState, run_pipeline
from tec_review.rules.capabilities import SANDBOX_TOOL
from tec_review.rules.catalog import Catalog, load_all_rules, load_catalog
from tec_review.sandbox.e2bcito_adapter import E2bcitoSandbox
from tec_review.telemetry.client import HttpTelemetry, NullTelemetry

app = typer.Typer(help="Auditoría técnica híbrida: hechos deterministas + interpretación verificada.",
                  no_args_is_help=True, add_completion=False)
rules_app = typer.Typer(help="Introspección del catálogo de reglas.", no_args_is_help=True)
app.add_typer(rules_app, name="rules")

DEFAULT_OUT = Path.home() / ".tec-review" / "out"
EXIT_TOOL_ERROR = 2


@app.callback()
def _configure_console() -> None:
    """Salida UTF-8 también en consolas Windows con code page heredada."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(EXIT_TOOL_ERROR)


def _prepare_out_dir(target: Path, out: Path | None, run_id: str) -> Path:
    out_dir = (out or DEFAULT_OUT) / f"{target.name}-{run_id}"
    PathGuard(target).check_writable(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    return out_dir


def _build_llm(settings: Settings, warnings: list[str]) -> LlmRouterAdapter | None:
    if not settings.use_llm:
        return None
    llm = LlmRouterAdapter(settings.llm_url, settings.llm_timeout_s, settings.llm_role,
                           settings.llm_model)
    if llm.health():
        return llm
    warnings.append(f"llm-router no responde en {settings.llm_url}: modo degradado sin LLM (I9).")
    return None


class _UnavailableAnalyzer:
    """Registra en el manifiesto un analizador pedido que no puede ejecutarse."""

    def __init__(self, name: str, detail: str) -> None:
        self.name, self.detail = name, detail

    def run(self, root, files) -> AnalyzerResult:
        return AnalyzerResult(run=ToolRun(name=self.name, status="unavailable", detail=self.detail))


def _coverage_analyzer(settings: Settings, rules: list):
    sandbox = E2bcitoSandbox()
    ok, detail = sandbox.available()
    if not ok:
        return _UnavailableAnalyzer(SANDBOX_TOOL, detail)
    return CoverageAnalyzer(rules, sandbox, critical_globs=settings.critical_modules)


def _build_dependencies(settings: Settings, catalog: Catalog, run_id: str,
                        warnings: list[str]) -> Dependencies:
    rules = list(catalog.rules.values())
    telemetry = HttpTelemetry(settings.telemetry_url, f"tec-review-{run_id}") \
        if settings.telemetry_enabled else NullTelemetry()
    analyzers = [PathRulesAnalyzer(rules), PythonAstAnalyzer(rules), TypeScriptAnalyzer(rules),
                 PatternAnalyzer(rules), PythonGraphAnalyzer(rules), DuplicationAnalyzer(rules),
                 RuffAnalyzer(rules),
                 SecureProjectsAnalyzer(settings.secureprojects_bin, settings.secureprojects_timeout_s)]
    if settings.run_tests:
        analyzers.append(_coverage_analyzer(settings, rules))
    return Dependencies(analyzers=analyzers, llm=_build_llm(settings, warnings), telemetry=telemetry)


def _summary(state: RunState) -> None:
    sc = state.scorecard
    color = {"GO": typer.colors.GREEN, "CONDITIONAL": typer.colors.YELLOW}.get(sc.verdict, typer.colors.RED)
    typer.secho(f"\nVeredicto: {sc.verdict}  |  score {sc.score}/100  |  confianza {sc.confidence} "
                f"({len(state.coverage.evaluated)}/{len(state.coverage.applicable)} reglas evaluadas)",
                fg=color, bold=True)
    typer.echo(f"Hallazgos: {len(state.findings)}  |  interpretados: {len(state.interpretations)}")
    for warning in state.warnings:
        typer.secho(f"  aviso: {warning}", fg=typer.colors.YELLOW)
    typer.echo(f"Reporte: {state.out_dir / 'report.md'}")


@app.command()
def review(
    path: Annotated[Path, typer.Argument(help="Ruta del proyecto a auditar (solo lectura).")],
    ruleset: Annotated[str, typer.Option(help="universal | devsaxaiflow")] = "universal",
    level: Annotated[str, typer.Option(help="quick | standard | deep")] = "standard",
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Solo capa determinista.")] = False,
    out: Annotated[Optional[Path],
                   typer.Option(help="Directorio de salida (fuera del proyecto).")] = None,
    budget: Annotated[Optional[int], typer.Option(help="Presupuesto de tokens por ejecución.")] = None,
    llm_url: Annotated[Optional[str], typer.Option(help="URL de llm-router.")] = None,
    llm_role: Annotated[Optional[str], typer.Option(help="Rol del catálogo de llm-router.")] = None,
    llm_model: Annotated[Optional[str], typer.Option(help="Modelo explícito (anula el rol).")] = None,
    run_tests: Annotated[bool, typer.Option("--run-tests",
                                            help="Cobertura ejecutando tests en e2bcito.")] = False,
    track_b: Annotated[bool, typer.Option("--track-b",
                                          help="Reglas de juicio (Pista B). Implícito en deep.")] = False,
    telemetry: Annotated[bool, typer.Option("--telemetry",
                                            help="Enviar eventos al servicio telemetry.")] = False,
) -> None:
    """Evalúa un proyecto y genera report.md, report.json, facts.json y manifest.json."""
    try:
        settings = load_settings(ruleset=ruleset, level=level, use_llm=not no_llm, llm_url=llm_url,
                                 llm_role=llm_role, llm_model=llm_model, token_budget=budget,
                                 telemetry_enabled=telemetry, run_tests=run_tests, track_b=track_b)
        catalog = load_catalog(settings.catalog_dir, settings.ruleset)
        target = path.resolve()
        if not target.is_dir():
            raise _fail(f"La ruta no existe o no es un directorio: {target}")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + f"-{settings.fingerprint()[:6]}"
        out_dir = _prepare_out_dir(target, out, run_id)
    except (ConfigError, ValueError, PathGuardError, FileExistsError) as exc:
        raise _fail(str(exc)) from exc
    warnings: list[str] = []
    deps = _build_dependencies(settings, catalog, run_id, warnings)
    state = RunState(settings=settings, catalog=catalog, target=target, run_id=run_id,
                     out_dir=out_dir, warnings=warnings)
    typer.echo(f"tec-review {__version__} - auditando {target}")
    _summary(run_pipeline(state, deps))


@app.command()
def doctor() -> None:
    """Muestra qué analizadores y servicios están disponibles. Nunca instala nada (I6)."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise _fail(str(exc)) from exc
    rules = load_all_rules(settings.catalog_dir)
    ruff = RuffAnalyzer(rules)
    sp = SecureProjectsAnalyzer(settings.secureprojects_bin)
    llm = LlmRouterAdapter(settings.llm_url, 5.0, settings.llm_role, settings.llm_model)
    rows = [
        ("catálogo", True, f"{len(rules)} reglas en {settings.catalog_dir}"),
        ("ruff", True, ruff.version()),
        ("secureprojects", sp.available(),
         str(settings.secureprojects_bin) if sp.available() else "define TEC_REVIEW_SECUREPROJECTS_BIN"),
        ("llm-router", llm.health(), settings.llm_url),
    ]
    for name, ok, detail in rows:
        typer.secho(f"{'OK ' if ok else 'FALTA'}  {name:<15} {detail}",
                    fg=typer.colors.GREEN if ok else typer.colors.YELLOW)


@rules_app.command("list")
def rules_list(ruleset: Annotated[str, typer.Option()] = "universal") -> None:
    """Lista las reglas activas de un ruleset."""
    catalog = load_catalog(load_settings().catalog_dir, ruleset)
    for rule in sorted(catalog.rules.values(), key=lambda r: r.id):
        severity = getattr(rule.severity, "value", rule.severity)
        typer.echo(f"{rule.id:<34} {rule.check.kind:<11} {severity:<8} {rule.title}")


@rules_app.command("show")
def rules_show(rule_id: str) -> None:
    """Muestra una regla con su cita literal y su safe_path."""
    rule = next((r for r in load_all_rules(load_settings().catalog_dir) if r.id == rule_id), None)
    if rule is None:
        raise _fail(f"Regla desconocida: {rule_id}")
    typer.echo(rule.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
