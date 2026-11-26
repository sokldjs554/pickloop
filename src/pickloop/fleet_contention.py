"""Exercise the existing exclusive-zone lease with independent TCP robot clients."""

from __future__ import annotations

import argparse
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import random
import socket
from socketserver import StreamRequestHandler, ThreadingTCPServer
from threading import Condition, Thread
import time


FAULT = "fault-amr"
SUPERVISOR = "supervisor"
FAULT_TASK = f"{FAULT}/0"


class Zone:
    """Serialize the existing lease operations and admit waiting tasks in FIFO order."""

    def __init__(self, robots, lease_s, timeout_s):
        from .mobile import FleetScheduler, MobileHold

        self.lease = FleetScheduler([*robots, FAULT], lease_s=lease_s)
        self.hold = MobileHold
        self.timeout_s = timeout_s
        self.condition = Condition()
        self.started_ns = time.monotonic_ns()
        self.deadline = time.monotonic() + timeout_s
        self.events = []
        self.connected = {}
        self.identities = {}
        self.owner_disconnected = False
        self.current = None
        self.pending = deque()
        self.completed = set()
        self.fenced_waiters = set()

    def record(self, event, robot, task=None, **fields):
        self.events.append(dict(seq=len(self.events), elapsed_ns=time.monotonic_ns() - self.started_ns,
                                event=event, robot=robot, task=task, **fields))

    def connect(self, robot, pid):
        with self.condition:
            allowed = robot in self.lease.robots or (robot == SUPERVISOR and pid == os.getpid())
            if not allowed or robot in self.connected or self.identities.get(robot, pid) != pid:
                return False
            self.connected[robot] = pid
            self.identities[robot] = pid
            self.record("connected", robot, pid=pid)
            self.condition.notify_all()
            return True

    def disconnect(self, robot):
        with self.condition:
            self.connected.pop(robot)
            self.record("disconnected", robot)
            if self.current and self.current[0] == robot and not self.owner_disconnected:
                self.owner_disconnected = True
                self.record("owner_disconnected", *self.current, occupied=robot in self.lease.occupied)
            self.condition.notify_all()

    def refresh_lease(self):
        was_fenced = self.lease.fenced
        if self.current:
            self.lease.valid(self.current[0], time.monotonic())
            if self.lease.fenced and not was_fenced:
                self.record("fenced", *self.current)
                self.condition.notify_all()

    def await_state(self, ready, reason):
        with self.condition:
            if not self.condition.wait_for(ready, timeout=max(0, self.deadline - time.monotonic())):
                raise RuntimeError(reason)

    def acquire(self, robot, task):
        key = (robot, task)
        if key in self.completed:
            self.record("completed_retry", robot, task)
            return "already_completed"
        self.pending.append(key)
        self.record("queued", robot, task, queue_depth=len(self.pending))
        self.condition.notify_all()
        while time.monotonic() < self.deadline:
            self.refresh_lease()
            if self.lease.fenced and key not in self.fenced_waiters:
                self.fenced_waiters.add(key)
                self.record("waiting_fenced", robot, task)
                self.condition.notify_all()
            if self.current is None and self.pending[0] == key and self.lease.acquire(robot, time.monotonic()):
                self.pending.popleft()
                self.current = key
                self.owner_disconnected = False
                self.record("granted", robot, task, queue_depth=len(self.pending))
                self.condition.notify_all()
                return "granted"
            self.condition.wait(timeout=0.025)
        self.pending.remove(key)
        self.record("timeout", robot, task)
        return "timeout"

    def request(self, robot, op, task, clear):
        with self.condition:
            self.refresh_lease()
            if robot == SUPERVISOR:
                # Only the harness's separate clearance signal may remove a disconnected owner.
                if (op != "reconcile" or task != FAULT_TASK or self.current != (FAULT, FAULT_TASK)
                        or not self.lease.fenced or not self.owner_disconnected or FAULT in self.connected):
                    return "reconcile_rejected"
                if clear is not True:
                    self.record("unclear_reconcile_rejected", FAULT, task)
                    return "reconcile_rejected"
                self.lease.release(FAULT, estimated_clear=True)
                self.record("reconciled", FAULT, task, clearance="synthetic_supervisor")
                self.current = None
                self.condition.notify_all()
                return "reconciled"
            if not isinstance(task, str) or not task.startswith(f"{robot}/"):
                return "task_identity_mismatch"
            if op == "acquire":
                return self.acquire(robot, task)
            if self.current != (robot, task):
                return "owner_mismatch"
            if op == "enter":
                try:
                    self.lease.enter(robot, time.monotonic())
                except self.hold:
                    self.record("stale_entry_rejected", robot, task)
                    return "entry_rejected"
                self.record("entered", robot, task)
                return "entered"
            if op == "release":
                # A disconnected owner needs the supervisor even after it reconnects.
                try:
                    self.lease.release(robot, estimated_clear=(
                        clear is True and not self.owner_disconnected and not self.lease.fenced))
                except self.hold:
                    self.record("unclear_release_rejected", robot, task)
                    return "release_rejected"
                self.completed.add((robot, task))
                self.record("released", robot, task)
                self.current = None
                self.condition.notify_all()
                return "released"
            return "unknown_operation"


