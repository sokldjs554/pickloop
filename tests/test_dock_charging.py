"""Independent reductions of the two-vehicle charging mission's raw samples."""
import gzip
import hashlib
import json
import math
import threading
import time

import pytest

from pickloop import dock_charging as charging
from pickloop import mobile


def run(tmp_path, scenario='normal', **kwargs):
    result = charging.run_dock_fleet(seed=0, scenario=scenario, out_dir=tmp_path, **kwargs)
    archive = tmp_path / result['mission_id'] / 'telemetry.jsonl.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == result['provenance']['telemetry_sha256']
    with gzip.open(archive, 'rt') as handle:
        rows = [json.loads(line) for line in handle]
    assert [row['sequence'] for row in rows] == list(range(len(rows)))
    assert all(a['mission_time_s'] <= b['mission_time_s'] for a, b in zip(rows, rows[1:]))
    for robot, battery in result['batteries'].items():
        delivered = sum(row['data']['terminal_v'] * row['data']['current_a'] * row['data']['dt_s'] / 3600
                        for row in rows if row['event'] == 'ELECTRICAL_SAMPLE' and row['robot'] == robot)
        assert battery['delivered_wh'] == pytest.approx(delivered, abs=1e-10)
        assert battery['final_soc'] == pytest.approx(battery['initial_soc'] + delivered / charging.CAPACITY_WH)
    for i, row in enumerate(rows):
        if row['event'] != 'ELECTRICAL_SAMPLE' or not row['data']['relay_closed']:
            continue
        data = row['data']
        sample = rows[i - 1]
        assert sample['event'] == 'SAMPLE' and sample['mission_time_s'] == row['mission_time_s']
        assert sample['data']['wheel_m_s'] == [0., 0.] and sample['robot'] == row['robot']
        assert sample['data']['zone_owner'] == row['robot'] and sample['data']['zone_occupied'] == [row['robot']]
        assert data['dock_accepted'] and data['at_rest'] and data['lease_valid']
        assert data['zone_occupied'] == [row['robot']] and data['zone_owner'] == row['robot']
        assert data['contact'] and charging.MIN_PILOT_V <= data['pilot_v'] <= charging.MAX_PILOT_V
    return result, rows


def test_low_soc_vehicles_take_turns_and_resume_after_measured_topup(tmp_path):
    result, rows = run(tmp_path)
    assert result['status'] == 'COMPLETED', result
    assert result['completed'] == ['amr-1', 'amr-2']
    assert result['final_zone'] == {'owner': None, 'occupied': []}
    assert result['mobile_metrics']['collision_count'] == 0
    assert result['mobile_metrics']['zone_max_simultaneous_occupants'] == 1
    gates = ['CHARGE_REQUESTED', 'ZONE_RESERVED', 'DOCK_ACCEPTED', 'CONTACT_VERIFIED', 'PILOT_VERIFIED',
             'CURRENT_VERIFIED', 'TOPUP_COMPLETE', 'PORT_DISABLED', 'ZONE_RELEASED']
    for robot in result['completed']:
        sequence = [next(row['sequence'] for row in rows if row['event'] == gate and row['robot'] == robot)
                    for gate in gates]
        assert sequence == sorted(sequence)
        assert result['batteries'][robot]['initial_soc'] < charging.LOW_SOC
        assert result['batteries'][robot]['final_soc'] >= charging.RESUME_SOC
        assert any(row['event'] == 'SAMPLE' and row['state'] == 'RETURN_TO_PARK' and row['robot'] == robot
                   and max(map(abs, row['data']['wheel_m_s'])) > .1 for row in rows)
        off = next(row for row in rows if row['event'] == 'PORT_DISABLED' and row['robot'] == robot)
        assert off['data']['current_a'] == 0 and off['data']['relay_closed'] is False
    release = next(row['sequence'] for row in rows if row['event'] == 'ZONE_RELEASED')
    assert all(row['sequence'] > release for row in rows if row['robot'] == 'amr-2' and row['event'] == 'SAMPLE')
    assert [(row['state'], row['data']['owner']) for row in rows if row['event'] == 'CHARGER_BUSY'] == [
        ('QUEUED', 'amr-1'), ('DOCK_OCCUPIED', 'amr-1'), ('CHARGING', 'amr-1')]


