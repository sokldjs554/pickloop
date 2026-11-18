# 재현한 실패와 수정 근거

## 궤적 사이의 명령 불연속

최초 구현은 각 경로를 현재 encoder 위치에서 새로 시작했다. 이전 명령과 작은 위치차가 발생해 seed4 정상 동작의 관절 가속도가4.407rad/s²를 넘었고, 운반 중 흡착 상실 후 재시작에서는100rad/s² 이상도 관측됐다. 이는 위치 도착만 확인하면 놓치는 문제다.

현재 구현은 이전 actuator command에서 이어지는 quintic 경로, 연속 감속 정지, 카탈로그 질량의 중력 보상을 적용한다. `test_measured_free_motion_and_recovery_limits`는 정상과 낙하 복구에서 실제 측정 회전 가속도≤3rad/s², 수직≤0.8m/s²를 검사한다. `test_cancel_during_lift_brakes_and_keeps_vacuum`은 움직이며 들고 있는 상태의 취소 후 물체 유지도 확인한다.

## 경로 차단 후 돌아오는 경로

첫 수정은 물체 운반만 높은 경로로 우회했다. 내려놓은 뒤 초기 높이로 돌아오다가 같은 장애물에 막혀, 실제 배치가 되었어도 보류로 끝났다. seed4의 TRANSPORT PATH_BLOCKED 후 RELEASE PATH_BLOCKED가 증거였다.

돌아오는 경로도 복구 clearance를 사용하도록 수정했다. `test_blocked_path_replans_with_payload_clearance`는 실제 물체를 옮겨 놓고 금지 충돌 없이1회 재시도로 완료되는지 검사한다.

## 실행됐지만 확인되지 않은 장치 명령

독립 리뷰에서 ACK와 후속 status가 모두 유실되면, 장치는 valve=True인데 물리 시뮬레이션은 client.command 반환 뒤에만 이를 적용하는 문제가 확인됐다. 실제 장치의 미확인 실행 상태를 과소평가하는 오류였다.

plant는 영속 장치 출력에서 독립적으로 밸브를 읽는다. `test_executed_but_unconfirmed_valve_still_affects_physics`는 실제 TCP에서 ACK를 끊고 status를 지연시켜, 실행 횟수1·흡착 유지·DEVICE_UNCERTAIN 보류를 동시에 검사한다. 재전송으로 성공 처리하지 않는다.

## 충돌하면서 정지할 때 결과가 사라짐

운반 중 사전 검사 이후 장애물을 올리는 재현에서, stop 과정의 충돌 예외가 다시 발생해 result.json이 없었다. 현재는 금지 접촉을 latch/계수하며 bounded stop report를 남긴다. `test_dynamic_collision_has_durable_terminal_evidence`는 실제 동적 장애물에 의한 충돌 이후 HELD 결과·충돌 지표·원본 JSON이 존재하는지 검사한다.

## 서버 재시작 후 중단 작업 조회

SQLite에는 TRANSPORT가 남았지만 서버 GET은 run.json만 읽어404를 반환했다. 현재는 단일 runner lease를 확보한 시작 절차가 중단 작업을 HOLD_RECOVERY_REQUIRED로 바꾸고, GET이 ledger 상태도 반환한다. `test_restart_reports_interrupted_job_without_resubmission`은 재제출 없이 조회되는지 검사한다.

## 보류와 밸브 ON을 같은 것으로 취급한 정책

기존의 “실패하면 진공 유지”만으로는 빈 그리퍼의 지속 흡착 실패에서도 출력이 켜진 채 남고, 반대로 단순 일괄 OFF는 하중이나 미확인 장치 실행을 해제할 수 있었다. 현재는 동작 정지와 밸브 결정을 분리한다. 정지 후 신선한 TCP 상태에서 빈 상태·약한 압력·ACK/max ID가 모두 확인되고 하중 추정/출력 불확실성이 없을 때만 OFF를 확인한다. 부착/불확실성은 보수적으로 유지·보류한다. 복구 초기화도 같은 규칙을 쓴다.

`STOP_REPORT`, `RETRY_EXHAUSTED`, `HOLD_POLICY` 또는 `RECOVERY_OUTPUT_POLICY`를 각각 확인한다. `RETAIN`은 출력 쓰기 없음이고, `OFF_UNCONFIRMED`는 OFF 적용 여부 미확정이므로 “흡착 유지 확인”으로 표시하지 않는다. [정책·실제 TCP 시험의 범위](hold-policy.md), [`test_stop_policy.py`](../tests/test_stop_policy.py)에 lost result·장치 상태 malformed·경쟁 writer 등 경계를 남겼다. 실제 센서 timestamp와 atomic release interlock은 구현되지 않아 실물 인수 항목으로 남는다.

## 1회 대 3회 비교로 복구 효과를 과대 해석한 문제

과거 `runs/final` 120회는 baseline 1회와 recovery 최대 3회를 비교했다. 추가 시도와 목표 재관측·경로 변경이 동시에 달라지므로 해당 완료율 차이를 복구 판단만의 효과라고 할 수 없다. 기록은 과거 결과로 보존하고 새 평가와 합산하지 않는다.

현재는 baseline 1회 외에 naive/reobserve/recovery의 동일 최대 3회·sim 60초/wall 90초 비교를 둔다. naive는 캐시 목표·고정 경로, reobserve는 새 목표·고정 경로, recovery는 새 목표·재시도 높이 변경이다. 목표가 없던 naive도 관측을 재시도하며 모든 정책의 안전 검사를 유지한다. 이는 특정 정책의 분해 실험이며 일반 재시도 최적성 비교는 아니다.

또한 새 조건 JSON은 장애를 시도 번호와 무관한 절대 sim 시간표로 고정하고 배치·물리·센서 범위를 개발/heldout에서 나눈다. `condition=None`의 과거·기본 CLI는 첫 관측/첫 시도 기반이므로 구분한다. 초기 개발 중 소스 변경을 동결 검사가 감지해 중단한 부분 배치는 최종 결과에서 제외한다. 현재 `runs/ablation-heldout` 576회 배치를 완료했으며 효과와 실패를 모두 원본에 남겼다. [명세·조건·재현 명령](ablation-protocol.md)을 따른다.

## 검토 상태

독립 리뷰의 중요 항목3개를 수정했고 각각 실패 재현→통과를 확인했다. 낙하 지표는 강제/과부하 suction loss와 지지면에서40mm 넘게 떠 있는 해제를 함께 계수하도록 명확히 했다. 충돌 지표는 모든 접촉이 아니라 금지 침투 episode임을 공개했다. 계획 직전 stale frame의 ValueError도 bounded recovery용 OperationError로 변환했다.

`verification/review-revision-all-tests.txt`와 `verification/review-revision-ui.txt`는 수정 후 검증 원본이다. 시험 통과와 576회 정책 성능 평가는 별도 증거다. ROS2 PID1 종료 문제의 수정 전후 실제 기록은 `ros2/evidence/`와 [ROS2 문서](ros2-integration.md)에 보존했다.
