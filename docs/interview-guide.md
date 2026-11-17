# 면접에서 설명할 설계 판단과 코드 읽기 순서

첫 설명은 “동일한 조건에서 실패 복구가 없는 실행과 제한된 복구 실행을 비교하고, 카메라·장치·물리 확인을 통해 **올바른 물체의 실제 운반·배치 또는 보류**를 증명하는 시뮬레이션 프로젝트”로 시작한다. 실물 로봇 배포·현장 처리량·ROI 경험으로 소개하지 않는다. 이번 코드는 AI 에이전트가 생성·실행했으며 사용자 기여는 요구 정의·피드백과 별도 PADS 보드 경험이다. [기여 구분](contributions.md)을 먼저 읽고 직접 검토한 범위만 말한다.

## 1. 데모에서 먼저 보여줄 세 장면

1. **정상:** SKU-RED-A 주문→RGB-D 분할·임베딩 품목 선택→베이스 좌표→경로→흡착 압력→lift/운반→release→두 시점 영상의 박스 내 안정 확인. 작업 ID로 camera/scene/event를 대조한다.
2. **일시 흡착 실패:** 같은 seed와 suction_once의 baseline/recovery를 나란히 확인한다. 실패 reason, attempt, pressure, 재관측/재계획을 보여주고 최종 결과를 원본 `events.jsonl`/`result.json`로 연다. 모션 목표 도달은 피킹 성공이 아니다.
3. **복구 불가:** suction_permanent에서 최대 3회 후 HELD. 반복을 무한히 늘려 성공으로 꾸미지 않는다. unknown·stale·장치 불확실도 역시 성공 처리하지 않는지 살펴본다.

기록 재생 모드는 이미 실행된 파일을 보여준다. 새 seed 계산은 실행 가능한 local API에서만 수행한다. 실제 브라우저 공개 URL·영상·수치는 최종 제출 산출물과 원본 결과를 사용하며 이 문서에 가상의 값/화면을 추가하지 않는다.

## 2. 코드 읽기 순서

| 순서 | 파일/함수 | 설명할 경계와 직접 확인할 질문 |
|---|---|---|
| 1 | [`types.py`](../src/pickloop/types.py), [`geometry.py`](../src/pickloop/geometry.py) | RGB uint8·depth m·각도 rad·시각 s/ns·`T_base_camera` 방향. 오래된 관측/shape/depth를 어디서 거부하는가? |
| 2 | [`simulation.py`](../src/pickloop/simulation.py): `Cell.observe`, `move_to`, `_vacuum_physics` | 실제 `mj_step`으로 물체가 움직이는가? 흡착 결합 성립/해제 조건과 collision sample, 보정 입력은 무엇인가? |
| 3 | [`perception.py`](../src/pickloop/perception.py), [`vision_model.py`](../src/pickloop/vision_model.py) | 제어에 simulator IDs/poses를 넘기지 않는 경계, depth proposal과 crop-only 모델·unknown 거부 |
| 4 | [`engine.py`](../src/pickloop/engine.py): `Action`, `Recovery`, `Controller.verify` | 실제 BT 상태/메모리, 재시도 1→3회 정책, 물체 운반 중 복구, visual verification과 독립 evaluator 분리 |
| 5 | [`device.py`](../src/pickloop/device.py), [`modbus_client.cpp`](../cpp/modbus_client.cpp) | FC03/FC16 frame, intent/apply crash window, ACK 손실 대조, cancel tombstone; 새 ID retry가 위험한 이유 |
| 6 | [`journal.py`](../src/pickloop/journal.py), [`server.py`](../src/pickloop/server.py) | job ID+config 충돌·미완료 재시작 hold·단일 runner·cancel·source provenance |
| 7 | [`tests/`](../tests/), [`models/vision_metrics.json`](../models/vision_metrics.json), 실행 원본 | 시험은 실제 TCP·MuJoCo를 어디까지 쓰는가? oracle component test와 통합 제어를 어떻게 구별하는가? |
| 8 | [`web/app.js`](../web/app.js), [`mobile.py`](../src/pickloop/mobile.py), [`ros2/`](../ros2/) | 공통 frame/log 시각, replay/live 구분; 모바일 known-map EKF와 ROS2 action bridge의 실제 범위 |

## 3. 핵심 선택과 대안

**MuJoCo CPU와 4축 셀:** GPU 없는 실행 환경에서 실제 강체·접촉·RGB-D·반복 seed 평가를 재현하기 위한 선택이다. Isaac Sim 동시 설치는 범위에 넣지 않았다. 6/7축 일반 manipulator보다 SCARA의 해석 IK와 제한 경로가 작고 검토 가능하지만, 일반 6D 파지·복잡한 bin picking·협동 안전을 검증하지 않는다.

**고정 카메라 외부 보정:** 영상 기준점과 알려진 베이스 기준점으로 OpenCV PnP를 추정하고 재투영 gate를 적용한다. 단순 오프셋이 아니지만 AX=XB 이동 말단 hand-eye도 아니다. 실제 설치에는 distortion·기준점 측량·다중 pose/불확실도·보정 drift 시험이 더 필요하다.

