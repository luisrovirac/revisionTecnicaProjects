"""Progreso visible: el usuario ve en qué paso va la ejecución y qué está haciendo."""

import io
import shutil

from conftest import FIXTURES, ROOT, deterministic_analyzers
from typer.testing import CliRunner

from tec_review.cli import app
from tec_review.config import load_settings
from tec_review.pipeline import NODES, Dependencies, RunState, run_pipeline
from tec_review.progress import ConsoleProgress
from tec_review.rules.catalog import load_catalog
from tec_review.telemetry.client import NullTelemetry


class RecordingProgress:
    def __init__(self):
        self.events = []

    def stage_start(self, index, total, name, label):
        self.events.append(("start", index, total, name))

    def step(self, detail, done=None, total=None):
        self.events.append(("step", detail, done, total))

    def activity(self, detail, done=None, total=None):
        self.events.append(("activity", detail, done, total))

    def stage_end(self, name, duration_ms, summary=""):
        self.events.append(("end", name, summary))

    def note(self, message, level="info"):
        self.events.append(("note", message, level))


def _run(tmp_path, progress):
    target = shutil.copytree(FIXTURES / "repos" / "seeded", tmp_path / "seeded")
    settings = load_settings(use_llm=False, ruleset="devsaxaiflow")
    catalog = load_catalog(ROOT / "catalog", settings.ruleset)
    (tmp_path / "out").mkdir()
    analyzers = deterministic_analyzers(catalog)
    deps = Dependencies(analyzers=analyzers, llm=None, telemetry=NullTelemetry(),
                        progress=progress)
    state = RunState(settings=settings, catalog=catalog, target=target, run_id="r",
                     out_dir=tmp_path / "out")
    run_pipeline(state, deps)
    return analyzers


def test_every_stage_is_announced_in_order_with_summary(tmp_path):
    progress = RecordingProgress()
    _run(tmp_path, progress)
    names = [n for n, _ in NODES]
    starts = [e for e in progress.events if e[0] == "start"]
    ends = [e for e in progress.events if e[0] == "end"]
    assert [e[3] for e in starts] == names
    assert [e[1:3] for e in starts] == [(i, len(names)) for i in range(1, len(names) + 1)]
    assert [e[1] for e in ends] == names
    assert all(e[2] for e in ends)  # cada paso dice qué produjo
    assert {e[1]: e[2] for e in ends}["interpret"] == "omitido: sin LLM"


def test_each_analyzer_is_reported_as_a_step(tmp_path):
    progress = RecordingProgress()
    analyzers = _run(tmp_path, progress)
    steps = [e for e in progress.events if e[0] == "step"]
    assert [(s[1], s[2], s[3]) for s in steps] == [
        (a.name, i, len(analyzers)) for i, a in enumerate(analyzers, start=1)]


def test_plain_mode_prints_steps_and_percent(tmp_path):
    out = io.StringIO()
    with ConsoleProgress(live=False, stream=out) as progress:
        progress.stage_start(2, 4, "collect", "Ejecutando analizadores")
        progress.step("ruff", 1, 3)
        progress.stage_end("collect", 1500, "3 analizadores")
        progress.note("algo falló", level="warn")
    text = out.getvalue()
    assert "[2/4] Ejecutando analizadores…" in text
    assert "1/3 ruff" in text
    assert "✓ [2/4] Ejecutando analizadores — 3 analizadores (1.5 s) · 50%" in text
    assert "aviso: algo falló" in text
    assert "\x1b[" not in text  # sin códigos de control fuera de una terminal


def test_live_mode_runs_without_errors():
    out = io.StringIO()
    with ConsoleProgress(live=True, stream=out) as progress:
        progress.stage_start(1, 2, "inventory", "Inventariando [archivos]")
        progress.step("src/[x].py", 1, 2)
        progress.stage_end("inventory", 10, "2 archivos")
    assert "Inventariando [archivos]" in out.getvalue()


def test_cli_shows_progress_and_quiet_hides_it(tmp_path):
    runner = CliRunner()
    target = str(FIXTURES / "repos" / "seeded")
    shown = runner.invoke(app, ["review", target, "--no-llm", "--out", str(tmp_path / "a")])
    assert shown.exit_code == 0, shown.output
    for i in range(1, len(NODES) + 1):
        assert f"[{i}/{len(NODES)}]" in shown.output
    assert "Veredicto:" in shown.output
    quiet = runner.invoke(app, ["review", target, "--no-llm", "--quiet",
                                "--out", str(tmp_path / "b")])
    assert quiet.exit_code == 0, quiet.output
    assert "[1/" not in quiet.output
    assert "Veredicto:" in quiet.output


def test_run_tool_streams_stderr_lines_while_running():
    import sys

    from tec_review.facts.adapters.process import run_tool

    script = ("import sys, time\n"
              "for i in range(3):\n"
              "    print(f'paso {i}', file=sys.stderr, flush=True)\n"
              "    time.sleep(0.05)\n"
              "print('resultado')\n")
    seen = []
    result = run_tool([sys.executable, "-c", script], timeout_s=30, on_stderr_line=seen.append)
    assert seen == ["paso 0", "paso 1", "paso 2"]
    assert result.stdout.strip() == "resultado"
    assert result.returncode == 0


def test_secureprojects_log_becomes_live_progress():
    from tec_review.facts.adapters.secureprojects import ScanProgress

    progress = RecordingProgress()
    scan = ScanProgress(progress)
    for line in [
        "[00:00] Ejecutando 3 de 17 analizadores: native-sast, trivy, semgrep",
        "[00:00]   -> trivy: iniciando",
        "[00:00]   -> semgrep: iniciando",
        "[00:00]   [1/3] native-sast: ok, 0 hallazgo(s) en 0s",
        "[00:04]   [2/3] semgrep: ok, 2 hallazgo(s) en 4.7s",
        '{"level":"WARN","msg":"tool failed","scanner":"trivy"}',
        "report written: C:/tmp/x.json",
    ]:
        scan.feed(line)
    assert scan.running == ["trivy"]
    assert (scan.done, scan.total) == (2, 3)
    notes = [e[1] for e in progress.events if e[0] == "note"]
    assert "secureprojects [00:04] [2/3] semgrep: ok, 2 hallazgo(s) en 4.7s" in notes
    assert ("note", "secureprojects trivy: tool failed", "warn") in progress.events
    assert not any("report written" in n for n in notes)
    activities = [e for e in progress.events if e[0] == "activity"]
    assert activities[-1] == ("activity", "en curso: trivy", 2, 3)


def test_plain_heartbeat_says_what_is_still_running():
    import time

    out = io.StringIO()
    with ConsoleProgress(live=False, stream=out, heartbeat_s=0.5) as progress:
        progress.stage_start(2, 9, "collect", "Ejecutando analizadores")
        progress.step("secureprojects", 8, 8)
        progress.activity("en curso: trivy")
        time.sleep(1.8)
    text = out.getvalue()
    assert "… sigue trabajando: [2/9] Ejecutando analizadores · 8/8 secureprojects · " \
           "en curso: trivy (lleva" in text
