"""Progreso visible en consola: en qué paso va la ejecución, qué hace y cuánto lleva.

Todo se escribe en stderr para no mezclarse con el resumen final (stdout).
- Terminal interactiva: barra en vivo (rich) con spinner, paso N/M, detalle, % y tiempo.
- Sin terminal (pipes, CI, tests): una línea de texto plano por evento.

Niveles de detalle, de mayor a menor:
  stage_start/stage_end  paso del pipeline        "[2/9] Ejecutando analizadores"
  step                   elemento dentro del paso "8/8 secureprojects"
  activity               qué hace ese elemento    "4/6 · en curso: trivy, semgrep"
Si nada cambia durante un rato, un latido indica qué se está esperando y cuánto lleva.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Self, TextIO

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

_LEVEL_PREFIX = {"info": "  ", "detail": "      ", "warn": "  aviso: "}
_LEVEL_STYLE = {"info": "cyan", "detail": "dim", "warn": "yellow"}
_LEVEL_COLOR = {"info": typer.colors.CYAN, "detail": None, "warn": typer.colors.YELLOW}
HEARTBEAT_S = 15.0  # sin novedades durante este tiempo -> se avisa de que sigue trabajando
_MAX_ACTIVITY = 70


class NullProgress:
    """No muestra nada (`--quiet` y tests)."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def stage_start(self, index: int, total: int, name: str, label: str) -> None:
        return None

    def step(self, detail: str, done: int | None = None, total: int | None = None) -> None:
        return None

    def activity(self, detail: str, done: int | None = None, total: int | None = None) -> None:
        return None

    def stage_end(self, name: str, duration_ms: int, summary: str = "") -> None:
        return None

    def note(self, message: str, level: str = "info") -> None:
        return None


