"""Run the loopback PLC bench or verify its three recorded traces offline."""
import argparse
import hashlib
import json
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "plc"
GRIP = 2147483681
RELEASE = GRIP + 1

# The expectations are fixed here. Each status tuple encodes ID, valve,
# pressure, attachment, application count, and cancellation.
IDLE = (0, False, 0, False, 0, False)
ENERGIZED = (GRIP, True, 0, False, 1, False)
HELD = (GRIP, True, -52.3, True, 1, False)
FENCED = (GRIP, True, -52.3, True, 1, True)
SUPPORTED = (GRIP, True, 0, False, 1, True)
OPEN = (RELEASE, False, 0, False, 2, False)
CONFLICT = "Modbus exception 3"
UNKNOWN = "uncertain command: reconcile the same ID; do not use a new ID"

# step, invocation, expected observed PLC state, expected client stderr, transport fault
CASES = (
    ("initial", ("status",), IDLE, "", None),
    ("energize", ("command", GRIP, 1), ENERGIZED, "", None),
    ("feedback", ("status",), HELD, "", None),
    ("duplicate", ("command", GRIP, 1), HELD, "", None),
    ("conflict", ("command", GRIP, 0), HELD, CONFLICT, None),
    ("cancel_hold", ("cancel", GRIP), FENCED, "", None),
    ("fenced_replay", ("command", GRIP, 1), FENCED, CONFLICT, None),
    ("unknown_release", ("command", RELEASE, 0), FENCED, UNKNOWN, "drop_before_forward"),
    ("hold_after_unknown", ("status",), FENCED, "", None),
    ("supported_fixture", ("status",), SUPPORTED, "", None),
    ("reconcile_applied", ("command", RELEASE, 0), OPEN, "", "drop_after_response"),
    ("stale", ("command", GRIP, 1), OPEN, CONFLICT, None),
    ("final", ("status",), OPEN, "", None),
)


def snapshot(state):
    ack, valve, pressure, attached, count, cancelled = state
    return {"ack_id": ack, "valve": valve, "pressure_kpa": pressure,
            "attached": attached, "error": "none", "execution_count": count,
            "max_command_id": ack, "cancelled": cancelled}


def registers(state):
    ack, valve, pressure, attached, count, cancelled = state
    return (1, ack >> 16, ack & 65535, int(valve), round(pressure * 10) & 65535,
            int(attached), 0, count >> 16, count & 65535, ack >> 16, ack & 65535,
            int(cancelled))


def frame(txn, pdu):
    return struct.pack(">HHHB", txn, 0, len(pdu) + 1, 1) + pdu


