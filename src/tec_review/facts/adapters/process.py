"""Ejecución de herramientas externas: sin shell, UTF-8 con reemplazo, con timeout."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class ToolExecutionError(Exception):
    """La herramienta no pudo ejecutarse o terminó con error."""


def run_tool(cmd: list[str], timeout_s: float, cwd: str | None = None) -> ProcessResult:
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
