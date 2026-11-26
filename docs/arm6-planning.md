# 6축 팔이 장애물을 우회하는 경로

회전 관절 6개의 시작·목표 자세를 고정하고 그 사이에 지그를 놓았다. 직선 관절 보간은 중간 자세에서 지그에 10.83 mm 침투했다. 양방향 RRT-Connect가 찾은 경로는 세 시드에서 모두 목표에 닿았다. 팔과 바닥·받침대·지그, 인접하지 않은 링크 쌍의 거리를 MuJoCo에서 계산했다. 고정 셀의 4축 주문 피킹과 별도로 실행한 관절 공간 계획 실험이다. [모델과 계획기](../src/pickloop/arm6_planning.py) · [시드별 경유점과 충돌 쌍](../runs/arm6-planning/result.json)

| 탐색 시드 | 탐색 반복 | 최소 형상 간 거리¹ |
|---|---:|---:|
| 3 | 35 | 12.21 mm |
| 17 | 14 | 8.52 mm |
| 41 | 35 | 11.90 mm |

¹ 각 경로에서 검사한 형상 간 최소 거리다. 관절 보간 간격은 계획 시 최대 0.020 rad, 결과 검증 시 최대 0.005 rad이며 요구 여유는 8 mm다. 지그를 제거하면 직선 경로를 반환했다. 관절 범위 밖의 시작점, 지그 안의 목표점, 탐색 예산 0을 각각 거절했다. 이 결과는 한 장면의 이산 자세 검사에 한정되며 경로 전체의 연속 충돌·속도·하중별 토크를 보증하지 않는다.

별도로 한 정지 자세에서 6번 모터에 12 N·m를 요청했다. 설정한 한계 8 N·m에서 MuJoCo 관절 액추에이터 센서와 시뮬레이터 내부 힘 벡터가 모두 8 N·m를 기록했다. 실제 관절 토크를 확인하려면 로봇 컨트롤러 피드백 또는 교정된 토크 센서가 필요하다. [시험 결과](../runs/arm6-planning/result.json) · [실물 계측 조건](hardware-acceptance.md)

## 재현

저장소 루트에서 프로젝트 의존성을 설치한 Python으로 실행한다.

```bash
PYTHONPATH=src python -m pickloop.arm6_planning --output /tmp/pickloop-arm6.json
cmp /tmp/pickloop-arm6.json runs/arm6-planning/result.json
PYTHONPATH=src python -m pytest tests/test_arm6_planning.py -q
```

동일 파일 비교에 사용한 MuJoCo와 NumPy 버전은 각각 3.3.7과 2.2.6이다.
