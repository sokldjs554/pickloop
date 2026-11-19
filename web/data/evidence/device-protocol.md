# Device protocol and recovery contract

This is a working TCP controller emulator and two interoperating clients, not a physical PLC or a certified safety controller. The Python server uses stdlib TCP/threading and SQLite. The independent POSIX C++17 program constructs and validates actual Modbus TCP frames; it does not call Python or share emulator memory.

## Usage

```python
from pickloop.device import DeviceEmulator, DeviceClient

server = DeviceEmulator(journal_path="work/device.sqlite").start()
client = DeviceClient("127.0.0.1", server.port, timeout=.2)
try:
    result = client.command(1, True)
    # The simulation/hardware adapter supplies physical observations separately.
    server.set_feedback(-52.3, True)
    print(client.status())
    client.cancel(1)  # leaves valve on; does not drop a held object
finally:
    client.close()
    server.stop()
```

The physics adapter must apply the observed controller `valve` to the suction model and call `set_feedback(pressure_kpa, attached)` from physics. A write changes controller valve intent only. It never invents pressure, attachment, a seal, or successful transport. Feedback defaults to `0.0` kPa and `False` in a new emulator object and is not restored from the command journal. Treat missing fresh sensor feedback after restart as unverified physical state.

Use a file journal for durability (`:memory:` is only for ephemeral runs). Use one active emulator per journal. Multiple simultaneous TCP clients are serialized through the controller lock. Clients must allocate globally unique, monotonically increasing positive uint32 IDs for new valve commands; after reconnect, inspect `max_command_id`. The device does not allocate IDs for clients. ID exhaustion requires explicit operator recovery, not wraparound.

## Frames and registers

All integers use network byte order. MBAP is transaction ID uint16, protocol ID `0`, length uint16 including unit ID, unit ID `1`. Maximum MBAP length is 254; invalid headers close the connection. Each valid reply echoes the transaction and unit. The Python client opens a fresh socket per RPC, so reconnect has no hidden session state.

FC03 (Read Holding Registers) exposes addresses 0–11. Any contiguous nonempty subset can be read. The clients read all twelve in one atomic snapshot.

| Address | Meaning |
| --- | --- |
| 0 | Protocol version: 1 |
| 1–2 | `ack_id`, high/low words |
| 3 | Controller valve intent: 0/1 |
| 4 | Signed int16 pressure, 0.1 kPa units |
| 5 | Physics/hardware attachment feedback: 0/1 |
| 6 | Error: 0 none, 1 recovery_required |
| 7–8 | Durable valve execution count, high/low words |
| 9–10 | Maximum reserved command ID, high/low words |
| 11 | Last acknowledged operation was cancellation: 0/1 |

FC16 (Write Multiple Registers) accepts exactly four registers at address 100:

| Offset | Meaning |
| --- | --- |
| 0–1 | Positive uint32 command ID, high/low words |
| 2 | Operation: 1 set valve, 2 cancel target ID |
| 3 | Valve: 0/1 for operation 1; must be 0 for operation 2 |

The FC16 reply is the standard address/quantity echo. It is sent after the operation has been committed to SQLite. Unsupported functions return exception 1, inaccessible addresses exception 2, malformed payloads/conflicts/stale IDs exception 3, and unresolved controller uncertainty exception 4. Error replies never change valve intent. Malformed/truncated MBAP frames receive no reply.

`ack_id` identifies the most recent durable valve application or cancellation. An accepted identical replay does not change the current state or move the acknowledgement back to an older ID. Cancelling an older ID explicitly acknowledges that target, so `ack_id` may decrease; `max_command_id` never decreases. A global status snapshot can reflect another client's later operation. A successful FC16 echo establishes acceptance even if the following snapshot reports a different ID.

## Identity, uncertainty, and cancellation

Before applying a new valve command, the emulator commits a `pending` intent and reserves its ID. It then commits `applied`, valve intent, acknowledgement, and execution count in a separate transaction with `synchronous=FULL`. Repeating an `applied` ID with identical valve payload returns success without execution or state restoration. A different payload with that ID is rejected. An unseen ID less than or equal to the reserved maximum is rejected.

On startup any `pending` row latches `recovery_required`. All valve writes, including duplicate valve writes, are then rejected. The last known valve intent remains unchanged; the server does not assume an uncertain release happened. This is deliberately an at-most-once intent protocol: a crash can leave an action unconfirmed, rather than safely proving exactly-once physical actuation. There is no automatic reset endpoint. Recovery requires an operator to reconcile hardware and create an explicitly recovered controller journal; deleting a journal blindly is unsafe.

Cancellation is a durable fence for the target command ID, not a valve write or a motion controller stop. For an existing ID it marks the record cancelled. For an unseen ID at or above the current maximum it reserves a cancellation tombstone. Later valve writes under that ID are rejected. Repeated cancellation is safe. Cancellation does not increment execution count, alter valve, alter physical feedback, or clear a recovery latch. A subsequent deliberate valve operation needs a fresh ID. A robot coordinator must separately decelerate its motion and retain suction while holding an object.

`DeviceClient.command()` performs a write and then reads status. If the write response is lost, it reconciles by reading status without issuing another valve write. It returns only when that snapshot confirms the same ID and requested valve (or cancellation). Otherwise it raises `UncertainCommandError`. Never turn that error into a retry with a new ID: retain the original ID and reconcile or enter hold. Valid Modbus exception replies raise `DeviceProtocolError` with `exception_code`; other protocol errors derive from `DeviceError`. `status()` can raise `TimeoutError`; a command whose status cannot be obtained raises `UncertainCommandError`.

Python deadlines cover connect/send/header/body for each numeric-localhost RPC; a command/cancel uses at most two RPC timeout budgets plus scheduling overhead. C++ uses nonblocking POSIX sockets and an absolute poll deadline of 200 ms per RPC. It accepts a numeric IPv4 host, avoiding unbounded DNS lookup. Neither client retries under a new ID. Idle server connections expire after one second. `stop()` closes active sockets, including sessions on a subsequently restarted server object.

## Reproducible faults and C++ interoperation

`inject_fault(kind)` arms one fault: `drop_ack` drops the next write reply after durable application; `delay_response` delays the next reply by 500 ms; `interrupt_after_intent` leaves the next new valve write pending and drops its reply, modelling a crash window. The interruption also latches uncertainty immediately. Dropping a cancellation ACK follows the same no-release rule. These are actual TCP faults, not alternate in-memory client implementations.

```bash
g++ -std=c++17 -Wall -Wextra -Werror -O2 cpp/modbus_client.cpp -o work/modbus_client
# Keep the emulator running in another process; use its actual printed port.
work/modbus_client 127.0.0.1 PORT status
work/modbus_client 127.0.0.1 PORT command 41 1
work/modbus_client 127.0.0.1 PORT cancel 41
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_device.py
```

Successful C++ operations emit JSON; errors return nonzero with a message on stderr. After any ambiguous command failure, reconcile the original ID before taking another action. Tests compile the C++ program and exercise it against the running TCP emulator, including duplicate suppression, cancellation, and conflict rejection.
