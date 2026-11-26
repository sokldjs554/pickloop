# 재구성한 LiDAR 지도에서의 폐루프 주행

운동학 시뮬레이터에서 [6.373 m A* 경로](slam-navigation.md)를 별도 시행으로 재주행했다. 첫 스캔의 원점과 방향에서 출발했고, 휠 엔코더와 실시간 36빔 LiDAR로 추정한 자세를 사용해 매 0.04초마다 휠 명령을 갱신했다. 동일한 69개 키프레임의 엔코더와 거리 데이터로 점유 격자와 스캔 기준 자세를 다시 만들었다. 주행 중에는 0.32초마다 인접 키프레임에 현재 스캔을 정합했다. 시뮬레이터 기준 자세와 장애물 형상은 센서 생성과 주행 후 평가에 사용했다. [제어기](../src/pickloop/slam_drive.py) · [실험 코드](../scripts/run_slam_drive.py)

| 시행 | 결과 | 이동 거리 | 종료 시 목표 오차 | 최소 차체 여유 |
| --- | --- | ---: | ---: | ---: |
| 재구성 경로 | `GOAL_REACHED` | 6.372 m | 0.043 m | 0.249 m |
| 지도 작성 후 장애물 추가 | `LIDAR_STOP` | 1.060 m | — | 0.103 m |
| 점유 셀에 목표 설정 | `NO_PATH` | 0 m | — | — |
| 미관측 셀에 목표 설정 | `NO_PATH` | 0 m | — | — |

경로 중심선에서 벗어난 최대 거리는 0.044 m였다. 70회의 스캔 정합을 자세 추정에 반영했고, 동일 시행의 추정 위치 RMSE는 0.025 m였다. 같은 엔코더 기록을 독립적으로 적분한 위치의 RMSE는 0.228 m였다. 주행 전 전체 경로에 반경 0.24 m와 계획 여유 0.13 m를 검사했다. 주행 중에는 추정 자세에서 정지 거리를 확보할 수 있도록 감속했고, 새 장애물을 발견한 시행에서는 제동 명령을 유지해 정지했다. 차체 여유는 기준 형상과 실제 이동의 각 적분 선분 사이 거리에서 차체 반경을 빼 계산했다. 결과는 지도 시드 7, 주행 시드 23의 단일 차체와 위치 목표에 해당한다. [수치와 출처 해시](../runs/slam-drive/summary.json) · [40 ms 표본](../runs/slam-drive/samples.jsonl.gz)

## 재현

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python scripts/run_slam_drive.py --out-dir /tmp/pickloop-slam-drive
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python -m pytest tests/test_slam_drive.py tests/test_slam_navigation.py tests/test_lidar_slam.py -q
```
