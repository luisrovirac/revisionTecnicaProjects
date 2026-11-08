"""Cobertura vía sandbox: el código del target solo se ejecuta tras el puerto (I2)."""

import io
import json
import tarfile

from conftest import ROOT, write_tree

from tec_review.domain.ports import SandboxError, SandboxRun
from tec_review.facts.coverage import COVERAGE_FILE, CoverageAnalyzer, build_archive
from tec_review.facts.inventory import build_inventory
from tec_review.rules.catalog import load_catalog

RULES = list(load_catalog(ROOT / "catalog", "universal").rules.values())
BIG = "def calcular():\n" + "".join(f"    x{i} = {i}\n" for i in range(35)) + "    return x0\n"


class FakeSandbox:
    name = "fake-sandbox"

    def __init__(self, percents=None, fail=False):
        self.percents, self.fail, self.received = percents or {}, fail, None

    def execute(self, archive, script, fetch, timeout_s):
        if self.fail:
            raise SandboxError("sin capacidad")
        self.received = archive
        payload = {"files": {p: {"summary": {"percent_covered": v}} for p, v in self.percents.items()}}
        return SandboxRun(exit_code=0, files={COVERAGE_FILE: json.dumps(payload).encode()})


def _run(tmp_path, sandbox):
    write_tree(tmp_path, {"src/motor.py": BIG, "src/mini.py": "X = 1\n",
                          "tests/test_motor.py": "def test_x():\n    assert True\n",
                          ".gitignore": ".env\n", ".env": "CLAVE=secreta\n"})
    inventory = build_inventory(tmp_path)
    return CoverageAnalyzer(RULES, sandbox).run(inventory.root, inventory.files)


def test_low_coverage_on_important_module_is_reported(tmp_path):
    result = _run(tmp_path, FakeSandbox({"src/motor.py": 42.0}))
    assert result.run.status == "ok"
    assert [(f.location.path, f.message) for f in result.facts] == [
        ("src/motor.py", "Cobertura de líneas 42% (umbral 80%).")]


def test_enough_coverage_and_small_modules_are_not_reported(tmp_path):
    assert _run(tmp_path, FakeSandbox({"src/motor.py": 91.0})).facts == []


def test_archive_contains_only_inventory_files_never_ignored_secrets(tmp_path):
    sandbox = FakeSandbox({"src/motor.py": 90.0})
    _run(tmp_path, sandbox)
    with tarfile.open(fileobj=io.BytesIO(sandbox.received), mode="r:gz") as tar:
        names = tar.getnames()
    assert ".env" not in names and "src/motor.py" in names


def test_sandbox_failure_becomes_tool_error_not_crash(tmp_path):
    result = _run(tmp_path, FakeSandbox(fail=True))
    assert result.run.status == "error" and result.facts == []


def test_build_archive_roundtrip(tmp_path):
    write_tree(tmp_path, {"a.py": "x = 1\n"})
    data = build_archive(tmp_path, ["a.py"])
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        assert tar.getnames() == ["a.py"]