**학습 범위:** 기하 depth 연결 성분이 proposal을 만들고 실제 학습 CNN이 RGB crop으로 유사 두 품목을 구분한다. 범용 detector/segmenter를 미세조정했다고 말하지 않는다. RGB 평균 baseline은 공간 무늬를 잃는 의도적으로 단순한 비교이며, 학습된 고성능 검출기 대비 우월성 근거가 아니다. synthetic-only, validation에 본 unknown 계열, inspected development 재사용·새 final seed 경계를 설명한다. export는 TorchScript이며 TensorRT/INT8/NPU 배포가 아니다. [모델·평가 원본 설명](vision-model.md)

**파지 모델:** 접근·정렬·압력 조건이 성립할 때 weld로 강체 결합하는 흡착 근사다. 실제 컵 변형/누설/표면/유체를 해결한 모델은 아니다. 위치 도달과 seal·lift·이송·release·안정 확인을 분리하고, pressure feedback은 valve 명령의 성공 고정 응답이 아니라 물리에서 갱신한다.

**계획·복구:** 해석 IK+quintic time scaling+표본 충돌 검사와 제한된 높이/관측 재시도다. 일반 OMPL 탐색이 아니다. BT 자체는 py_trees 기능이고, phase·실패 분류·bounded decorator·보류 정책은 신규 구현이다. 재시도 횟수 외에 sim/wall deadline, cancel과 device uncertainty의 즉시 종료를 설명한다.

**Python/C++ 역할:** Python이 인식·학습·실험·셀·BT/API 통합을 담당한다. C++17은 별도 프로세스에서 실제 Modbus frame과 deadline을 구현하고 같은 emulator와 상호운용한다. C++ 코드를 Python 뒤에서 제어 루프에 숨겨 썼다거나 실시간 OS/하드 실시간 지터를 검증했다고 주장하지 않는다.

**Exactly-once 대신 보류 가능한 계약:** ACK 손실 후 새 ID로 구동을 재시도하면 중복 물리 작동을 일으킬 수 있다. 동일 ID/상태를 대조하고 crash가 pending을 남기면 hold한다. cancel은 release가 아니며 motion stop과 진공/지지는 별도다. 실제 전원 상실 시 journal만으로 물체를 지킬 수 없다는 [실물 계획](hardware-acceptance.md)을 설명한다.

**ROS2와 모바일 범위:** ROS2는 custom task action→HTTP core·실제 기록 camera/joint/clock/events bridge다. TF/CameraInfo·MoveIt·Nav2·ros2_control 전체 스택이 아니다. 모바일는 알려진 map의 A*·wheel 운동학·EKF 측위·raycast LiDAR·구역 배정/도킹 gate이고 SLAM/실제 충전이 아니다. 모바일 정상 미션은 실제 `engine.run_job`을 호출해 배치 완료 뒤 구역을 나가 다음 robot reposition까지 실행했다. [모바일 최종 결과](../runs/mobile/normal-seed-0-final/result.json)·[실행/한계](mobile-extension.md)를 확인한다. ROS2 정상 action·확인된 cancel·중복 job 재전송과 실제 DDS topic 수신은 [증거 요약](../ros2/evidence/integration-summary.json)에 있다. ROS cancel은 초기 접근 중 시험으로, 부착 하중 상태의 ROS 취소까지 실행한 증거는 아니다.

## 4. 평가에서 방어해야 할 질문

- 성공은 controller visual gate와 evaluator truth가 모두 맞아야 한다. simulator truth는 물리 구현·평가에만 쓰고 인식/IK 선택에 전달하지 않는다. [`test_physics.py`](../tests/test_physics.py)의 known-coordinate 시험은 명시적 oracle component test다.
- baseline/recovery는 seed·장면·초기 위치·fault가 같아야 한다. 동작이 달라진 뒤 센서 경로가 달라질 수 있으며 이는 정책 차이의 결과다. 개선을 전체 모델 우수성이나 실물 ROI로 일반화하지 않는다.
- 인식 정확도, first-attempt, 최종 완료, 복구율 분모, timeout/held와 실패 시간은 별개다. 없는 관측의 위치 오차를 0으로 채우지 않는다. task latency와 batch-1 model forward latency, sim time과 wall time을 구분한다.
- 처음 본 개발 split 결과에 맞춰 모델을 바꿨다면 그 split은 final이 아니다. 최종 가중치·threshold 고정 뒤 별도 final seed로 평가한 로그와 모델 해시를 확인한다.
- 남은 공백은 실제 모델 배포, 실물 전장/컵 성능, SLAM·충전, KiCAD, 일반 hand-eye·범용 물체다. 공고 대응표에서 관련 구현과 미충족 항목을 함께 보여준다.

## 5. 사용자의 PCB 경험을 연결하는 표현

“PADS와 ATmega128으로 회로 설계와 부품 배치·배선을 경험했습니다. 배선이 복잡해 부품을 재배치했고 숙련 동료의 조언을 반영해 더 정돈한 뒤 도구 검증 success를 확인했습니다. 이 경험은 배치와 인터페이스 제약을 소프트웨어와 함께 검토하는 데 도움이 됩니다.”

검증 success의 검사 종류·실물 제작/측정은 아직 미확인이라고 이어서 구분한다. PCB 결함 검사 저장소·PickLoop 제안 I/O 보드는 각각 다른 작업이다. 직접 실행한 재현·수정이 생기면 날짜·diff·원본 결과와 함께 [기여 문서](contributions.md)에 추가한 뒤 설명한다.
