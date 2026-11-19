"""Two low-charge simulated vehicles share a dock in the known-map kinematic plant."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import platform
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .mobile import DT, ROOT, FleetScheduler, MobileHold, MobileMap, MobileSimulation, metrics_from_rows, wrap

CAPACITY_WH = 48.
LOW_SOC = .20
RESUME_SOC = .205
MIN_PILOT_V = 24.
MAX_PILOT_V = 27.
MIN_CURRENT_A = .25
MAX_CURRENT_A = 2.
STABLE_SAMPLES = 5
HANDSHAKE_TIMEOUT_S = 1.
TOPUP_TIMEOUT_S = 40.
SCENARIOS = ('normal', 'no_contact', 'low_voltage', 'no_current', 'current_interrupt')


@dataclass
class Battery:
    initial_soc: float
    delivered_wh: float = 0.

    @property
    def soc(self):
        return self.initial_soc + self.delivered_wh / CAPACITY_WH


class DockCircuit:
    """Ideal pad switch, pilot tap and current shunt on a resistive DC circuit."""

    def __init__(self, fault):
        self.fault = fault
        self.powered_s = 0.

    def read(self, truth, dock, soc, relay_closed):
        dx, dy = truth[0] - dock[0], truth[1] - dock[1]
        c, s = math.cos(dock[2]), math.sin(dock[2])
        axial, lateral = c * dx + s * dy, -s * dx + c * dy
        aligned = abs(axial) <= .045 and abs(lateral) <= .035 and abs(wrap(truth[2] - dock[2])) <= .05
        contact = bool(aligned and self.fault != 'no_contact')
        pilot = (19. if self.fault == 'low_voltage' else 25.2) if contact else 0.
        open_circuit_v = 23. + 3. * soc
        broken_path = self.fault == 'no_current' or (self.fault == 'current_interrupt' and self.powered_s >= 2.)
        current = 0.
        if contact and relay_closed and not broken_path:
            current = min(MAX_CURRENT_A, max(0., (pilot - open_circuit_v) / .9))
        terminal = open_circuit_v + current * .12
        return dict(contact=contact, pilot_v=pilot, terminal_v=terminal, current_a=current,
                    relay_closed=relay_closed)


def request_for_waiters(sim, waiters, state):
    for waiting in waiters:
        if sim.fleet.acquire(waiting, sim.t):
            raise MobileHold('PREMATURE_ZONE_HANDOVER')
        sim.emit('CHARGER_BUSY', sim.t, waiting, state,
                 {'owner': sim.fleet.owner, 'occupied': sorted(sim.fleet.occupied),
                  'waiting_pose_m_rad': sim.truth[waiting].tolist(), 'waiting_wheel_m_s': sim.wheels[waiting].tolist()})


def charge_while_parked(sim, robot, battery, port, waiters=()):
    """Switch power after contact and pilot confirmation. Log each metered interval."""
    state = 'WAIT_CONTACT'
    entered = sim.t
    consecutive = 0
    relay = False
    try:
        while True:
            if not sim.fleet.valid(robot, sim.t) or sim.fleet.occupied != {robot}:
                raise MobileHold('CHARGER_ZONE_INTERLOCK')
            if max(map(abs, sim.wheels[robot])) > 1e-9:
                raise MobileHold('CHARGER_POSE_INTERLOCK')
            sim.tick(robot, [0., 0.], state)
            dock = sim.docking_measurements(robot)
            accepted = dock['accepted'] and dock['position_sigma_m'] <= .025
            at_rest = max(map(abs, sim.wheels[robot])) <= 1e-9
            lease = sim.fleet.valid(robot, sim.t)
            if not (lease and sim.fleet.occupied == {robot}):
                raise MobileHold('CHARGER_ZONE_INTERLOCK')
            if not (accepted and at_rest):
                raise MobileHold('CHARGER_POSE_INTERLOCK')

            measurement = port.read(sim.truth[robot], sim.world.config['dock_m_rad'], battery.soc, relay)
            current = measurement['current_a']
            battery.delivered_wh += measurement['terminal_v'] * current * DT / 3600.
            if relay:
                port.powered_s += DT
            sim.emit('ELECTRICAL_SAMPLE', sim.t, robot, state,
                     dict(**measurement, dt_s=DT, soc=battery.soc, dock_accepted=accepted, at_rest=bool(at_rest),
                          lease_valid=lease, zone_owner=sim.fleet.owner, zone_occupied=sorted(sim.fleet.occupied)))
            contact = measurement['contact']
            pilot_ok = MIN_PILOT_V <= measurement['pilot_v'] <= MAX_PILOT_V
            current_ok = MIN_CURRENT_A <= current <= MAX_CURRENT_A
            if state != 'WAIT_CONTACT' and not contact:
                raise MobileHold('CONTACT_LOST')
            if relay and not pilot_ok:
                raise MobileHold('PILOT_LOST')

            if state == 'CHARGING':
                if not current_ok:
                    raise MobileHold('CURRENT_LOST')
                if battery.soc >= RESUME_SOC:
                    sim.emit('TOPUP_COMPLETE', sim.t, robot, state,
                             {'soc': battery.soc, 'delivered_wh': battery.delivered_wh})
                    return
                if sim.t - entered >= TOPUP_TIMEOUT_S:
                    raise MobileHold('TOPUP_TIMEOUT')
                continue

            if state == 'WAIT_CONTACT':
                ok, event, next_state, timeout = contact, 'CONTACT_VERIFIED', 'VERIFY_PILOT', 'CONTACT_TIMEOUT'
            elif state == 'VERIFY_PILOT':
                ok, event, next_state, timeout = pilot_ok, 'PILOT_VERIFIED', 'VERIFY_CURRENT', 'PILOT_TIMEOUT'
            else:
                ok, event, next_state, timeout = current_ok, 'CURRENT_VERIFIED', 'CHARGING', 'CURRENT_TIMEOUT'
            consecutive = consecutive + 1 if ok else 0
            if consecutive == STABLE_SAMPLES:
                sim.emit(event, sim.t, robot, state, measurement)
                if event == 'CURRENT_VERIFIED':
                    request_for_waiters(sim, waiters, 'CHARGING')
                state, entered, consecutive = next_state, sim.t, 0
                relay = state in ('VERIFY_CURRENT', 'CHARGING')
            elif sim.t - entered >= HANDSHAKE_TIMEOUT_S - 1e-9:
                raise MobileHold(timeout)
    finally:
        # An instantaneous open-circuit read has zero duration and transfers no energy.
        off = port.read(sim.truth[robot], sim.world.config['dock_m_rad'], battery.soc, relay_closed=False)
        sim.emit('PORT_DISABLED', sim.t, robot, state, off)
        if off['current_a'] != 0.:
            raise MobileHold('CURRENT_AFTER_DISABLE')


def run_dock_fleet(seed=0, scenario='normal', out_dir='runs/dock-charging', mission_id=None,
                   initial_soc=(.198, .199)):
    if scenario not in SCENARIOS:
        raise ValueError('unsupported charging scenario')
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if len(initial_soc) != 2 or not all(0 <= value <= 1 for value in initial_soc):
        raise ValueError('initial_soc must contain two fractions between zero and one')
    mission_id = mission_id or f'charge-{scenario}-{seed}-{uuid.uuid4().hex[:8]}'
    if not mission_id or Path(mission_id).name != mission_id or mission_id in ('.', '..'):
        raise ValueError('mission_id must be a single path component')
    directory = Path(out_dir) / mission_id
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / 'telemetry.jsonl.gz'
    world = MobileMap.load()
    fleet = FleetScheduler(world.config['robot_starts_m_rad'])
    batteries = {robot: Battery(soc) for robot, soc in zip(('amr-1', 'amr-2'), initial_soc)}
    queue = sorted((robot for robot, pack in batteries.items() if pack.soc < LOW_SOC),
                   key=lambda robot: (batteries[robot].soc, robot))
    completed, rows = [], []
    reason = None
    with gzip.GzipFile(filename=archive, mode='wb', mtime=0) as handle:
        def emit(event, now, robot=None, state=None, data=None):
            row = dict(sequence=len(rows), mission_id=mission_id, mission_time_s=round(now, 6), event=event,
                       robot=robot, state=state, data=data or {})
            rows.append(row)
            handle.write((json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n').encode())

        sim = MobileSimulation(world, seed, emit, fleet, threading.Event(), 240., time.monotonic() + 120.)
        for robot, battery in batteries.items():
            emit('SOC_EVALUATED', sim.t, robot, data={'soc': battery.soc, 'trigger_soc': LOW_SOC})
        for robot in queue:
            emit('CHARGE_REQUESTED', sim.t, robot, 'QUEUED', {'soc': batteries[robot].soc, 'trigger_soc': LOW_SOC})

        try:
            for index, robot in enumerate(queue):
                if not fleet.acquire(robot, sim.t):
                    raise MobileHold('ZONE_UNAVAILABLE')
                emit('ZONE_RESERVED', sim.t, robot, 'NAVIGATING', {'expires_s': fleet.expires})
                waiters = queue[index + 1:]
                request_for_waiters(sim, waiters, 'QUEUED')
                sim.drive(robot, world.config['dock_m_rad'], 'NAVIGATING')
                sim.require_dock(robot)
                request_for_waiters(sim, waiters, 'DOCK_OCCUPIED')
                port = DockCircuit(scenario if index == 0 else 'normal')
                charge_while_parked(sim, robot, batteries[robot], port, waiters)
                sim.drive(robot, world.config['robot_starts_m_rad'][robot], 'RETURN_TO_PARK')
                sim.release_clear_zone(robot)
                completed.append(robot)
        except MobileHold as exc:
            reason = str(exc)
            emit('STOP_COMMAND', sim.t, state='HELD', data={'reason': reason, 'zone_owner_retained': fleet.owner})
            sim.brake_to_rest()
        status = 'HELD' if reason else 'COMPLETED'
        emit('TERMINAL', sim.t, state=status, data={'reason': reason})
    inputs = ['src/pickloop/dock_charging.py', 'src/pickloop/mobile.py', 'scripts/run_dock_charging.py',
              'configs/mobile-map.json']
    result = dict(schema_version=1, mission_id=mission_id, seed=seed, scenario=scenario, status=status,
                  reason=reason, simulation='kinematic two-AMR fleet and ideal DC port', completed=completed,
                  batteries={robot: dict(initial_soc=b.initial_soc, final_soc=b.soc, delivered_wh=b.delivered_wh)
                             for robot, b in batteries.items()}, mobile_metrics=metrics_from_rows(rows),
                  final_zone={'owner': fleet.owner, 'occupied': sorted(fleet.occupied)},
                  provenance={'source_files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                               for name in inputs},
                              'telemetry_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                              'python': platform.python_version(), 'numpy': np.__version__})
    (directory / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result
