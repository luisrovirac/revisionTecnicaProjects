"""Ejecución de herramientas externas: sin shell, UTF-8 con reemplazo, con timeout."""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class ToolExecutionError(Exception):
    """La herramienta no pudo ejecutarse o terminó con error."""


def run_tool(cmd: list[str], timeout_s: float, cwd: str | None = None,
             on_stderr_line: Callable[[str], None] | None = None) -> ProcessResult:
    """Ejecuta `cmd`. Con `on_stderr_line`, cada línea de stderr se entrega en cuanto llega."""
    if on_stderr_line is not None:
        return _run_streaming(cmd, timeout_s, cwd, on_stderr_line)
    try:
        completed = subprocess.run(  # noqa: S603 - lista de argumentos, sin shell
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s, cwd=cwd, check=False, stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise ToolExecutionError(f"No se encontró el ejecutable: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(f"Timeout tras {timeout_s}s: {cmd[0]}") from exc
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def _run_streaming(cmd: list[str], timeout_s: float, cwd: str | None,
                   on_line: Callable[[str], None]) -> ProcessResult:
    try:
        proc = subprocess.Popen(  # noqa: S603 - lista de argumentos, sin shell
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise ToolExecutionError(f"No se encontró el ejecutable: {cmd[0]}") from exc
    out: list[str] = []
    err: list[str] = []

    def read_stdout() -> None:
        out.append(proc.stdout.read())

    def read_stderr() -> None:
        for line in proc.stderr:
            err.append(line)
            try:
                on_line(line.rstrip("\r\n"))
            except Exception:
                logger.debug("Fallo al notificar progreso", exc_info=True)

    readers = [threading.Thread(target=read_stdout, daemon=True),
               threading.Thread(target=read_stderr, daemon=True)]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait()
        raise ToolExecutionError(f"Timeout tras {timeout_s}s: {cmd[0]}") from exc
    for reader in readers:
        reader.join(timeout=5)
    return ProcessResult(proc.returncode, "".join(out), "".join(err))