def check(ok, message):
    if not ok:
        raise ValueError(message)


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def verify(output):
    steps = read_rows(output / "steps.jsonl")
    wire = read_rows(output / "wire.jsonl")
    scans = read_rows(output / "scans.jsonl")
    check([s["step"] for s in steps] == [case[0] for case in CASES], "scenario order")
    check(all(w["connection"] == n and w["service_ns"] > 0
              for n, w in enumerate(wire, 1)), "connection history or timing")
    check(all(s["scan"] == n and s["execution_ns"] > 0 and len(s["output"]) == 13
              for n, s in enumerate(scans, 1)), "scan history")
    intervals = [(b["at_ns"] - a["at_ns"]) / 1e6 for a, b in zip(scans, scans[1:])]
    check(intervals and min(intervals) > 0, "scan clock")
    actual_commands = [(s["command"], s["output"]) for s in scans if s["command"] is not None]
    expected_commands = []
    cursor = 0
    for row, (step, args, state, error, fault) in zip(steps, CASES):
        label = f"{step} does not meet the fixed acceptance criteria"
        check(row["args"] == list(args) and row["elapsed_ns"] > 0, label)
        check(row["exit_code"] == (1 if error else 0) and row["stderr"] == error, label)
        check(row["status"] == (None if error else snapshot(state)), label)

        # Derive the exact sequence of expected FC16/FC03 frames independently
        # of the C++ client and pyModbusTCP. Transaction IDs restart per process.
        expected = []
        if args[0] != "status":
            command_id = args[1]
            words = [command_id >> 16, command_id & 65535,
                     2 if args[0] == "cancel" else 1, args[2] if len(args) > 2 else 0]
            command = bytes.fromhex("100064000408") + struct.pack(">4H", *words)
            result = bytes.fromhex("9003" if error == CONFLICT else "1000640004")
            expected.append((command, result, fault))
            if fault != "drop_before_forward":
                expected_commands.append((words, [*registers(state), 3 if error == CONFLICT else 0]))
        if error != CONFLICT:
            read = bytes.fromhex("030000000c")
            result = bytes.fromhex("0318") + struct.pack(">12H", *registers(state))
            expected.append((read, result, None))
        for txn, (request, response, injected) in enumerate(expected, 1):
            check(cursor < len(wire), label)
            event = wire[cursor]
            cursor += 1
            forwarded = injected != "drop_before_forward"
            check(event["step"] == step and event["fault"] == injected, label)
            check(event["forwarded"] is forwarded and event["delivered"] is (injected is None), label)
            check(event["request_hex"] == frame(txn, request).hex(), label)
            check(event["response_hex"] == (frame(txn, response).hex() if forwarded else ""), label)
    check(cursor == len(wire), "unexpected RPC after scenario")
    check(actual_commands == expected_commands, "PLC input or output differs from wire contract")
    for scan in scans:
        check(scan["output"][4] == (scan["pressure_deci_kpa"] & 65535)
              and scan["output"][5] == scan["attached_input"], "feedback image mismatch")

    timings = [s["elapsed_ns"] / 1e6 for s in steps]
    return {"outcome": "pass", "steps": len(steps), "tcp_connections": len(wire),
            "plc_command_scans": len(actual_commands), "scans_recorded": len(scans),
            "valve_applications": actual_commands[-1][1][8],
            "final_id": steps[-1]["status"]["ack_id"],
            "scan_interval_ms_median": round(statistics.median(intervals), 3),
            "scan_interval_ms_max": round(max(intervals), 3),
            "client_process_ms_median": round(statistics.median(timings), 3),
            "client_process_ms_max": round(max(timings), 3)}


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))


def measure(output):
    from bench import bench

    cpp = ROOT / "cpp/modbus_client.cpp"
    with tempfile.TemporaryDirectory() as work:
        binary = Path(work) / "modbus_client"
        flags = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"]
        subprocess.run(["g++", *flags, str(cpp), "-o", str(binary)], check=True)
        with bench() as (station, relay):
            steps = []
            for step, args, _, _, fault in CASES:
                if step == "feedback":
                    station.feedback(-523, True)
                elif step == "supported_fixture":
                    station.feedback(0, False)
                relay.step, relay.fault = step, fault
                start = time.monotonic_ns()
                process = subprocess.run([str(binary), "127.0.0.1", str(relay.server_address[1]),
                                          *map(str, args)], capture_output=True, text=True, timeout=2)
                steps.append({"step": step, "args": args, "exit_code": process.returncode,
                              "elapsed_ns": time.monotonic_ns() - start,
                              "status": json.loads(process.stdout) if process.stdout else None,
                              "stderr": process.stderr.strip()})
            wire = list(relay.wire)
            with station.cv:
                scans = list(station.scans)
        output.mkdir(parents=True, exist_ok=False)
        write_rows(output / "steps.jsonl", steps)
        write_rows(output / "wire.jsonl", wire)
        write_rows(output / "scans.jsonl", scans)
        metrics = verify(output)
        environment = {"awlsim": version("awlsim"), "pyModbusTCP": version("pyModbusTCP"),
                       "python": sys.version.split()[0], "compile_flags": flags,
                       "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
                       "scan_target_ms": 10,
                       "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (cpp, HERE / "pickloop.awl", HERE / "bench.py", Path(__file__))}}
        (output / "summary.json").write_text(json.dumps({"environment": environment, "result": metrics},
                                                        indent=2) + "\n")
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=Path, help="fresh directory for a live run")
    group.add_argument("--check", type=Path, help="directory containing an existing run")
    args = parser.parse_args()
    if args.check:
        result = verify(args.check)
        summary = json.loads((args.check / "summary.json").read_text())
        check(result == summary["result"], "summary differs from the traces")
    else:
        result = measure(args.out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
