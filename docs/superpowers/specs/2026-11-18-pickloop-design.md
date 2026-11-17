# PickLoop 설계 (2026-11-18)

요청: PyBrain AI 제출용, 물체를 실제로 운반·배치하고 실패를 감지해 복구하거나 보류하는 재현 가능한 로봇 시스템. 사용자는 조사에 멈추지 말고 구현·평가까지 진행하도록 명시했다. 아래 구현 선택은 에이전트의 판단이며 사용자 경력으로 주장하지 않는다.

## 선택과 범위
- MuJoCo CPU + Python: 강체 접촉, 관절 구동, RGB-D 렌더링을 로컬에서 반복 실행. Isaac Sim은 GPU/대용량 런타임 부담으로 제외. 둘 다 현실의 흡착 누설을 자동으로 검증하지 않는다.
- 자체 4축 SCARA (회전 2, 수직 1, 손목 회전 1): 상면 흡착 작업의 최소 관절 구조. 특정 상용 팔의 성능/충돌 인증을 주장하지 않는다. 이동을 qpos 순간 변경으로 구현하지 않고 position actuator를 물리 시간 적분한다.
- 깊이 기반 연결 성분으로 instance proposal, 학습한 CNN embedding으로 SKU 분류/unknown rejection, RGB-D 상면의 3D 중심 추정. synthetic 2 SKU와 미등록 품목. 합성 훈련·검증·최종 split의 seed 영역 분리. 실제 창고 인식 일반화는 미검증.
- 고정 카메라 외부 보정: 실제 2D-3D 대응점 + solvePnP, 재투영 오차 확인. hand-eye로 부르지 않는다.
- Behavior Tree로 Observe→Plan→Approach→Seal→Lift→Transport→Release→Verify. 재관측과 제한 재시도, 완료/보류/취소 terminal. 첫 시도만 실행하는 기준과 동일 초기 seed/장애로 비교.
- TCP Modbus FC03/FC16 실제 프레임을 사용하는 컨트롤러 에뮬레이터 + C++ 클라이언트. command id/ack/status/cancel + 영속 중복 억제. 미확인 타임아웃 이후 새 ID로 재전송 금지.
- FastAPI local live API + static replay dashboard. 공개 Sites에는 검증된 실행 파일을 재생하고, 로컬에서는 새 작업 실행 지원. 재생에서 조건 재계산 버튼을 활성화하지 않는다.
- ROS2 bridge는 설치 가능성 검증 후 실행 증거와 함께 제공. 모바일 확장은 고정형 완료 이후 수행. SLAM/충전/실물 배포를 수행하지 않으면 공백으로 표시.

## 경계와 계약
세계/베이스: 우수계 x 오른쪽, y 셀 뒤쪽, z 위. 길이 m, 각 rad, 시간 s. camera_optical x 오른쪽/y 아래/z 전방. T_base_camera는 optical→base 4x4, 카메라 K pixel. TCP는 흡착컵 접촉면. RGB uint8 HWC; depth float32 axial metres. Observation: run_id, observation_id, sim_time, monotonic_received_ns, RGB, depth, K, calibration id. 제어기는 RGB-D/K/T와 관절 encoder, 그리퍼 pressure/state만 읽으며 객체 truth는 evaluator/흡착 접촉 물리 내부만 접근.

수직 접근은 이미지로 얻은 물체 상면으로 계획. 관절 제한/속도/가속도/충돌을 표본화해 검사하고 궤적 실행에서 tracking timeout을 감시. 순응성/누설을 단순화한 suction은 근접+상면 정렬+압력 성립시에만 weld constraint를 켜고 힘 한계를 넘거나 장애 주입 시 해제한다. 위치 도착만으로 성공하지 않음: lift pressure + optical disappearance/source 및 목적지 재인식, release 이후 정지 관측으로 검증. 평가기는 별도 truth로 정확한 SKU/박스 내 물체/낙하를 검사한다.

로그 JSONL: schema_version/run_id/job_id/event_id/sim_time/wall_elapsed_s/state/event/attempt/observation_id/data; 한 frame manifest가 동일 step의 camera/scene/log 이벤트를 연결. SQLite job ledger로 재시작 후 미완료 작업을 HOLD_RECOVERY_REQUIRED로 전환. 자동 물리 재실행 금지. Cancel은 동작 중 확인, 속도 제한 정지 및 들고 있는 물체 자동 해제 금지.

## 사전 평가 규칙
개발 seed 0..99, 최종 seed 1000..1004. 정상/가림/깊이누락/보정오차/흡착실패/통신지연/낙하/경로차단/영구흡착실패/unknown. baseline 최대 1회, recovery 최대 3회, 각 작업 sim timeout 60s + wall timeout 90s. 완료는 올바른 물체가 지정 bin 내부에 정지하고 손에서 분리됐을 때. 시간은 성공/실패 모두 종료까지 포함, timeout은 예산으로 처리. 복구율 분모는 첫 시도 실패 작업. 처리량은 전체 sim elapsed 시간에 대한 완료 수; wall 처리량 별도. seed별 및 조건별 분산 공개. 최종 결과를 보고 튜닝하면 그 결과는 개발로 이관하고 새 holdout manifest를 생성한다.

## 제출물/한계
소스, 고정 dependency 환경, 테스트/CI, 원본 로그, 재생 데모/실행 영상, 결과 생성 스크립트, 대응표, 기여 기록, 면접 문서. 실물 robot/PLC/PCB fabrication, 안전 인증 및 현장 throughput 검증은 별도. 사용자 PCB 경험은 답변 전 상세 미확인. 기존 저장소 코드 재사용 시 파일/commit/license를 반드시 기록.