class Server(ThreadingTCPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, zone):
        self.zone = zone
        super().__init__(("127.0.0.1", 0), RequestHandler)


class RequestHandler(StreamRequestHandler):
    def reply(self, status):
        self.wfile.write(json.dumps({"status": status}).encode() + b"\n")

    def handle(self):
        self.connection.settimeout(self.server.zone.timeout_s)
        line = self.rfile.readline(4096)
        if not line:
            return
        hello = json.loads(line)
        robot = hello["robot"]
        if not self.server.zone.connect(robot, hello["pid"]):
            self.reply("identity_rejected")
            return
        try:
            self.reply("connected")
            while line := self.rfile.readline(4096):
                message = json.loads(line)
                self.reply(self.server.zone.request(robot, message["op"], message["task"],
                                                    message.get("clear")))
        except (ConnectionError, TimeoutError):
            pass
        finally:
            self.server.zone.disconnect(robot)


def request(stream, *, expected, **message):
    stream.write(json.dumps(message).encode() + b"\n")
    stream.flush()
    reply = stream.readline(4096)
    status = json.loads(reply)["status"] if reply else "connection_closed"
    if status != expected:
        raise RuntimeError(f"{message}: expected {expected}, received {status}")


@contextmanager
def connect(address, robot, timeout_s):
    with socket.create_connection(address, timeout_s) as client:
        with client.makefile("rwb") as stream:
            request(stream, expected="connected", robot=robot, pid=os.getpid())
            yield stream


def worker(address, robot, index, tasks, seed, start, timeout_s):
    rng = random.Random(seed + index)
    with connect(address, robot, timeout_s) as stream:
        if not start.wait(timeout_s):
            raise RuntimeError("worker start deadline")
        for number in range(tasks):
            task = f"{robot}/{number}"
            request(stream, expected="granted", op="acquire", task=task)
            request(stream, expected="entered", op="enter", task=task)
            time.sleep(rng.uniform(0.008, 0.018))
            request(stream, expected="released", op="release", task=task, clear=True)
        request(stream, expected="already_completed", op="acquire", task=task)


def fault_worker(address, probe, timeout_s):
    with connect(address, FAULT, timeout_s) as stream:
        request(stream, expected="granted", op="acquire", task=FAULT_TASK)
        request(stream, expected="entered", op="enter", task=FAULT_TASK)
    if not probe.wait(timeout_s):
        raise RuntimeError("fault probe deadline")
    with connect(address, FAULT, timeout_s) as stream:
        request(stream, expected="entry_rejected", op="enter", task=FAULT_TASK)
        request(stream, expected="release_rejected", op="release", task=FAULT_TASK, clear=False)


