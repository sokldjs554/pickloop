# 동결 조건 비교 평가

원본 120개 실행, 60개 짝. 모든 수치는 result.json에서 생성.

| 조건 | 기준 완료 | 복구 완료 | 기준 평균 s | 복구 평균 s |
|---|---:|---:|---:|---:|
| calibration_error | 0/5 | 5/5 | 4.08 | 27.29 |
| communication_delay | 0/5 | 5/5 | 3.78 | 26.89 |
| connection_loss | 5/5 | 5/5 | 16.56 | 16.56 |
| depth_missing | 0/5 | 5/5 | 0.45 | 20.25 |
| drop | 0/5 | 5/5 | 7.82 | 31.11 |
| normal | 5/5 | 5/5 | 16.56 | 16.56 |
| occlusion | 0/5 | 5/5 | 0.45 | 20.25 |
| path_blocked | 0/5 | 5/5 | 5.91 | 19.69 |
| stale_observation | 0/5 | 5/5 | 0.45 | 20.25 |
| suction_once | 0/5 | 5/5 | 3.98 | 27.09 |
| suction_permanent | 0/5 | 0/5 | 3.98 | 19.98 |
| unknown | 0/5 | 0/5 | 0.45 | 2.77 |

시간 단위는 simulated seconds. 실패 작업도 실제 종료까지 분모에 포함. 현장 처리량/ROI가 아니다.
복구율 = 첫 시도 작업 미완료 중 재시도 후 최종 완료 / 첫 시도 작업 미완료. 영구 실패와 unknown 주문도 분모에 포함.
first_attempt_pick_success는 첫 시도 압력 유지 상태의 lift 확인이고, first_attempt_success는 첫 시도 최종 배치 완료다.
완료 비율 Wilson 95% 구간은 이 합성 조건 표본의 불확실성 설명이며 실물 일반화 근거가 아니다.
