"""TCP integration tests: durable command identity and fail-closed uncertainty."""
import importlib
import json
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

import pytest


@pytest.fixture
def api():
    try:
        return importlib.import_module("pickloop.device")
    except ModuleNotFoundError:
        pytest.fail("the real Modbus TCP device implementation is missing")


@pytest.fixture
def device(api, tmp_path):
    server = api.DeviceEmulator(journal_path=tmp_path / "device.sqlite").start()
    try:
        yield server
    finally:
        server.stop()


def client(api, device, timeout=.15):
    return api.DeviceClient("127.0.0.1", device.port, timeout=timeout)


def test_duplicate_same_payload_is_not_reexecuted(api, device):
    first = client(api, device).command(1, True)
    duplicate = client(api, device).command(1, True)
    assert first["ack_id"] == duplicate["ack_id"] == 1
    assert duplicate["valve"] is True
    assert duplicate["execution_count"] == 1
    assert duplicate["pressure_kpa"] == 0
    assert duplicate["attached"] is False


def test_conflicting_duplicate_cannot_change_valve(api, device):
    c = client(api, device)
    c.command(5, True)
    with pytest.raises(api.DeviceError):
        c.command(5, False)
    assert c.status()["valve"] is True
    assert c.status()["execution_count"] == 1


def test_drop_ack_reconciles_without_reexecuting(api, device):
    c = client(api, device)
    device.inject_fault("drop_ack")
    result = c.command(9, True)
    assert result["ack_id"] == 9
    assert result["execution_count"] == 1
    assert c.command(9, True)["execution_count"] == 1


def test_delay_has_bounded_timeout_and_connection_recovers(api, device):
    c = client(api, device, timeout=.04)
    device.inject_fault("delay_response")
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        c.status()
    assert time.monotonic() - start < .2
    assert c.status()["ack_id"] == 0
    assert c.command(1, True)["execution_count"] == 1


def test_feedback_is_external_and_survives_valve_change(api, device):
    device.set_feedback(-52.3, True)
    c = client(api, device)
    assert c.command(1, True)["pressure_kpa"] == pytest.approx(-52.3)
    assert c.command(2, False)["attached"] is True
    device.set_feedback(0, False)
    assert c.status()["attached"] is False


def test_cancel_held_command_retains_valve_and_blocks_replay(api, device):
    c = client(api, device)
    c.command(10, True)
    device.set_feedback(-50, True)
    result = c.cancel(10)
    assert result["valve"] is True
    assert result["attached"] is True
    assert result["cancelled"] is True
    with pytest.raises(api.DeviceError):
        c.command(10, True)
    assert c.cancel(10)["execution_count"] == 1
    assert c.command(11, False)["valve"] is False


def test_cancel_before_command_is_a_persistent_tombstone(api, device):
    c = client(api, device)
    assert c.cancel(20)["execution_count"] == 0
    with pytest.raises(api.DeviceError):
        c.command(20, True)
    with pytest.raises(api.DeviceError):
        c.command(19, True)
    assert c.status()["valve"] is False


def test_old_duplicate_does_not_restore_outdated_valve(api, device):
    a, b = client(api, device), client(api, device)
    a.command(1, True)
    b.command(2, False)
    result = a.command(1, True)
    assert result["ack_id"] == 2
    assert result["valve"] is False
    assert result["execution_count"] == 2


def test_completed_commands_persist_on_restart(api, tmp_path):
    path = tmp_path / "durable.sqlite"
    d = api.DeviceEmulator(journal_path=path).start()
    client(api, d).command(30, True)
    d.stop()
    d = api.DeviceEmulator(journal_path=path).start()
    try:
        result = client(api, d).command(30, True)
        assert result["execution_count"] == 1
        assert result["valve"] is True
        with pytest.raises(api.DeviceError):
            client(api, d).command(29, False)
    finally:
        d.stop()


def test_unfinished_intent_at_restart_fails_closed_without_reexecution(api, tmp_path):
    path = tmp_path / "uncertain.sqlite"
    d = api.DeviceEmulator(journal_path=path).start()
    c = client(api, d)
    c.command(1, True)
    d.inject_fault("interrupt_after_intent")
    with pytest.raises(api.UncertainCommandError):
        c.command(2, False)
    d.stop()
    d = api.DeviceEmulator(journal_path=path).start()
    try:
        c = client(api, d)
        assert c.status()["error"] == "recovery_required"
        assert c.status()["valve"] is True
        assert c.status()["execution_count"] == 1
        for command_id in (2, 3):
            with pytest.raises(api.DeviceError):
                c.command(command_id, False)
        assert c.cancel(2)["valve"] is True
    finally:
        d.stop()