def evaluate(events, robots, tasks):
    """Replay coordinator decisions without relying on its lease or queue snapshots."""
    queued = {}
    processes = {}
    connected = set()
    grants = set()
    finished = set()
    retries = set()
    waiting_fenced = set()
    fault_time = {}
    waits = []
    windows = []
    owner = None
    occupants = set()
    peak_queue = peak_occupancy = unsafe = violations = 0
    prior_ns = -1
    for sequence, row in enumerate(events):
        event, robot, task, timestamp = (row[name] for name in ("event", "robot", "task", "elapsed_ns"))
        violations += int(row["seq"] != sequence or timestamp < prior_ns)
        prior_ns = timestamp
        key = (robot, task)
        if event == "connected":
            violations += int(robot in connected)
            connected.add(robot)
            if robot != SUPERVISOR:
                previous = processes.setdefault(robot, row["pid"])
                violations += int(previous != row["pid"])
        elif event == "disconnected":
            violations += int(robot not in connected)
            connected.discard(robot)
        elif event == "queued":
            violations += int(key in queued or key in finished or row["queue_depth"] != len(queued) + 1)
            queued[key] = timestamp
            peak_queue = max(peak_queue, len(queued))
        elif event == "granted":
            safe = owner is None and not occupants and robot in connected and key not in grants
            unsafe += int(not safe)
            violations += int(next(iter(queued), None) != key)
            queued_at = queued.pop(key, timestamp)
            violations += int(row["queue_depth"] != len(queued))
            if robot != FAULT:
                waits.append((timestamp - queued_at) / 1e6)
            grants.add(key)
            owner = key
        elif event == "entered":
            violations += int(owner != key or bool(occupants) or robot not in connected)
            occupants.add(key)
            peak_occupancy = max(peak_occupancy, len(occupants))
        elif event == "waiting_fenced":
            violations += int(key not in queued or "fenced" not in fault_time
                              or "reconciled" in fault_time)
            waiting_fenced.add(robot)
        elif event in {"released", "reconciled"}:
            violations += int(owner != key or occupants != {key})
            owner = None
            occupants.discard(key)
            if event == "released":
                violations += int(key in finished or robot == FAULT or robot not in connected)
                finished.add(key)
                windows.append(timestamp)
        elif event == "completed_retry":
            violations += int(key not in finished or key in retries)
            retries.add(key)
        elif event not in {"owner_disconnected", "fenced", "stale_entry_rejected",
                           "unclear_release_rejected", "unclear_reconcile_rejected"}:
            violations += 1
        if event in {"owner_disconnected", "fenced", "stale_entry_rejected",
                     "unclear_release_rejected", "unclear_reconcile_rejected", "reconciled"}:
            violations += int(robot != FAULT or task != FAULT_TASK or event in fault_time)
            if event != "reconciled":
                violations += int(owner != key or occupants != {key})
            fault_time[event] = timestamp
            if event == "owner_disconnected":
                violations += int(row["occupied"] is not True or FAULT in connected)
            elif event in {"unclear_reconcile_rejected", "reconciled"}:
                violations += int(SUPERVISOR not in connected or FAULT in connected)
                if event == "reconciled":
                    violations += int(row["clearance"] != "synthetic_supervisor")

    expected = {(robot, f"{robot}/{number}") for robot in robots for number in range(tasks)}
    expected_retries = {(robot, f"{robot}/{tasks - 1}") for robot in robots}
    phases = ("owner_disconnected", "fenced", "stale_entry_rejected",
              "unclear_release_rejected", "unclear_reconcile_rejected", "reconciled")
    ordered = all(phase in fault_time for phase in phases) and list(fault_time) == list(phases)
    count = len(set(processes.values()))
    violations += int(not ordered or owner is not None or bool(occupants or queued or connected))
    violations += int(set(processes) != {*robots, FAULT} or count != len(robots) + 1)
    violations += int(expected != finished or grants != expected | {(FAULT, FAULT_TASK)}
                      or retries != expected_retries)
    violations += int(waiting_fenced != set(robots) or peak_queue != len(robots))
    waits.sort()
    elapsed_ms = (max(windows) - fault_time["reconciled"]) / 1e6 if windows and ordered else 0
    return {
        "worker_processes": count, "completed_tasks": len(finished), "grants": len(grants),
        "completed_id_retries": len(retries),
        "unsafe_grants": unsafe, "trace_violations": violations, "peak_queue_depth": peak_queue,
        "fenced_waiters": len(waiting_fenced), "peak_modeled_occupancy": peak_occupancy,
        "queue_wait_ms_p50": round(waits[math.ceil(len(waits) * 0.50) - 1], 3) if waits else None,
        "queue_wait_ms_p95": round(waits[math.ceil(len(waits) * 0.95) - 1], 3) if waits else None,
        "queue_wait_ms_max": round(waits[-1], 3) if waits else None,
        "drain_ms": round(elapsed_ms, 3),
        "throughput_tasks_s": round(len(finished) * 1000 / elapsed_ms, 3) if elapsed_ms > 0 else None,
        "disconnect_to_fence_ms": (
            round((fault_time["fenced"] - fault_time["owner_disconnected"]) / 1e6, 3) if ordered else None),
        "fence_to_clearance_ms": (
            round((fault_time["reconciled"] - fault_time["fenced"]) / 1e6, 3) if ordered else None),
    }


