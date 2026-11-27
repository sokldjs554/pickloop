import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest


NOTEBOOK = Path(__file__).resolve().parents[1] / "docs/experiments/isaac-sim/notebook.ipynb"
CELLS = ["".join(cell["source"]) for cell in json.loads(NOTEBOOK.read_text())["cells"]
         if cell["cell_type"] == "code"]
MEASURED = {"physics_steps": 180, "passed": True, "start_z_m": 1.0,
            "final_z_m": 0.05, "final_speed_m_s": 0.0}
MARKER = "PICKLOOP_PHYSICS_RESULT " + json.dumps(MEASURED)


def run_notebook(tmp_path, monkeypatch, marker, crash):
    monkeypatch.chdir(tmp_path)
    real_run = subprocess.run
    runtime = tmp_path / ".pickloop-isaac-5.1/runtime/bin"
    runtime.mkdir(parents=True)
    (runtime / "python").symlink_to(sys.executable)
    monkeypatch.setenv("PATH", str(runtime))
    (runtime / "uv").touch(mode=0o755)
    def simulated_child(args, **kwargs):
        if "-c" in args and "SimulationApp" in args[-1]:
            # Use real stdout redirection and the OS exit status without requiring a GPU.
            program = "import os, signal, resource\nresource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n"
            if marker:
                program += f"print({marker!r}, flush=True)\n"
            if crash:
                program += "os.kill(os.getpid(), signal.SIGSEGV)\n"
            return real_run([sys.executable, "-c", program], **kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", simulated_child)
    namespace = {}
    for cell in CELLS[:-1]:
        exec(cell, namespace)
    namespace["report"]["gpu"] = {"exit_code": 0}
    exec(CELLS[-1].replace("RUN_PHYSICS = False", "RUN_PHYSICS = True")
         .replace("ACCEPT_NVIDIA_EULA = False", "ACCEPT_NVIDIA_EULA = True"), namespace)
    return json.loads((tmp_path / "pickloop-isaac-result.json").read_text())


@pytest.mark.parametrize(("marker", "crash", "expected", "measured"), [
    (MARKER, True, "run_incomplete", True),
    (None, True, "run_incomplete", False),
    (MARKER, False, "physics_passed", True),
    (MARKER + "\n" + MARKER, False, "run_incomplete", False),
])
def test_isaac_measurements_survive_process_exit(tmp_path, monkeypatch, marker, crash, expected, measured):
    result = run_notebook(tmp_path, monkeypatch, marker, crash)
    assert result["status"] == expected
    assert result.get("physics") == (MEASURED if measured else None)
    assert result["physics_exit_code"] == (-signal.SIGSEGV if crash else 0)


def test_recovery_reads_previous_run_without_changing_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "pickloop-isaac.log"
    report = tmp_path / "pickloop-isaac-result.json"
    old_log = MARKER + "\nFatal Python error: Segmentation fault\n"
    old_report = '{"status":"run_incomplete"}'
    log.write_text(old_log)
    report.write_text(old_report)
    namespace = {}
    for cell in CELLS[:-1]:
        exec(cell, namespace)
    evidence = namespace["read_physics_log"](log)
    assert evidence["physics"] == MEASURED
    assert "Segmentation fault" in evidence["fatal_error"]
    assert (log.read_text(), report.read_text()) == (old_log, old_report)
