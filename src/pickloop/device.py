"""Small, real Modbus TCP suction controller with durable idempotency.

The journal records controller intent/state, not physical evidence. Physics or
hardware owns pressure/attachment via ``set_feedback``. See docs/device-protocol.md.
"""
from __future__ import annotations

import math
import socket
import socketserver
import sqlite3
import struct
import threading
import time
from pathlib import Path


class DeviceError(RuntimeError):
    """A rejected command or invalid Modbus response."""


class DeviceProtocolError(DeviceError):
    def __init__(self, message: str, exception_code: int | None = None):
        super().__init__(message)
        self.exception_code = exception_code


class UncertainCommandError(DeviceError):
    """The caller must reconcile this ID; never resend with a new ID."""


def _validate_id(command_id: int) -> None:
    if type(command_id) is not int or not 1 <= command_id <= 0xFFFFFFFF:
        raise ValueError("command_id must be a positive uint32")


def _receive(sock: socket.socket, size: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Modbus response deadline expired")
        sock.settimeout(remaining)
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise DeviceProtocolError("connection closed before complete Modbus frame")
        data.extend(chunk)
    return bytes(data)


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


class _Handler(socketserver.BaseRequestHandler):
    def setup(self):
        with self.server.device._lock:
            self.server.device._connections.add(self.request)

    def finish(self):
        with self.server.device._lock:
            self.server.device._connections.discard(self.request)

    def handle(self):
        device = self.server.device
        stopping = self.server.stopping
        # Idle connections cannot hold the service's shutdown indefinitely.
        try:
            while not stopping.is_set():
                deadline = time.monotonic() + 1.0
                header = _receive(self.request, 7, deadline)
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                if protocol != 0 or unit != 1 or not 2 <= length <= 254:
                    return  # malformed MBAP has no trustworthy Modbus exception envelope
                pdu = _receive(self.request, length - 1, deadline)
                response, fault = device._process(pdu, stopping)
                if fault in ("drop_ack", "interrupt_after_intent"):
                    return
                if fault == "delay_response" and stopping.wait(.5):
                    return
                self.request.sendall(struct.pack(">HHHB", transaction, 0, len(response) + 1, 1) + response)
        except (OSError, DeviceError):
            return


class DeviceEmulator:
    """Threaded localhost TCP device. Use one active emulator per journal.

    Persisted commands never automatically execute again. An unfinished intent
    at startup latches recovery_required, retaining the last known valve state.
    """

    def __init__(self, host="127.0.0.1", port=0, journal_path=":memory:"):
        self.host, self.port = host, port
        self.journal_path = str(journal_path)
        self._lock = threading.RLock()
        self._connections = set()
        self._stopping = threading.Event()
        self._server = None
        self._thread = None
        self._db = None
        self._fault = None
        self._pressure = 0
        self._attached = False

    def start(self):
        if self._server is not None:
            return self
        if self.journal_path != ":memory:":
            Path(self.journal_path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.journal_path, check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS controller (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                ack_id INTEGER NOT NULL, valve INTEGER NOT NULL,
                execution_count INTEGER NOT NULL, max_id INTEGER NOT NULL,
                recovery_required INTEGER NOT NULL, cancelled INTEGER NOT NULL);
            INSERT OR IGNORE INTO controller VALUES (1,0,0,0,0,0,0);
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY, valve INTEGER,
                state TEXT NOT NULL CHECK(state IN ('pending','applied','cancelled')));
        """)
        if db.execute("SELECT 1 FROM commands WHERE state='pending' LIMIT 1").fetchone():
            db.execute("UPDATE controller SET recovery_required=1 WHERE singleton=1")
        db.commit()
        self._db = db
        try:
            self._server = _Server((self.host, self.port), _Handler)
        except Exception:
            db.close()
            self._db = None
            raise
        self.port = self._server.server_address[1]
        self._server.device = self
        self._stopping = threading.Event()
        self._server.stopping = self._stopping
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server is None:
            return
        self._stopping.set()
        self._server.shutdown()
        with self._lock:
            for connection in tuple(self._connections):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        self._server.server_close()
        self._thread.join(timeout=1)
        # No handlers may enter the DB after observing stopping; handlers already
        # processing hold this lock until their durable operation is complete.
        with self._lock:
            self._db.close()
            self._db = None
            self._server = None

    def output_valve(self):
        """Plant-side digital output, independent of client ACK/reconciliation.

        This is an emulator wiring interface, never a coordinator observation.
        """
        with self._lock:
            return bool(self._db.execute('SELECT valve FROM controller WHERE singleton=1').fetchone()[0])

    def set_feedback(self, pressure_kpa, attached):
        if not math.isfinite(pressure_kpa) or not -3276.8 <= pressure_kpa <= 3276.7:
            raise ValueError("pressure must be finite and fit signed 0.1 kPa register")
        if type(attached) is not bool:
            raise ValueError("attached must be bool")
        with self._lock:
            self._pressure = round(pressure_kpa * 10)
            self._attached = attached

    def inject_fault(self, kind):
        """One-shot transport/crash-window fault for reproducible evaluation."""
        if kind not in ("drop_ack", "delay_response", "interrupt_after_intent"):
            raise ValueError("unknown device fault")
        with self._lock:
            self._fault = kind

    def _registers(self):
        ack, valve, count, max_id, recovery, cancelled = self._db.execute(
            "SELECT ack_id,valve,execution_count,max_id,recovery_required,cancelled FROM controller WHERE singleton=1"
        ).fetchone()
        return [1, ack >> 16, ack & 0xFFFF, valve, self._pressure & 0xFFFF,
                int(self._attached), recovery, count >> 16, count & 0xFFFF,
                max_id >> 16, max_id & 0xFFFF, cancelled]

    def _write(self, command_id, operation, valve, fault):
        if command_id == 0 or operation not in (1, 2) or valve not in (0, 1) or (operation == 2 and valve):
            return 3
        old = self._db.execute("SELECT valve,state FROM commands WHERE id=?", (command_id,)).fetchone()
        ack, current_valve, count, max_id, recovery, cancelled = self._db.execute(
            "SELECT ack_id,valve,execution_count,max_id,recovery_required,cancelled FROM controller WHERE singleton=1"
        ).fetchone()
        if operation == 2:
            # Cancellation is a journal fence, never a release command. Pending
            # uncertainty remains latched even if its ID is subsequently cancelled.
            if old is None:
                if command_id < max_id:
                    return 3
                self._db.execute("INSERT INTO commands VALUES (?,NULL,'cancelled')", (command_id,))
            else:
                self._db.execute("UPDATE commands SET state='cancelled' WHERE id=?", (command_id,))
            self._db.execute("UPDATE controller SET ack_id=?,max_id=?,cancelled=1 WHERE singleton=1",
                             (command_id, max(max_id, command_id)))
            self._db.commit()
            return None
        if recovery:
            return 4  # server failure: uncertain hardware state requires operator recovery
        if old:
            return None if old == (valve, "applied") else 3
        if command_id <= max_id or count >= 0xFFFFFFFF:
            return 3
        # Separate durable intent from durable result: a crash in this window
        # cannot prove execution and must never silently replay the action.
        self._db.execute("INSERT INTO commands VALUES (?,?,'pending')", (command_id, valve))
        self._db.execute("UPDATE controller SET max_id=? WHERE singleton=1", (command_id,))
        self._db.commit()
        if fault == "interrupt_after_intent":
            self._db.execute("UPDATE controller SET recovery_required=1 WHERE singleton=1")
            self._db.commit()
            return None
        self._db.execute("UPDATE commands SET state='applied' WHERE id=?", (command_id,))
        self._db.execute("UPDATE controller SET ack_id=?,valve=?,execution_count=execution_count+1,cancelled=0 WHERE singleton=1", (command_id, valve))
        self._db.commit()
        return None

    def _process(self, pdu, stopping):
        with self._lock:
            if stopping.is_set():
                return bytes([pdu[0] | 0x80, 4]), None
            fc = pdu[0]
            # A write-specific fault waits for a write rather than being consumed
            # by a diagnostic status read.
            fault = self._fault
            if fault == "delay_response" or (fc == 16 and fault):
                self._fault = None
            else:
                fault = None
            error = None
            if fc == 3:
                if len(pdu) != 5:
                    error = 3
                else:
                    address, quantity = struct.unpack(">HH", pdu[1:])
                    if not 1 <= quantity <= 125:
                        error = 3
                    elif address + quantity > 12:
                        error = 2
                    else:
                        registers = self._registers()[address:address + quantity]
                        response = bytes([3, 2 * quantity]) + struct.pack(">" + "H" * quantity, *registers)
            elif fc == 16:
                if len(pdu) < 6:
                    error = 3
                else:
                    address, quantity, byte_count = struct.unpack(">HHB", pdu[1:6])
                    if quantity != 4 or byte_count != 8 or len(pdu) != 14:
                        error = 3
                    elif address != 100:
                        error = 2
                    else:
                        hi, lo, operation, valve = struct.unpack(">HHHH", pdu[6:])
                        error = self._write((hi << 16) | lo, operation, valve, fault)
                        response = bytes([16]) + pdu[1:5]
            else:
                error = 1
            return (bytes([fc | 0x80, error]) if error else response), fault


class DeviceClient:
    """Each RPC uses a fresh TCP connection; reconnect needs no session recovery.

    A command uses at most two RPC deadlines (write + status reconciliation).
    A write timeout never causes automatic execution under a new command ID.
    """

    def __init__(self, host, port, timeout=.2):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self.host, self.port, self.timeout = host, port, timeout
        self._transaction = 0
        self._lock = threading.Lock()

    def _request(self, pdu):
        # A client can be shared between threads; transaction assignment is local
        # but every reply is validated against its own actual request.
        with self._lock:
            self._transaction = (self._transaction + 1) & 0xFFFF
            transaction = self._transaction
        deadline = time.monotonic() + self.timeout
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(max(.000001, deadline - time.monotonic()))
                sock.sendall(struct.pack(">HHHB", transaction, 0, len(pdu) + 1, 1) + pdu)
                header = _receive(sock, 7, deadline)
                tid, protocol, length, unit = struct.unpack(">HHHB", header)
                if tid != transaction or protocol != 0 or unit != 1 or not 2 <= length <= 254:
                    raise DeviceProtocolError("invalid Modbus MBAP response")
                response = _receive(sock, length - 1, deadline)
        except TimeoutError:
            raise
        except OSError as exc:
            raise DeviceProtocolError("Modbus transport failed") from exc
        if response[0] == pdu[0] | 0x80:
            if len(response) != 2:
                raise DeviceProtocolError("malformed Modbus exception")
            raise DeviceProtocolError(f"Modbus exception {response[1]}", response[1])
        if response[0] != pdu[0]:
            raise DeviceProtocolError("unexpected Modbus function")
        return response

    def status(self):
        response = self._request(bytes.fromhex("030000000c"))
        if len(response) != 26 or response[1] != 24:
            raise DeviceProtocolError("invalid status register length")
        r = struct.unpack(">12H", response[2:])
        if r[0] != 1 or r[3] > 1 or r[5] > 1 or r[6] > 1 or r[11] > 1:
            raise DeviceProtocolError("invalid status register values")
        pressure = r[4] if r[4] < 0x8000 else r[4] - 0x10000
        return {"ack_id": (r[1] << 16) | r[2], "valve": bool(r[3]),
                "pressure_kpa": pressure / 10, "attached": bool(r[5]),
                "error": "recovery_required" if r[6] else "none",
                "execution_count": (r[7] << 16) | r[8],
                "max_command_id": (r[9] << 16) | r[10], "cancelled": bool(r[11])}

    def _operate(self, command_id, operation, valve):
        _validate_id(command_id)
        pdu = bytes([16]) + struct.pack(">HHBHHHH", 100, 4, 8, command_id >> 16, command_id & 0xFFFF, operation, int(valve))
        uncertain = False
        try:
            response = self._request(pdu)
            if response != bytes.fromhex("1000640004"):
                raise DeviceProtocolError("invalid FC16 write acknowledgement")
        except DeviceProtocolError as exc:
            if exc.exception_code is not None:
                raise  # a valid Modbus exception is a definitive rejection
            uncertain = True
        except TimeoutError:
            uncertain = True
        try:
            status = self.status()
        except (DeviceError, TimeoutError) as exc:
            raise UncertainCommandError(f"command {command_id}: no confirmed result; reconcile same ID") from exc
        if uncertain and (status["error"] != "none" or status["ack_id"] != command_id or
                          (operation == 1 and (status["cancelled"] or status["valve"] != valve)) or
                          (operation == 2 and not status["cancelled"])):
            raise UncertainCommandError(f"command {command_id}: result is uncertain; reconcile same ID")
        return status

    def command(self, command_id: int, valve: bool):
        if type(valve) is not bool:
            raise ValueError("valve must be bool")
        return self._operate(command_id, 1, valve)

    def cancel(self, command_id: int):
        return self._operate(command_id, 2, False)

    def close(self):
        """No persistent socket is held; provided for owner lifecycle symmetry."""
