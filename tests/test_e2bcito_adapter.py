"""Adaptador de e2bcito con un SDK falso: disponibilidad, rutas y mapeo de errores."""

import sys
import types

import pytest

from tec_review.domain.ports import SandboxError
from tec_review.sandbox.e2bcito_adapter import WORKDIR, E2bcitoSandbox


class E2bcitoError(Exception):
    pass


class APIError(E2bcitoError):
    pass


class FakeFiles:
    def __init__(self, stored):
        self.stored, self.uploaded = stored, None

    def upload_folder(self, dest, archive):
        self.uploaded = (dest, archive)

    def read(self, path):
        if path not in self.stored:
            raise APIError(f"no existe {path}")
        return self.stored[path]


class FakeSandbox:
    def __init__(self, stored, exec_error=None):
        self.files, self.exec_error, self.calls = FakeFiles(stored), exec_error, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec(self, cmd, cwd, timeout):
        self.calls.append((cmd, cwd, timeout))
        if self.exec_error:
            raise self.exec_error
        return types.SimpleNamespace(exit_code=3, stdout="o" * 5000, stderr="e")


def _install_sdk(monkeypatch, sandbox):
    sdk = types.ModuleType("e2bcito")
    sdk.Sandbox = types.SimpleNamespace(create=lambda **kwargs: sandbox)
    sdk.errors = types.SimpleNamespace(E2bcitoError=E2bcitoError, APIError=APIError)
    monkeypatch.setitem(sys.modules, "e2bcito", sdk)


def test_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv("E2BCITO_API_KEY", raising=False)
    ok, detail = E2bcitoSandbox().available()
    assert not ok and "E2BCITO_API_KEY" in detail


def test_unavailable_without_sdk(monkeypatch):
    monkeypatch.setenv("E2BCITO_API_KEY", "k")
    monkeypatch.setitem(sys.modules, "e2bcito", None)  # import e2bcito -> ImportError
    ok, detail = E2bcitoSandbox().available()
    assert not ok and "SDK e2bcito" in detail


def test_available_with_key_and_sdk(monkeypatch):
    monkeypatch.setenv("E2BCITO_API_KEY", "k")
    monkeypatch.setenv("E2BCITO_BASE_URL", "http://sandbox.local")
    _install_sdk(monkeypatch, FakeSandbox({}))
    assert E2bcitoSandbox().available() == (True, "http://sandbox.local")


def test_execute_resolves_fetch_paths_in_workdir(monkeypatch):
    sandbox = FakeSandbox({f"{WORKDIR}/cov.json": b"{}"})
    _install_sdk(monkeypatch, sandbox)
    run = E2bcitoSandbox().execute(b"tar", "pytest", ["cov.json", "falta.json"], 60)
    assert sandbox.files.uploaded == (WORKDIR, b"tar")
    assert sandbox.calls == [(["bash", "-lc", "pytest"], WORKDIR, 60)]
    assert run.files == {"cov.json": b"{}"}  # el archivo que falta no rompe la ejecución
    assert run.exit_code == 3 and len(run.stdout) == 4000


def test_execute_maps_sdk_errors_to_sandbox_error(monkeypatch):
    _install_sdk(monkeypatch, FakeSandbox({}, exec_error=E2bcitoError("caído")))
    with pytest.raises(SandboxError, match="caído"):
        E2bcitoSandbox().execute(b"tar", "pytest", [], 60)
