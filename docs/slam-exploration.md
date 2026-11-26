# 빈 점유 지도에서의 온라인 탐색

시드 31의 별도 운동학 시행에서 첫 스캔으로 좌표계를 정의하고, 차체를 한 바퀴 회전시켜 0.07 m 점유 격자를 만들었다. 휠 엔코더로 자세를 예측하고 LiDAR를 현재 회전의 첫 스캔 또는 주행 중 이전에 관측한 스캔과 정합했다. 탐색기는 미관측 셀에 인접한 자유 셀을 경계로 삼아, 경계에 가까운 접근점을 현재 지도에서 선택했다. 차체 반경 0.24 m와 여유 0.13 m를 더한 전 구간이 관측된 자유 공간을 통과하는 접근점만 선택했다. 각 접근점에 도착해 정지하면 새로 회전 스캔을 수집하고 지도를 갱신했다. [실험 코드](../scripts/run_slam_exploration.py) · [탐색기](../src/pickloop/slam_exploration.py)

| 지도 갱신 시점 | 관측된 자유 셀 |
| --- | ---: |
| 출발 위치에서 첫 회전 스캔 직후 | 5,926 |
| 첫 탐색 경로 주행 후 | 5,965 |
| 두 번째 탐색 경로 주행 후 | 8,476 |

두 경로를 합해 2.704 m 이동했고, 실제 이동 선분을 기준 형상과 비교한 최소 차체 여유는 0.222 m였다. 두 번째 접근점에서 지도 갱신을 마친 후 정지했으며 상태는 `FRONTIER_BUDGET_REACHED`였다. 이 상태는 두 구간의 실험 한도를 채웠다는 뜻이다. 최종 자유 셀은 첫 지도보다 순 2,550개 늘었다. 기준 형상과 시뮬레이터 자세는 센서 생성과 주행 후 평가에 사용했다. 탐색 결과는 단일 환경에서 정지·회전 후 지도 갱신을 반복한 두 구간에 해당한다. [결과와 출처 해시](../runs/slam-exploration/summary.json) · [단계별 격자](../runs/slam-exploration/grids.npz) · [40 ms 표본](../runs/slam-exploration/samples.jsonl.gz)

## 재현

```bash
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python scripts/run_slam_exploration.py --out-dir /tmp/pickloop-slam-exploration
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python -m pytest tests/test_slam_exploration.py tests/test_slam_drive.py -q
```