def join(process, deadline):
    process.join(max(0, deadline - time.monotonic()))
    if process.exitcode != 0:
        raise RuntimeError(f"{process.name} failed to finish, exitcode={process.exitcode}")


def run(out, robot_count, tasks, seed, lease_s, timeout_s):
    started = datetime.now(timezone.utc)
    robots = [f"amr-{i:02d}" for i in range(robot_count)]
    zone = Zone(robots, lease_s, timeout_s)
    context = mp.get_context("spawn")
    start, probe = context.Event(), context.Event()
    children = []
    with Server(zone) as server:
        server_thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.025})
        server_thread.start()
        try:
            address = server.server_address
            for i, robot in enumerate(robots):
                child = context.Process(name=robot, target=worker,
                                        args=(address, robot, i, tasks, seed, start, timeout_s))
                child.start()
                children.append(child)
            zone.await_state(lambda: all(robot in zone.connected for robot in robots),
                             "healthy workers failed to connect")
            fault = context.Process(name=FAULT, target=fault_worker, args=(address, probe, timeout_s))
            fault.start()
            children.append(fault)
            zone.await_state(lambda: zone.owner_disconnected, "fault did not disconnect as zone owner")
            start.set()
            zone.await_state(lambda: len(zone.fenced_waiters) == robot_count,
                             "contenders did not all observe the fenced lease")
            probe.set()
            join(fault, zone.deadline)
            zone.await_state(lambda: FAULT not in zone.connected, "fault probe did not disconnect")
            with connect(address, SUPERVISOR, timeout_s) as stream:
                request(stream, expected="reconcile_rejected", op="reconcile", task=FAULT_TASK, clear=False)
                request(stream, expected="reconciled", op="reconcile", task=FAULT_TASK, clear=True)
            for child in children:
                join(child, zone.deadline)
            zone.await_state(lambda: not zone.connected, "TCP handlers did not finish")
            if zone.identities != {SUPERVISOR: os.getpid(), **{child.name: child.pid for child in children}}:
                raise RuntimeError("reported identities did not match spawned workers")
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(1)
            server.shutdown()
            server_thread.join()

    out.mkdir(parents=True, exist_ok=True)
    events_path = out / "events.jsonl.gz"
    raw = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in zone.events).encode()
    events_path.write_bytes(gzip.compress(raw, mtime=0))
    metrics = evaluate(zone.events, robots, tasks)
    sources = [Path(__file__), Path(__file__).with_name("mobile.py")]
    result = {
        "started_utc": started.isoformat(timespec="milliseconds"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "platform": platform.platform(), "python": platform.python_version(),
        "topology": "single-host loopback TCP; one coordinator and spawned robot processes",
        "coordinator_pid": os.getpid(), "zone_capacity": 1,
        "config": dict(robots=robots, tasks_per_robot=tasks, seed=seed, lease_s=lease_s, timeout_s=timeout_s),
        "events": len(zone.events), "events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
        "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "metrics": metrics, "passed": not (metrics["unsafe_grants"] or metrics["trace_violations"]),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(metrics, sort_keys=True))
    return result["passed"]


def check(out):
    result = json.loads((out / "result.json").read_text())
    compressed = (out / "events.jsonl.gz").read_bytes()
    events = [json.loads(line) for line in gzip.decompress(compressed).splitlines()]
    config = result["config"]
    metrics = evaluate(events, config["robots"], config["tasks_per_robot"])
    passed = (hashlib.sha256(compressed).hexdigest() == result["events_sha256"]
              and len(events) == result["events"] and metrics == result["metrics"]
              and result["passed"] is True and metrics["unsafe_grants"] == metrics["trace_violations"] == 0)
    print(json.dumps({"passed": passed, "metrics": metrics}, sort_keys=True))
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--robots", type=int, default=24, choices=range(2, 65), metavar="2..64")
    parser.add_argument("--tasks", type=int, default=8, choices=range(1, 65), metavar="1..64")
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--lease-s", type=float, default=0.5)
    parser.add_argument("--timeout-s", type=float, default=25)
    args = parser.parse_args()
    if not (0 < args.lease_s < args.timeout_s < math.inf):
        parser.error("require finite durations and 0 < lease-s < timeout-s")
    if args.check:
        return 0 if check(args.check) else 1
    return 0 if run(args.out, args.robots, args.tasks, args.seed, args.lease_s, args.timeout_s) else 1


if __name__ == "__main__":
    raise SystemExit(main())
