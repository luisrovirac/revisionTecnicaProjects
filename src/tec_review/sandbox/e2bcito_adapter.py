"""Adaptador de e2bcito (ADR 0004): ejecuta los tests del target dentro de un sandbox gVisor.

El SDK `e2bcito` es opcional (no está en PyPI): `pip install -e ../e2bcito/sdk/python`.
La API key se lee de E2BCITO_API_KEY y la URL de E2BCITO_BASE_URL, como hace el propio SDK.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath

from tec_review.domain.ports import SandboxError, SandboxRun

WORKDIR = "/workspace/proj"


def _sdk():
    try:
        import e2bcito  # noqa: PLC0415 - dependencia opcional, solo con --run-tests
    except ImportError as exc:
        raise SandboxError(
            "SDK e2bcito no instalado: pip install -e ../e2bcito/sdk/python") from exc
    return e2bcito


class E2bcitoSandbox:
    name = "e2bcito"

    def __init__(self, template: str = "default", ttl: str = "30m") -> None:
        self.template, self.ttl = template, ttl

    def available(self) -> tuple[bool, str]:
        if not os.environ.get("E2BCITO_API_KEY"):
            return False, "Falta E2BCITO_API_KEY."
        try:
            _sdk()
        except SandboxError as exc:
            return False, str(exc)
        return True, os.environ.get("E2BCITO_BASE_URL", "URL por defecto del SDK e2bcito")

    def execute(self, archive: bytes, script: str, fetch: list[str], timeout_s: float) -> SandboxRun:
        sdk = _sdk()
        try:
            with sdk.Sandbox.create(template=self.template, ttl=self.ttl,
                                    internet_enabled=True) as sandbox:
                sandbox.files.upload_folder(WORKDIR, archive)
                result = sandbox.exec(["bash", "-lc", script], cwd=WORKDIR, timeout=timeout_s)
                files = {path: data for path in fetch
                         if (data := self._read(sandbox, sdk, str(PurePosixPath(WORKDIR) / path)))}
        except sdk.errors.E2bcitoError as exc:
            raise SandboxError(f"e2bcito: {exc.__class__.__name__}: {exc}") from exc
        return SandboxRun(exit_code=result.exit_code, stdout=result.stdout[-4000:],
                          stderr=result.stderr[-4000:], files=files)

    @staticmethod
    def _read(sandbox, sdk, path: str) -> bytes | None:
        try:
            return sandbox.files.read(path)
        except sdk.errors.APIError:
            return None
