"""Loopback bench. Awlsim runs OB1 and pyModbusTCP handles the protocol."""
import contextlib
import socket
import socketserver
import struct
import threading
import time
from pathlib import Path

# Awlsim 0.78 initializes parser types during this import.
from awlsim.core.main import AwlSim
from awlsim.awlcompiler.tokenizer import AwlParser
from pyModbusTCP.server import DataBank, DataHandler, ModbusServer

PERIOD = 0.010


class ScanStation(DataHandler):
    """Copy command and sensor inputs into the S7 image once per scan."""

    def __init__(self):
        super().__init__(DataBank(virtual_mode=True))
        parser = AwlParser()
        parser.parseText(Path(__file__).with_name("pickloop.awl").read_text())
        self.sim = AwlSim()
        self.sim.load(parser.getParseTree(), rebuild=True)
        self.sim.startup()
        self.cv = threading.Condition()
        self.writer = threading.Lock()
        self.stop = threading.Event()
        self.mailbox = None
        self.pressure = self.attached = 0
        self.output = ()
        self.scans = []
        self.thread = threading.Thread(target=self.cycle, daemon=True)
        self.thread.start()
        with self.cv:
            if not self.cv.wait_for(lambda: self.output, 1):
                raise RuntimeError("PLC did not complete its first scan")

    def cycle(self):
        start = deadline = time.monotonic_ns()
        while not self.stop.is_set():
            with self.cv:
                before = time.monotonic_ns()
                words = self.mailbox or (0, 0, 0, 0)
                inputs = self.sim.cpu.inputs.getDataBytes()
                struct.pack_into(">4HhHH", inputs, 0, *words, self.pressure, self.attached,
                                 int(self.mailbox is not None))
                self.sim.runCycle()
                self.output = struct.unpack_from(">13H", self.sim.cpu.outputs.getDataBytes())
                self.scans.append({"scan": len(self.scans) + 1, "at_ns": before - start,
                                   "execution_ns": time.monotonic_ns() - before,
                                   "command": self.mailbox, "pressure_deci_kpa": self.pressure,
                                   "attached_input": self.attached, "output": self.output})
                self.mailbox = None
                self.cv.notify_all()
            # When the OS misses a deadline, resume on a future period.
            deadline += int(PERIOD * 1e9)
            now = time.monotonic_ns()
            if deadline < now:
                deadline = now + int(PERIOD * 1e9)
            self.stop.wait((deadline - now) / 1e9)

    def feedback(self, pressure_deci_kpa, attached):
        with self.cv:
            self.pressure, self.attached = pressure_deci_kpa, int(attached)
            prior = len(self.scans)
            if not self.cv.wait_for(lambda: len(self.scans) > prior, 1):
                raise RuntimeError("sensor fixture did not reach the process image")

    def write_h_regs(self, address, words_l, srv_info):
        if address != 100 or len(words_l) != 4:
            return self.Return(2)
        with self.writer, self.cv:
            self.mailbox = tuple(words_l)
            if not self.cv.wait_for(lambda: self.mailbox is None, 1):
                return self.Return(4)
            return self.Return(self.output[12])

    def read_h_regs(self, address, count, srv_info):
        if address + count > 12:
            return self.Return(2)
        with self.cv:
            return self.Return(0, self.output[address:address + count])

    def close(self):
        self.stop.set()
        self.thread.join()
        self.sim.shutdown()


def read_frame(stream):
    header = stream.read(7)
    if len(header) != 7:
        raise EOFError("incomplete Modbus header")
    length = struct.unpack_from(">H", header, 4)[0]
    if not 2 <= length <= 254:
        raise ValueError("invalid Modbus length")
    body = stream.read(length - 1)
    if len(body) != length - 1:
        raise EOFError("incomplete Modbus payload")
    return header + body


class LoopbackRelay(socketserver.StreamRequestHandler):
    """Record each real client RPC and optionally disconnect one test write."""
    timeout = 1

    def handle(self):
        start = time.monotonic_ns()
        request = read_frame(self.rfile)
        response = b""
        fault = self.server.fault if request[7] == 16 else None
        if fault:
            self.server.fault = None
        if fault != "drop_before_forward":
            with socket.create_connection(("127.0.0.1", self.server.peer), timeout=1) as peer:
                peer.sendall(request)
                with peer.makefile("rb") as stream:
                    response = read_frame(stream)
        row = {"step": self.server.step, "connection": len(self.server.wire) + 1,
               "request_hex": request.hex(), "response_hex": response.hex(),
               "forwarded": fault != "drop_before_forward", "delivered": fault is None,
               "fault": fault, "service_ns": time.monotonic_ns() - start}
        self.server.wire.append(row)
        if not fault:
            self.wfile.write(response)


@contextlib.contextmanager
def bench():
    station = ScanStation()
    try:
        plc = ModbusServer(host="127.0.0.1", port=0, no_block=True, data_hdl=station)
        plc.start()
        try:
            with socketserver.TCPServer(("127.0.0.1", 0), LoopbackRelay) as relay:
                # pyModbusTCP 0.3.1 stores the bound ephemeral port on its TCP server.
                relay.peer = plc._service.server_address[1]
                relay.wire = []
                relay.step = relay.fault = None
                worker = threading.Thread(target=relay.serve_forever, args=(0.01,), daemon=True)
                worker.start()
                try:
                    yield station, relay
                finally:
                    relay.shutdown()
                    worker.join()
        finally:
            plc.stop()
    finally:
        station.close()
