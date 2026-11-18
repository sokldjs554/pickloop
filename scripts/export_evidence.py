#!/usr/bin/env python3
"""Export existing execution evidence for the static site; never run a simulator.

Sources are copied byte-for-byte. Descriptions are derived from recorded results,
and basic cross-file checks fail closed rather than publishing invented outcomes.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE_NAMES = ('normal-seed-0-final', 'blocked-seed-1-final', 'contention-seed-2-final')


def read_json(path):
    return json.loads(path.read_text())


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mobile_metrics(rows):
    """Independent stdlib reduction of the logged metrics; no engine import."""
    samples = [row for row in rows if row['event'] == 'SAMPLE']
    distance = 0.; last = {}; square_errors = []; speeds = []; accelerations = []
    for row in samples:
        data = row['data']; robot = row['robot']
        truth = data['truth_pose_m_rad']; estimate = data['estimate_pose_m_rad']
        if robot in last:
            distance += math.dist(truth[:2], last[robot][:2])
        last[robot] = truth
        square_errors.append(math.dist(truth[:2], estimate[:2]) ** 2)
        speeds.extend(abs(value) for value in data['wheel_m_s'])
        accelerations.extend(abs(value) for value in data['wheel_accel_m_s2'])
    return {
        'sample_count': len(samples), 'distance_m': distance,
        'localization_rmse_m': math.sqrt(sum(square_errors) / len(square_errors)) if square_errors else None,
        'max_wheel_speed_m_s': max(speeds, default=0.),
        'max_wheel_acceleration_m_s2': max(accelerations, default=0.),
        'collision_count': sum(row['data']['collision'] for row in samples),
        'sim_duration_s': max((row['mission_time_s'] for row in rows), default=0.),
        'zone_max_simultaneous_occupants': max((len(row['data']['zone_occupied']) for row in samples), default=0),
    }


def validate_mobile(directory):
    result = read_json(directory / 'result.json')
    raw = directory / 'trajectory.jsonl'; rows = read_rows(raw)
    require(hashlib.sha256(raw.read_bytes()).hexdigest() == result['provenance']['trajectory_sha256'],
            f'{directory.name}: raw trajectory hash mismatch')
    for key, value in mobile_metrics(rows).items():
        actual = result['metrics'][key]
        require(actual is None if value is None else actual is not None and math.isclose(actual, value, abs_tol=1e-10, rel_tol=1e-10),
                f'{directory.name}: metric mismatch: {key}')
    starts = [row for row in rows if row['event'] == 'PICK_STARTED']
    require(result['physics_picker'] == bool(starts), f'{directory.name}: picker invocation metadata mismatch')
    require(result['metrics']['collision_count'] == 0, f'{directory.name}: unexpected flagged collisions')
    require(result['metrics']['zone_max_simultaneous_occupants'] <= 1, f'{directory.name}: zone occupancy conflict')
    if result['status'] == 'COMPLETED':
        events = [row['event'] for row in rows]
        ordered = ['DOCK_ACCEPTED', 'PICK_STARTED', 'PICK_FINISHED', 'ZONE_RELEASED', 'NEXT_TASK_COMPLETED']
        require([events.index(event) for event in ordered] == sorted(events.index(event) for event in ordered),
                f'{directory.name}: invalid gate order')
        pick = result['pick_result']
        require(pick['job_id'] == result['job_id'] and pick['success'], f'{directory.name}: physical job mismatch')
        require(pick['metrics']['verified_by_vision'] and pick['metrics']['verified_by_truth'],
                f'{directory.name}: missing placement verification')
    else:
        require(not starts and result['pick_result'] is None, f'{directory.name}: unexpected picker execution')
    return result, rows


def export(dest=ROOT / 'web/data'):
    dest = Path(dest); evidence_dir = dest / 'evidence'
    ros = ROOT / 'ros2/evidence'
    summary = read_json(ros / 'integration-summary.json')
    actions = {}
    for name in ('normal', 'cancel', 'duplicate', 'final-replay'):
        rows = read_rows(ros / f'action-{name}.jsonl')
        actions[name] = next(row['result'] for row in reversed(rows) if 'result' in row)
        if name != 'final-replay':
            require(actions[name] == summary[name]['result'], f'ROS {name}: summary disagrees with raw result')
            require(sum('feedback' in row for row in rows) == summary[name]['feedback_messages'],
                    f'ROS {name}: feedback count mismatch')
    normal, cancel = actions['normal'], actions['cancel']
    require(normal['action_status'] == 4 and normal['success'] and normal['status'] == 'COMPLETED', 'ROS normal not verified')
    require(cancel['action_status'] == 5 and cancel['status'] == 'CANCELLED', 'ROS cancellation not confirmed')
    require(actions['duplicate']['run_id'] == normal['run_id'] == actions['final-replay']['run_id'], 'ROS duplicate/replay run ID mismatch')
    require(actions['final-replay'] == summary['final_image_replay'], 'ROS final-image replay summary mismatch')
    topics = read_json(ros / 'topics.json')
    require(topics == summary['topics'], 'ROS sensor probe differs from summary')
    require(all(topics['counts'].get(name, 0) > 0 for name in ('clock', 'events', 'joints', 'camera')), 'missing observed DDS topic')
    require('Summary: 2 packages finished' in (ros / 'docker-build.log').read_text(), 'missing successful ROS colcon build')
    live = ROOT / 'runs/live' / normal['run_id']
    live_result = read_json(live / 'result.json')
    require(live_result['success'] and live_result['metrics']['verified_by_vision'] and live_result['metrics']['verified_by_truth'],
            'ROS-backed physics result not independently verified')
    cancel_live = ROOT / 'runs/live' / cancel['run_id']
    cancel_result = read_json(cancel_live / 'result.json')
    require(cancel_result['status'] == 'CANCELLED' and not cancel_result['success'], 'ROS core cancellation not recorded')
    mobile = {name: validate_mobile(ROOT / 'runs/mobile' / name) for name in MOBILE_NAMES}
    mission, mission_rows = mobile[MOBILE_NAMES[0]]
    blocked = mobile[MOBILE_NAMES[1]][0]; contention = mobile[MOBILE_NAMES[2]][0]
    require(blocked['reason'] == 'NO_PATH' and contention['reason'] == 'ZONE_WAIT_TIMEOUT', 'unexpected negative mobile outcomes')
    require(blocked['status'] == contention['status'] == 'HELD', 'negative mobile runs not held')
    mobile_audit = read_json(ROOT / 'runs/mobile/verification.json')
    for row in mobile_audit:
        result = mobile[row['mission_id']][0]
        require(row['metrics'] == result['metrics'] and row['source_sha256'] == result['provenance']['source_sha256'],
                'saved mobile audit is stale')
    dock = next(row['data'] for row in mission_rows if row['event'] == 'DOCK_ACCEPTED')
    device_log = ROOT / 'web/data/evidence/device-tests.txt'
    mobile_log = ROOT / 'web/data/evidence/mobile-tests.txt'
    require(re.search(r'test_cpp_client_uses_same_tcp_device\s+PASSED', device_log.read_text()), 'missing actual C++ socket test pass')
    require(' failed' not in device_log.read_text() and ' failed' not in mobile_log.read_text(), 'focused evidence log contains failures')
    require('test_zone_lease_expiry_fences_owner_and_cannot_reassign_occupied_zone PASSED' in mobile_log.read_text(), 'missing lease expiry test evidence')

    # All outcome checks above finish before publishing or copying any evidence.
    evidence_dir.mkdir(parents=True, exist_ok=True)
    inventory = []
    def copy(source, name):
        source = Path(source); target = evidence_dir / name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        require(hashlib.sha256(target.read_bytes()).hexdigest() == original_hash, f'export copy changed: {name}')
        inventory.append({'url': 'data/evidence/' + name, 'source': str(source.relative_to(ROOT)),
                          'sha256': original_hash, 'bytes': source.stat().st_size})
        return 'data/evidence/' + name
    copied = {}
    for name in ('docker-build.log', 'integration-summary.json', 'action-normal.jsonl', 'action-cancel.jsonl',
                 'action-duplicate.jsonl', 'action-final-replay.jsonl', 'topics.json', 'interface.log', 'graph.log'):
        copied['ros-' + name] = copy(ros / name, 'ros2-' + name)
    for name in ('result.json', 'events.jsonl', 'run.json'):
        copied['ros-physics-' + name] = copy(live / name, 'ros2-physics-' + name)
    for name in ('result.json', 'events.jsonl'):
        copied['ros-cancel-physics-' + name] = copy(cancel_live / name, 'ros2-cancel-physics-' + name)
    copied['ros-camera'] = copy(live / 'frames/00000-camera.jpg', 'ros2-normal-camera-sample.jpg')
    copied['device-log'] = copy(device_log, 'device-tests.txt')
    copied['device-source'] = copy(ROOT / 'cpp/modbus_client.cpp', 'modbus-client.cpp')
    copied['device-test-source'] = copy(ROOT / 'tests/test_device.py', 'device-tests.py')
    copied['mobile-log'] = copy(mobile_log, 'mobile-tests.txt')
    for name in MOBILE_NAMES:
        prefix = {'normal-seed-0-final': 'mobile-normal', 'blocked-seed-1-final': 'mobile-blocked',
                  'contention-seed-2-final': 'mobile-contention'}[name]
        for file in ('result.json', 'trajectory.jsonl', 'trajectory.svg'):
            copied[prefix + '-' + file] = copy(ROOT / 'runs/mobile' / name / file, prefix + '-' + file)
    pick_dir = ROOT / 'runs/mobile' / MOBILE_NAMES[0] / 'pick' / mission['pick_result']['run_id']
    for name in ('result.json', 'events.jsonl'):
        copied['mobile-pick-' + name] = copy(pick_dir / name, 'mobile-pick-' + name)
    for name in ('device-protocol.md', 'ros2-integration.md', 'mobile-extension.md', 'execution-evidence.md'):
        copied[name] = copy(ROOT / 'docs' / name, name)
    copied['mobile-audit'] = copy(ROOT / 'runs/mobile/verification.json', 'mobile-verification.json')

    def link(label, key):
        return {'label': label, 'url': copied[key]}
    counts = topics['counts']; metrics = mission['metrics']
    cards = [
        {
            'title': 'ROS 2 · 실제 DDS 작업 실행',
            'description': f"정상 action은 {normal['status']}, 초기 취소는 core 확인 후 {cancel['status']}로 종료했습니다. 중복 job ID와 최종 이미지 재접속도 같은 run_id({normal['run_id']})를 반환했습니다. 취소는 파지 전 실험이며, ROS 작업→HTTP 브리지입니다. ros2_control·실물 로봇 제어 검증은 아닙니다.",
            'links': [link('정상 action 원문', 'ros-action-normal.jsonl'), link('취소 action 원문', 'ros-action-cancel.jsonl'),
                      link('중복 작업 원문', 'ros-action-duplicate.jsonl'), link('최종 이미지 재접속', 'ros-action-final-replay.jsonl'),
                      link('연결된 정상 물리 작업 결과', 'ros-physics-result.json'), link('core 취소 결과', 'ros-cancel-physics-result.json'),
                      link('DDS 검증 요약', 'ros-integration-summary.json')],
        },
        {
            'title': 'ROS 2 · 빌드와 센서 메시지 수신',
            'description': f"Jazzy colcon 빌드에서 두 패키지를 생성했습니다. 별도 DDS probe는 clock {counts['clock']}개, 상태 {counts['events']}개, 관절 {counts['joints']}개, 카메라 {counts['camera']}개를 수신했습니다. 원문은 수신 횟수와 대표 샘플 메타데이터이며 rosbag 전체 스트림은 아닙니다. JPEG 링크는 정상 작업의 실제 관측 파일입니다. TF·CameraInfo·하드웨어 드라이버는 구현 범위 밖입니다.",
            'links': [link('실제 colcon 빌드 로그', 'ros-docker-build.log'), link('DDS 센서 probe 원문', 'ros-topics.json'),
                      link('action·topic graph', 'ros-graph.log'), link('생성된 action 인터페이스', 'ros-interface.log'),
                      link('관측 JPEG 원본', 'ros-camera'), link('정상 작업 프레임·이벤트 원문', 'ros-physics-run.json')],
        },
        {
            'title': 'C++ · 실제 Modbus TCP 소켓 검증',
            'description': '독립 C++17 클라이언트를 g++로 컴파일하고 별도 subprocess로 실행해 TCP 에뮬레이터에 명령·중복·ACK 유실 복구·취소·상태 요청을 검증했습니다. verbose 실행 로그와 해당 테스트·클라이언트 소스를 함께 제공합니다. 실물 PLC 미연결이며, 밸브 명령 수락이 압력·흡착 성공을 뜻하지 않습니다.',
            'links': [link('실제 TCP·C++ 테스트 실행 로그', 'device-log'), link('C++ POSIX 소켓 클라이언트', 'device-source'),
                      link('컴파일·subprocess 검증 코드', 'device-test-source'), link('프로토콜·복구 계약', 'device-protocol.md')],
        },
        {
            'title': '모바일 · 추정 주행 → 도킹 → 같은 피킹 작업',
            'description': f"seed 0: {metrics['distance_m']:.3f} m 이동, 위치 RMSE {metrics['localization_rmse_m'] * 1000:.3f} mm. 도킹 추정 오차 {dock['estimate_error_m'] * 1000:.2f} mm / 진실 평가 오차 {dock['truth_error_m'] * 1000:.2f} mm를 확인한 뒤 같은 job ID로 실제 MuJoCo 피킹을 실행했습니다. zone 이탈 후 두 번째 로봇의 재배치가 완료됐습니다. 알려진 지도 EKF이며 SLAM은 아닙니다. 차동구동 운동학이고 바퀴 접촉 물리가 아닙니다. 이동체와 팔 셀은 분리된 시뮬레이터입니다.",
            'links': [link('실제 계산 궤적', 'mobile-normal-trajectory.svg'), link('encoder·LiDAR·EKF 전체 원문', 'mobile-normal-trajectory.jsonl'),
                      link('미션·도킹·메트릭 결과', 'mobile-normal-result.json'), link('동일 작업의 물리 피킹 결과', 'mobile-pick-result.json'),
                      link('물리 피킹 이벤트', 'mobile-pick-events.jsonl'), link('단위·좌표계·구현 한계', 'mobile-extension.md')],
        },
        {
            'title': '모바일 · 막힌 경로와 zone 경합에서 보류',
            'description': f"seed 1은 NO_PATH, seed 2는 {contention['metrics']['sim_duration_s']:g}초 대기 후 ZONE_WAIT_TIMEOUT으로 보류했습니다. 두 경우 피킹 호출은 0회입니다. 정상 실행의 최대 기록 zone 점유는 {metrics['zone_max_simultaneous_occupants']}대, 충돌 판정 샘플은 {metrics['collision_count']}개였습니다. 별도 테스트는 lease 만료 후 점유·불확실 zone 재할당 거부와 취소 시 감속 정지를 확인합니다. 소규모 단일 프로세스 스케줄러이며 실차 안전 인증이 아닙니다.",
            'links': [link('막힌 경로 결과', 'mobile-blocked-result.json'), link('막힌 경로 이벤트', 'mobile-blocked-trajectory.jsonl'),
                      link('zone 경합 결과', 'mobile-contention-result.json'), link('zone 경합 센서·점유 원문', 'mobile-contention-trajectory.jsonl'),
                      link('lease·취소·추정 테스트 실행 로그', 'mobile-log'), link('raw metric·SHA 재검증', 'mobile-audit'),
                      link('재생성 방법·검증 범위', 'execution-evidence.md'),
                      {'label': '배포 원문의 SHA 목록', 'url': 'data/evidence/manifest.json'}],
        },
    ]
    manifest = {
        'schema_version': 1, 'files': inventory,
        'checks': {'ros_action_raw_summary_match': True, 'ros_duplicate_run_identity': True,
                   'ros_sensor_probe_summary_match': True, 'cpp_subprocess_socket_test_recorded_pass': True,
                   'mobile_raw_metrics_and_sha_match': True, 'mobile_gate_order_and_job_identity': True,
                   'mobile_negative_picker_calls': 0},
        'scope': 'Recorded local simulation and TCP/DDS software execution; physical robot disconnected. Known-map EKF, no SLAM; kinematics, no wheel/contact physics; task bridge, no ros2_control; separate mobile/fixed-cell worlds.',
    }
    (evidence_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    for card in cards:
        for item in card['links']:
            require((dest / item['url'].removeprefix('data/')).is_file(), f"missing website link: {item['url']}")
    (dest / 'evidence.json').write_text(json.dumps(cards, indent=2, ensure_ascii=False))
    print(f'Exported {len(cards)} evidence cards, {len(inventory)} byte-verified files, {sum(file["bytes"] for file in inventory):,} bytes to {dest}')
    return cards


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=ROOT / 'web/data')
    export(parser.parse_args().dest)