class ConsoleProgress:
    """Progreso para humanos. Usar como context manager para cerrar la barra siempre."""

    def __init__(self, live: bool | None = None, stream: TextIO | None = None,
                 heartbeat_s: float = HEARTBEAT_S) -> None:
        self._stream = stream
        self._live = _is_terminal(stream or sys.stderr) if live is None else live
        self._heartbeat_s = heartbeat_s
        self._bar: Progress | None = None
        self._task = None
        self._item = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._beat: threading.Thread | None = None
        self._index, self._total, self._label = 0, 1, ""
        self._step, self._step_frac = "", 0.0
        self._step_span = 0.0  # fracción del paso que ocupa el elemento actual
        self._activity = ""
        self._step_since = self._changed_at = self._last_output = time.perf_counter()

    # -- ciclo de vida ------------------------------------------------------------------
    def __enter__(self) -> Self:
        if self._live:
            console = Console(file=self._stream, stderr=self._stream is None)
            self._bar = Progress(SpinnerColumn(), TextColumn("{task.description}"),
                                 BarColumn(bar_width=20), TaskProgressColumn(),
                                 TimeElapsedColumn(), _WaitingColumn(self), console=console,
                                 transient=True)
            self._bar.start()
            self._task = self._bar.add_task("Preparando…", total=100)
            # Segunda fila: el elemento en curso (analizador, hallazgo…) con su propio avance.
            self._item = self._bar.add_task("", total=None, visible=False)
        elif self._heartbeat_s > 0:
            self._beat = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._beat.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._beat is not None:
            self._beat.join(timeout=2)
        if self._bar is not None:
            self._bar.stop()
            self._bar = None

    # -- eventos ------------------------------------------------------------------------
    def stage_start(self, index: int, total: int, name: str, label: str) -> None:
        with self._lock:
            self._index, self._total, self._label = index, total, label
            self._set_step("", 0.0, 1.0)
            if self._bar is not None:
                self._refresh()
            else:
                self._echo(f"[{index}/{total}] {label}…", bold=True)

    def step(self, detail: str, done: int | None = None, total: int | None = None) -> None:
        counter = _counter(done, total)
        with self._lock:
            if done is not None and total:
                self._set_step(f"{counter}{detail}", (done - 1) / total, 1 / total)
            else:
                self._set_step(detail, self._step_frac, 0.0)
            if self._bar is not None:
                self._bar.reset(self._item, total=None, completed=0, visible=True,
                                description=_escape(f"  └ {detail}"))
                self._refresh()
            else:
                self._echo(f"    → {counter}{detail}…")

    def activity(self, detail: str, done: int | None = None, total: int | None = None) -> None:
        """Qué hace ahora el elemento en curso; no imprime línea propia en modo texto."""
        with self._lock:
            text = f"{_counter(done, total)}{detail}"
            if text != self._activity:
                self._activity, self._changed_at = text, time.perf_counter()
            if self._bar is None:
                return
            item = f"  └ {self._step_name()} · {_short(text)}"
            if done is not None and total:
                self._bar.update(self._item, total=total, completed=min(done, total),
                                 description=_escape(item))
                self._refresh(self._step_frac + min(done / total, 1.0) * self._step_span)
            else:
                self._bar.update(self._item, description=_escape(item))
                self._refresh()

    def stage_end(self, name: str, duration_ms: int, summary: str = "") -> None:
        tail = f" — {summary}" if summary else ""
        line = f"✓ [{self._index}/{self._total}] {self._label}{tail} ({_duration(duration_ms / 1000)})"
        with self._lock:
            self._set_step("", 1.0, 0.0)
            if self._bar is not None:
                self._refresh(1.0)
                self._bar.console.print(line, style="green", markup=False, highlight=False)
            else:
                pct = round(100 * self._index / self._total)
                self._echo(f"{line} · {pct}%", color=typer.colors.GREEN)

    def note(self, message: str, level: str = "info") -> None:
        text = f"{_LEVEL_PREFIX.get(level, '  ')}{message}"
        with self._lock:
            if self._bar is not None:
                self._bar.console.print(text, style=_LEVEL_STYLE.get(level, ""), markup=False,
                                        highlight=False)
            else:
                self._echo(text, color=_LEVEL_COLOR.get(level))

    # -- latido -------------------------------------------------------------------------
    def waiting_for(self) -> float:
        """Segundos sin ningún cambio visible en el paso actual."""
        return time.perf_counter() - max(self._changed_at, self._step_since)

    def current(self) -> str:
        parts = [p for p in (f"[{self._index}/{self._total}] {self._label}", self._step,
                             _short(self._activity)) if p]
        return " · ".join(parts)

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(1.0):
            with self._lock:
                quiet_for = time.perf_counter() - self._last_output
                if self._index and quiet_for >= self._heartbeat_s:
                    in_step = time.perf_counter() - self._step_since
                    self._echo(f"      … sigue trabajando: {self.current()} "
                               f"(lleva {_duration(in_step)})")

    # -- internos -----------------------------------------------------------------------
    def _set_step(self, text: str, frac: float, span: float) -> None:
        self._step, self._step_frac, self._step_span = text, frac, span
        self._activity = ""
        self._step_since = self._changed_at = time.perf_counter()
        if self._bar is not None and not text:
            self._bar.update(self._item, visible=False)

    def _step_name(self) -> str:
        """Nombre del elemento sin el contador "3/8 "."""
        head, _, rest = self._step.partition(" ")
        return rest if rest and "/" in head and head.replace("/", "").isdigit() else self._step

    def _refresh(self, fraction: float | None = None) -> None:
        frac = self._step_frac if fraction is None else fraction
        done_stages = max(self._index - 1, 0) + min(max(frac, 0.0), 1.0)
        stage = f"[{self._index}/{self._total}] {self._label}"
        step = f" · {self._step}" if self._step else ""
        self._bar.update(self._task, description=_escape(stage + step),
                         completed=100 * done_stages / self._total)

    def _echo(self, text: str, color: str | None = None, bold: bool = False) -> None:
        typer.secho(text, fg=color, bold=bold, err=self._stream is None, file=self._stream)
        self._last_output = time.perf_counter()


class _WaitingColumn(ProgressColumn):
    """Muestra cuánto lleva el paso sin novedades, para que se vea que no está colgado."""

    def __init__(self, owner: ConsoleProgress) -> None:
        super().__init__()
        self._owner = owner

    def render(self, task) -> Text:
        if task.id != self._owner._item:
            return Text("")
        waiting = self._owner.waiting_for()
        if waiting < 5:
            return Text("")
        return Text(f"esperando {_duration(waiting)}", style="yellow")


def _counter(done: int | None, total: int | None) -> str:
    return f"{done}/{total} " if done is not None and total else ""


def _is_terminal(stream: TextIO) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s"


def _short(text: str) -> str:
    return text if len(text) <= _MAX_ACTIVITY else text[: _MAX_ACTIVITY - 1] + "…"


def _escape(text: str) -> str:
    """Evita que rutas o ids con corchetes se interpreten como markup de rich."""
    return text.replace("[", "\\[")
