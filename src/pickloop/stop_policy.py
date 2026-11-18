"""Fail-closed terminal valve policy for a stopped, exclusively owned controller.

No physics is advanced here. The caller must stop motion, pause physics/feedback
changes, and exclude other valve writers for the complete decision. Modbus has
no atomic conditional release primitive; see docs/hold-policy.md.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

MAX_COMMAND_ID = 0xFFFFFFFF
WEAK_PRESSURE_KPA = 10.0
_STATUS_FIELDS = ('ack_id', 'valve', 'pressure_kpa', 'attached', 'error',
                  'execution_count', 'max_command_id', 'cancelled')


def _valid_id(value):
    return type(value) is int and 0 <= value <= MAX_COMMAND_ID


def _snapshot(status):
    """Keep reports JSON-safe even when a broken adapter returns invalid data."""
    if not isinstance(status, Mapping):
        return None
    result = {}
    for field in _STATUS_FIELDS:
        if field not in status:
            continue
        value = status[field]
        if value is None or type(value) in (str, bool, int):
            result[field] = value
        elif type(value) is float and math.isfinite(value):
            result[field] = value
        else:
            result[field] = None
    return result


def _status_problem(status, expected_id):
    if not isinstance(status, Mapping):
        return 'INVALID_STATUS'
    if status.get('error') != 'none':
        return 'DEVICE_STATUS_ERROR'
    if (not _valid_id(status.get('ack_id')) or
            not _valid_id(status.get('max_command_id')) or
            status['ack_id'] != expected_id or status['max_command_id'] != expected_id):
        return 'ACK_NOT_EXCLUSIVE_OR_UNCONFIRMED'
    if any(type(status.get(field)) is not bool for field in ('valve', 'attached', 'cancelled')):
        return 'INVALID_STATUS'
    if not _valid_id(status.get('execution_count')):
        return 'INVALID_STATUS'
    pressure = status.get('pressure_kpa')
    if type(pressure) not in (int, float) or not math.isfinite(pressure):
        return 'INVALID_PRESSURE'
    return None


def _load_problem(status):
    if status['attached']:
        return 'ATTACHMENT_CONFIRMED'
    if abs(status['pressure_kpa']) >= WEAK_PRESSURE_KPA:
        return 'PRESSURE_MAY_SUPPORT_LOAD'
    return None


def resolve_terminal_valve(client, reason, command_id, *, output_uncertain=False, carrying=False):
    """Return a JSON-safe decision; never issue OFF based on cached/local state.

    ``command_id`` is the coordinator's last attempted ID, or zero before any
    command. A confirmed unloaded terminal may allocate exactly one new OFF ID.
    ``command_id`` in the result is the last ID this helper attempted; the caller
    may assign it back to its counter. ``next_command_id`` is the next candidate
    above observed/attempted IDs (None at exhaustion), not retry authorization.

    RETAIN means no output write, not proof that the current output is ON.
    OFF_UNCONFIRMED means one OFF may have applied; never claim retention and
    never issue another fresh-ID write to resolve that uncertainty.
    """
    valid_id = _valid_id(command_id)
    report = dict(action='RETAIN', reason='INVALID_COMMAND_ID', terminal_reason=str(reason),
                  status_before=None, status=None, command_id=command_id if valid_id else None,
                  next_command_id=command_id + 1 if valid_id and command_id < MAX_COMMAND_ID else None,
                  release_attempted=False, output_uncertain=output_uncertain is not False)

    def finish(action, decision_reason, *, uncertain=None):
        report['action'] = action
        report['reason'] = decision_reason
        if uncertain is not None:
            report['output_uncertain'] = uncertain
        known_max = report['command_id']
        for snapshot in (report['status_before'], report['status']):
            if snapshot and _valid_id(snapshot.get('max_command_id')):
                known_max = max(known_max, snapshot['max_command_id'])
        report['next_command_id'] = known_max + 1 if known_max < MAX_COMMAND_ID else None
        return report

    if not valid_id:
        return report
    # Read again at the terminal boundary; a previous successful RPC or a local
    # carrying flag cannot substitute for this new device snapshot.
    try:
        before = client.status()
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'[:512]
        return finish('RETAIN', 'FRESH_STATUS_UNAVAILABLE', uncertain=True)
    report['status_before'] = _snapshot(before)
    report['status'] = report['status_before']

    upper_reason = str(reason).upper()
    if output_uncertain is not False or any(token in upper_reason for token in
                                           ('UNCERTAIN', 'UNCONFIRMED', 'RECOVERY_REQUIRED')):
        return finish('RETAIN', 'OUTPUT_UNCERTAINTY_VETO', uncertain=True)
    problem = _status_problem(before, command_id)
    if problem:
        return finish('RETAIN', problem, uncertain=True)
    if carrying is not False:
        return finish('RETAIN', 'CONTROLLER_LOAD_UNCONFIRMED')
    problem = _load_problem(before)
    if problem:
        return finish('RETAIN', problem)
    if before['valve'] is False:
        return finish('ALREADY_OFF', 'UNLOADED_OUTPUT_ALREADY_OFF', uncertain=False)
    if command_id == MAX_COMMAND_ID:
        return finish('RETAIN', 'COMMAND_ID_EXHAUSTED')

    off_id = command_id + 1
    report['command_id'] = off_id  # reserve even if the response is lost
    report['release_attempted'] = True
    try:
        response = client.command(off_id, False)
    except Exception as error:
        report['status'] = None  # the pre-write snapshot is no longer current
        report['error'] = f'{type(error).__name__}: {error}'[:512]
        return finish('OFF_UNCONFIRMED', 'OFF_COMMAND_UNCONFIRMED', uncertain=True)
    report['status'] = _snapshot(response)
    if (_status_problem(response, off_id) or response['valve'] is not False or
            response['cancelled'] or _load_problem(response)):
        return finish('OFF_UNCONFIRMED', 'OFF_ACK_NOT_CONFIRMED', uncertain=True)
    try:
        after = client.status()
    except Exception as error:
        report['status'] = None
        report['error'] = f'{type(error).__name__}: {error}'[:512]
        return finish('OFF_UNCONFIRMED', 'OFF_VERIFICATION_UNAVAILABLE', uncertain=True)
    report['status'] = _snapshot(after)
    if (_status_problem(after, off_id) or after['valve'] is not False or
            after['cancelled'] or _load_problem(after)):
        return finish('OFF_UNCONFIRMED', 'OFF_VERIFICATION_MISMATCH', uncertain=True)
    return finish('OFF_CONFIRMED', 'FRESH_CONFIRMED_UNLOADED_OFF', uncertain=False)
