"""Exercise the fleet gate through actual robot processes and TCP sockets."""

import gzip
import json
from pathlib import Path
import subprocess
import sys

from pickloop.fleet_contention import evaluate


ROOT = Path(__file__).resolve().parents[1]


def test_tcp_contention_waits_for_positive_clearance(tmp_path):
    run = subprocess.run(
        [sys.executable, "-m", "pickloop.fleet_contention", "--robots", "6",
         "--tasks", "2", "--out", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=25,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["passed"] is True
    metrics = result["metrics"]
    assert metrics["worker_processes"] == 7
    assert metrics["completed_tasks"] == 12
    assert metrics["peak_queue_depth"] == metrics["fenced_waiters"] == 6
    assert metrics["peak_modeled_occupancy"] == 1
    assert metrics["unsafe_grants"] == metrics["trace_violations"] == 0
    with gzip.open(tmp_path / "events.jsonl.gz", "rt") as trace:
        events = [json.loads(line) for line in trace]
    kinds = [row["event"] for row in events]
    assert (kinds.index("owner_disconnected") < kinds.index("fenced")
            < kinds.index("stale_entry_rejected") < kinds.index("unclear_release_rejected")
            < kinds.index("reconciled"))
    assert kinds[kinds.index("owner_disconnected"):kinds.index("reconciled")].count("granted") == 0

    check = subprocess.run([sys.executable, "-m", "pickloop.fleet_contention", "--check", str(tmp_path)],
                           cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert check.returncode == 0, check.stdout + check.stderr

    # Move a real healthy grant ahead of positive clearance, preserving sequence and clock order.
    fault_fence = kinds.index("fenced")
    healthy_grant = kinds.index("granted", kinds.index("reconciled"))
    premature = events.pop(healthy_grant)
    premature["elapsed_ns"] = events[fault_fence]["elapsed_ns"]
    events.insert(fault_fence + 1, premature)
    for sequence, row in enumerate(events):
        row["seq"] = sequence
    corrupted = evaluate(events, result["config"]["robots"], 2)
    assert corrupted["unsafe_grants"] == 1