@pytest.mark.parametrize("command_id", [0, -1, 2**32, True])
def test_invalid_command_ids_do_not_execute(api, device, command_id):
    with pytest.raises(ValueError):
        client(api, device).command(command_id, True)
    assert client(api, device).status()["execution_count"] == 0


def raw_request(device, pdu):
    with socket.create_connection(("127.0.0.1", device.port), timeout=.2) as s:
        s.sendall(struct.pack(">HHHB", 17, 0, len(pdu) + 1, 1) + pdu)
        header = s.recv(7)
        length = struct.unpack(">HHHB", header)[2]
        answer = b""
        while len(answer) < length - 1:
            answer += s.recv(length - 1 - len(answer))
        return answer


@pytest.mark.parametrize("pdu, expected", [
    (bytes.fromhex("0400000001"), bytes.fromhex("8401")),
    (bytes.fromhex("0300000000"), bytes.fromhex("8303")),
    (bytes.fromhex("0300630001"), bytes.fromhex("8302")),
    (bytes.fromhex("100064000408000000010001"), bytes.fromhex("9003")),
    (bytes.fromhex("1000640004080000000100010002"), bytes.fromhex("9003")),
])
def test_server_returns_modbus_exceptions_for_bad_pdus(device, pdu, expected):
    assert raw_request(device, pdu) == expected


def response_peer(response):
    """An actual TCP peer supplying a deliberate invalid Modbus response."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]

    def serve():
        try:
            with listener.accept()[0] as connection:
                request = connection.recv(1024)
                transaction = request[:2]
                connection.sendall(response(transaction))
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return port, thread


@pytest.mark.parametrize("response", [
    lambda t: t + bytes.fromhex("00000003018302"),  # exception
    lambda t: bytes.fromhex("ffff00000003018302"),  # wrong transaction
    lambda t: t + bytes.fromhex("000000050103020000"),  # short register bank
    lambda t: t + bytes.fromhex("00010003018302"),  # non-Modbus protocol
    lambda t: t + bytes.fromhex("00000005010304"),  # truncated PDU
])
def test_client_rejects_error_and_malformed_responses(api, response):
    port, thread = response_peer(response)
    with pytest.raises(api.DeviceError):
        api.DeviceClient("127.0.0.1", port, timeout=.08).status()
    thread.join(.2)


def test_cpp_client_uses_same_tcp_device(api, device, tmp_path):
    root = Path(__file__).parents[1]
    binary = tmp_path / "modbus_client"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2", str(root / "cpp/modbus_client.cpp"), "-o", str(binary)], check=True)
    def run(*args):
        result = subprocess.run([str(binary), "127.0.0.1", str(device.port), *args], capture_output=True, text=True, check=True, timeout=2)
        return json.loads(result.stdout)
    assert run("command", "41", "1")["execution_count"] == 1
    assert run("command", "41", "1")["execution_count"] == 1
    device.inject_fault("drop_ack")
    assert run("command", "42", "1")["execution_count"] == 2
    assert run("cancel", "41")["valve"] is True
    assert run("status")["cancelled"] is True
    with pytest.raises(subprocess.CalledProcessError):
        run("command", "41", "0")


def test_cancelling_older_id_acknowledges_that_id_without_releasing(api, device):
    c = client(api, device)
    c.command(1, False)
    c.command(2, True)
    result = c.cancel(1)
    assert result["ack_id"] == 1
    assert result["max_command_id"] == 2
    assert result["valve"] is True
    assert result["execution_count"] == 2


def test_concurrent_duplicate_clients_execute_only_once(api, device):
    from concurrent.futures import ThreadPoolExecutor
    barrier = threading.Barrier(8)
    def submit(_):
        barrier.wait()
        return client(api, device, timeout=.5).command(77, True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))
    assert all(result["execution_count"] == 1 for result in results)
    assert client(api, device).status()["execution_count"] == 1


def test_uint32_boundary_is_not_truncated(api, device):
    c = client(api, device)
    assert c.command(4294967295, True)["ack_id"] == 4294967295
    assert c.command(4294967295, True)["execution_count"] == 1
    with pytest.raises(api.DeviceError):
        c.command(4294967294, False)


def test_stop_closes_old_sessions_before_same_object_restart(api, tmp_path):
    d = api.DeviceEmulator(journal_path=tmp_path / "restart.sqlite").start()
    connection = socket.create_connection(("127.0.0.1", d.port), timeout=.2)
    try:
        connection.sendall(bytes.fromhex("00010000000601030000000c"))
        assert len(connection.recv(1024)) == 33
        d.stop()
        d.start()
        assert connection.recv(1) == b""
        assert client(api, d).command(1, True)["execution_count"] == 1
    finally:
        connection.close()
        d.stop()
