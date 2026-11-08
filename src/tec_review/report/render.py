"""Render Markdown del reporte (Jinja2). Solo presentación: no decide nada."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined

if TYPE_CHECKING:
    from tec_review.report.view import ReportView

DIMENSION_LABEL = {
    "security": "Seguridad", "testing": "Pruebas", "design": "Arquitectura y diseño",
    "maintainability": "Mantenibilidad", "config": "Configuración y observabilidad",
}
SEVERITY_LABEL = {"critical": "CRÍTICA", "high": "ALTA", "medium": "MEDIA", "low": "BAJA",
                  "info": "INFO"}
GAP_LABEL = {
    "tool_unavailable": "herramienta no disponible", "capability_missing": "evaluador pendiente",
    "parse_error": "error de parseo", "excluded": "excluida",
    "track_b_disabled": "juicio (Pista B) desactivado",
}
STATUS_LABEL = {
    "confirmed": "interpretación del modelo verificada contra el fragmento",
    "unverifiable": "el modelo no superó la verificación: se muestra la plantilla determinista",
    "skipped_budget": "sin interpretar: presupuesto de tokens agotado",
}


def md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def md_code(value: object) -> str:
    text = str(value).replace("\n", " ").strip()
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def location(view) -> str:
    loc = view.finding.location
    return f"{loc.path}:{loc.start_line}" if loc.start_line else loc.path


def _environment() -> Environment:
    env = Environment(loader=PackageLoader("tec_review.report", "templates"),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
                      keep_trailing_newline=True, autoescape=False)  # noqa: S701 - salida Markdown
    env.filters.update(cell=md_cell, code=md_code, loc=location)
    env.globals.update(DIM=DIMENSION_LABEL, SEV=SEVERITY_LABEL, GAP=GAP_LABEL, STATUS=STATUS_LABEL)
    return env


def render_markdown(view: ReportView) -> str:
    return _environment().get_template("report.md.j2").render(v=view)