@pytest.mark.parametrize('scenario,reason,passed_gate,forbidden_gate', [
    ('no_contact', 'CONTACT_TIMEOUT', 'DOCK_ACCEPTED', 'CONTACT_VERIFIED'),
    ('low_voltage', 'PILOT_TIMEOUT', 'CONTACT_VERIFIED', 'PILOT_VERIFIED'),
    ('no_current', 'CURRENT_TIMEOUT', 'PILOT_VERIFIED', 'CURRENT_VERIFIED'),
    ('current_interrupt', 'CURRENT_LOST', 'CURRENT_VERIFIED', 'TOPUP_COMPLETE'),
])
def test_fault_is_observed_and_blocks_waiting_vehicle(tmp_path, scenario, reason, passed_gate, forbidden_gate):
    result, rows = run(tmp_path, scenario)
    assert result['status'] == 'HELD' and result['reason'] == reason
    assert result['completed'] == [] and result['final_zone'] == {'owner': 'amr-1', 'occupied': ['amr-1']}
    assert any(row['event'] == passed_gate for row in rows)
    assert not any(row['event'] == forbidden_gate or row['event'] == 'ZONE_RELEASED' for row in rows)
    assert not any(row['robot'] == 'amr-2' and row['event'] == 'SAMPLE' for row in rows)
    off = next(row for row in rows if row['event'] == 'PORT_DISABLED')
    assert off['data']['current_a'] == 0 and off['data']['relay_closed'] is False
    assert (result['batteries']['amr-1']['delivered_wh'] > 0) == (scenario == 'current_interrupt')
    assert result['batteries']['amr-2']['delivered_wh'] == 0


def test_independent_contact_geometry_and_relay():
    dock = [4., 2., math.pi / 2]
    port = charging.DockCircuit('normal')
    for pose in ([4., 2.1, dock[2]], [4.08, 2., dock[2]], [4., 2., dock[2] + .1]):
        measured = port.read(pose, dock, .2, relay_closed=True)
        assert not measured['contact'] and measured['current_a'] == 0
    assert port.read(dock, dock, .2, relay_closed=False)['current_a'] == 0
    assert port.read(dock, dock, .2, relay_closed=True)['current_a'] > 0


def test_ready_vehicles_stay_parked(tmp_path):
    result, rows = run(tmp_path, initial_soc=(charging.LOW_SOC, .8))
    assert result['status'] == 'COMPLETED' and result['completed'] == []
    assert [r['event'] for r in rows] == ['SOC_EVALUATED', 'SOC_EVALUATED', 'TERMINAL']


@pytest.mark.parametrize('condition,reason', [('expired_lease', 'CHARGER_ZONE_INTERLOCK'),
                                              ('moving_wheel', 'CHARGER_POSE_INTERLOCK'),
                                              ('bad_estimate', 'CHARGER_POSE_INTERLOCK')])
def test_rejects_inhibited_charge_before_current_flows(condition, reason):
    world = mobile.MobileMap.load()
    fleet = mobile.FleetScheduler(world.config['robot_starts_m_rad'])
    events = []
    sim = mobile.MobileSimulation(world, 0, lambda *args: events.append(args), fleet,
                                  threading.Event(), 240., time.monotonic() + 120.)
    robot = 'amr-1'
    dock = world.config['dock_m_rad']
    sim.truth[robot][:] = dock
    estimator = sim.estimators[robot]
    estimator.pose[:] = dock
    estimator.cov *= .001
    assert fleet.acquire(robot, sim.t)
    fleet.enter(robot, sim.t)
    if condition == 'expired_lease':
        sim.t = fleet.expires
    elif condition == 'moving_wheel':
        sim.wheels[robot][:] = .01  # Inside the navigation stop tolerance but still rolling.
    else:
        estimator.pose[0] += .2
    with pytest.raises(mobile.MobileHold, match=reason):
        charging.charge_while_parked(sim, robot, charging.Battery(.198), charging.DockCircuit('normal'))
    assert events[-1][0] == 'PORT_DISABLED' and events[-1][4]['current_a'] == 0.
    assert not any(row[0] == 'ELECTRICAL_SAMPLE' for row in events)
