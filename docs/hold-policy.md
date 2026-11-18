# Terminal stop and valve policy

`HELD` is a task outcome, not an instruction to leave every actuator on. Motion stopping and suction disposition are separate decisions. The coordinator first performs a controlled motion stop and logs its `STOP_REPORT`. It then calls `resolve_terminal_valve` and logs the returned decision as `HOLD_POLICY`. Retry exhaustion is a separate `RETRY_EXHAUSTED` event; it must not be inferred from the valve state.

```python
from pickloop.stop_policy import resolve_terminal_valve

# Caller owns stopping, exclusive output access, and any later physics settling.
stop_report = cell.stop_motion()
policy = resolve_terminal_valve(
    client, reason, command_id,
    output_uncertain=uncertain_output_or_cancel,
    carrying=controller_believes_payload_is_held,
)
command_id = policy['command_id']
```

The helper never advances physics and never uses evaluator object truth. It obtains a new TCP status response at the terminal boundary. A previously cached RPC, local valve value, or task outcome cannot authorize release.

OFF is eligible only when every condition below is true:

- No output/cancellation uncertainty veto and no unresolved controller carrying belief.
- The fresh status reports `error='none'`, boolean valve/attachment/cancellation fields, finite numeric pressure, and valid execution metadata.
- Both `ack_id` and `max_command_id` equal the coordinator's last attempted command ID. ID zero is accepted only for the initial state.
- Attachment feedback is explicitly false and absolute pressure is strictly below **10 kPa**. Thus detached −6 kPa is weak vacuum and may be switched off; −10 kPa or stronger vacuum retains the output conservatively. Positive pressure at or above the same magnitude also fails the weak-pressure check.

This 10 kPa threshold is an explicit conservative policy for the current simplified simulator. It does not certify a real payload's weight, residual adhesion, sensor accuracy, or hardware release safety. In a physical controller, release qualification needs validated sensing and a hardware interlock appropriate to the gripper/load.

When eligible and currently ON, the helper issues exactly one explicit OFF with the next uint32 ID. It validates the command response and another fresh TCP status response: both must acknowledge that ID as the maximum, valve must be OFF, cancellation must be false, and unloaded feedback must remain valid. The helper does not claim pressure has decayed after the write; the physics owner may perform a guarded settlement interval and collect subsequent evidence separately.

| `action` | Meaning |
| --- | --- |
| `RETAIN` | No output write was issued. This preserves the current output; it does not prove it is ON. |
| `ALREADY_OFF` | Fresh status already confirmed unloaded output OFF; no redundant command was issued. |
| `OFF_CONFIRMED` | One new OFF command was acknowledged and independently re-read with unloaded feedback. |
| `OFF_UNCONFIRMED` | One OFF was attempted, but its application/final state is unconfirmed. The output may already be OFF; do not describe this as retained suction. |

Reports include a machine-readable `reason`, original `terminal_reason`, `status_before`, latest `status` (or null when unavailable), `release_attempted`, and `output_uncertain`. `command_id` is the last ID attempted by the helper and is safe to assign back to the coordinator's counter. `next_command_id` is the next candidate above the IDs observed/attempted, or null at uint32 exhaustion. It is not permission to retry after uncertainty. Never convert an ambiguous OFF into a new-ID OFF retry; reconcile the original attempted ID or enter operator hold.

Reasons containing `UNCERTAIN`, `UNCONFIRMED`, or `RECOVERY_REQUIRED`, and an explicit `output_uncertain` flag, always veto release even if a later snapshot looks weak/detached. `SEAL_NOT_CONFIRMED` is a physical seal failure rather than a command-acknowledgement failure: an acknowledged ON with confirmed detached weak vacuum can therefore be shut OFF. A `carrying=True` veto protects a cancellation where controller load belief contradicts weak/detached feedback. A successfully acknowledged cancellation tombstone does not itself prohibit a subsequent deliberate unloaded OFF under a fresh ID.

## Concurrency and freshness boundary

The caller must own the controller exclusively and keep physics/feedback paused throughout this helper. The current engine's per-run private emulator and synchronous stopped `Cell` meet that boundary when integrated accordingly. A new network response is a fresh controller snapshot; the Modbus status bank does not carry a sensor timestamp, so the caller must also ensure the feedback originated from the stopped physical step.

FC03 status and FC16 output commands are separate transactions. Existing Modbus does not offer an atomic “OFF only if still detached and weak” operation. A competing writer can invalidate snapshots; expected ACK/max checks and final verification detect many such races, while a reused competing ID is rejected. They cannot prevent a physical load from attaching between the last read and OFF if external dynamics or writers continue. Such a deployment requires an atomic controller-side interlock or equivalent validated physical release guard before using automatic unloaded OFF. Do not treat this helper as that hardware interlock.

## Verification

Dedicated tests use the actual persistent TCP emulator for detached −6 kPa shutdown, loaded cancellation retention, uncertain-applied output retention, fresh-status timeouts, recovery latches, cancellation tombstones, ID exhaustion, and competing clients. Test adapters additionally inject lost result delivery and malformed status data; assertions check the real emulator's valve and execution count.

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_stop_policy.py tests/test_device.py
```
