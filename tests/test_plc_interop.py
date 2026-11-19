"""Acceptance tests for an independent loopback PLC, plus its offline gate."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "plc/run_interop.py"
RECORD = ROOT / "runs/plc-interop"


def invoke(*args):
    return subprocess.run([sys.executable, str(RUNNER), *map(str, args)],
                          capture_output=True, text=True, timeout=30)


@pytest.mark.skipif(any(importlib.util.find_spec(name) is None
                        for name in ("awlsim", "pyModbusTCP")),
                    reason="install plc/requirements.txt to run the live PLC")
def test_cpp_reconciles_a_lost_write_echo_against_an_awl_scan(tmp_path):
    output = tmp_path / "live"
    run = invoke("--out", output)
    assert run.returncode == 0, run.stderr
    rows = [json.loads(line) for line in (output / "steps.jsonl").read_text().splitlines()]
    by_name = {row["step"]: row for row in rows}
    assert by_name["reconcile_applied"]["status"]["execution_count"] == 2
    assert by_name["unknown_release"]["exit_code"] != 0
    assert by_name["hold_after_unknown"]["status"]["pressure_kpa"] == -52.3
    assert invoke("--check", output).returncode == 0


def test_checked_in_trace_satisfies_fixed_gate():
    check = invoke("--check", RECORD)
    assert check.returncode == 0, check.stderr


@pytest.mark.parametrize("corruption", ["accepted_duplicate", "pressure_word", "missing_reconnect"])
def test_offline_gate_rejects_wrong_client_state_and_wire_history(tmp_path, corruption):
    assert RECORD.is_dir(), "PLC trace missing"
    trace = tmp_path / "bad"
    shutil.copytree(RECORD, trace)
    filename = "steps.jsonl" if corruption == "accepted_duplicate" else "wire.jsonl"
    path = trace / filename
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if corruption == "accepted_duplicate":
        next(row for row in rows if row["step"] == "duplicate")["status"]["execution_count"] = 2
    if corruption == "pressure_word":
        target = next(row for row in rows if row["step"] == "feedback")
        target["response_hex"] = target["response_hex"].replace("fdf5", "020b")
    if corruption == "missing_reconnect":
        rows = [row for row in rows if row["step"] != "unknown_release" or row["request_hex"][14:16] != "03"]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = invoke("--check", trace)
    assert result.returncode != 0, result.stdout


@pytest.mark.skipif(any(importlib.util.find_spec(name) is None
                        for name in ("awlsim", "pyModbusTCP")),
                    reason="install plc/requirements.txt to run the live PLC")
def test_invalid_zero_opcode_is_rejected_at_first_scan():
    # A zero in the opcode word is still a write request. It must be
    # distinguished from an idle cycle with no request.
    sys.path.insert(0, str(ROOT / "plc"))
    try:
        from bench import bench
        from pyModbusTCP.client import ModbusClient
        with bench() as (_, relay):
            client = ModbusClient(host="127.0.0.1", port=relay.peer, unit_id=1, auto_close=True)
            assert not client.write_multiple_registers(100, [0, 4, 0, 0])
            assert client.last_except == 3
            assert client.read_holding_registers(0, 12) == [1] + [0] * 11
    finally:
        sys.path.pop(0)
