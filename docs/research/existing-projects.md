# 기존 프로젝트 구현·평가·기여 근거 감사

조사일: 2026-11-17 UTC. 연결된 GitHub 도구로 저장소 메타데이터와 공개 파일을 먼저 조회하고, 전체 소스·원본 결과·이력을 읽기 위해 공개 저장소를 별도 clone했다. 계정의 비공개 저장소는 조사하지 않았다. 이 문서는 PickLoop 신규 코드의 구현 완료를 뜻하지 않는다. 조사 중 기존 코드를 PickLoop에 복사하지 않았다.

**가장 중요한 범위 수정:** 현재 ReachBench는 이미 MuJoCo Panda의 물리 접촉 집기·운반·트레이 놓기와 가림 복구를 구현했다. 따라서 PickLoop를 단순히 “목표 접근을 물체 이동으로 확장”했다고 설명하면 현재 원본을 잘못 설명한다. 신규 기여는 상품 식별 학습, 흡착 상태 확인, 실제 장치 프로토콜, 취소·중복·재시작 계약, Behavior Tree 복구와 운영 증거의 통합으로 구분해야 한다.

## 근거 수준

- **코드 확인:** 실제 입력·판정·제어 경로를 읽었다.
- **기록 확인:** 저장소에 추적된 원본 JSON·학습 이력·시험 소스가 있음을 확인했다. 과거 실행을 이번에 재실행했다는 뜻은 아니다.
- **독립 재실행:** 아래 명령을 현재 clone에서 실행해 출력을 확인했다.
- README의 성과 설명, git author 문자열, 계정 소유는 개인의 직접 구현·실물 배포를 자동 증명하지 않는다. 저장소별 명시적 기여 설명을 함께 따른다.

커밋 고정 목록과 파일 SHA-256, 실행 명령·결과는 [repository-evidence.json](repository-evidence.json)에 있다. 이후 HEAD가 바뀌어도 아래 링크는 조사한 버전을 가리킨다.

| 저장소 | 조사 커밋 | 라이선스 및 재사용 판단 |
|---|---|---|
| [reachbench](https://github.com/sokldjs554/reachbench) | `9fc431b31156536dc2d4a18ba1cb69c17d381d30` | MIT; Panda 모델 Apache-2.0 및 외부 자산 고지 별도 |
| [ondevice-pcb-inspection](https://github.com/sokldjs554/ondevice-pcb-inspection) | `648eeb8c455d97017aeae07605f090e169ecc4b8` | 루트 LICENSE/COPYING 미발견; 공개라는 이유로 재배포 허용 추정 금지 |
| [sceneproof](https://github.com/sokldjs554/sceneproof) | `1733a4cc0e2175969cd08852c6131bfa50699764` | Apache-2.0; 데이터·모델 개별 조건 별도 |
| [edgesight-soc](https://github.com/sokldjs554/edgesight-soc) | `73ce8bb38c4594b16df470bf1711a210680ea7ba` | 루트 LICENSE/COPYING 미발견; 공개라는 이유로 재배포 허용 추정 금지 |
| [npuloop](https://github.com/sokldjs554/npuloop) | `dd13cb558e49ef3a8ee87d54ab094df6aae06597` | 루트 LICENSE/COPYING 미발견; 공개라는 이유로 재배포 허용 추정 금지 |
| [rtls-foresight](https://github.com/sokldjs554/rtls-foresight) | `5bef49b8968249f7681877e48a61cdc6badea072` | 루트 LICENSE/COPYING 미발견; 공개라는 이유로 재배포 허용 추정 금지 |
| [DriveSplat](https://github.com/sokldjs554/DriveSplat) | `ac2b6cb228ed81eaf7482f2bba49ef5d37f7b0bc` | 루트 LICENSE/COPYING 미발견; 공개라는 이유로 재배포 허용 추정 금지 |
| [inference-rail](https://github.com/sokldjs554/inference-rail) | `8a2c9a4400af176362b1ded0808bbc984c617112` | All rights reserved; 소스 복사 금지 명시 |

## 1. ReachBench — 가장 가까운 출발점과 중복 범위

[README](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/README.md) / [작업 제어](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/manipulation/controller.py) / [물리·IK·센서](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/manipulation/world.py) / [RGB-D 인식](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/manipulation/perception.py) / [통합 시험](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/tests/test_manipulation.py)


**코드로 확인한 구현:** MuJoCo 4.0.1, Franka Panda, 두 고정 카메라, RGB→HSV 적색 분할→연결 성분→depth 역투영→카메라 좌표 변환→감쇠 최소제곱 IK→관절 모터 명령→접촉 그리퍼 닫기→들기→운반→해제→최종 판정이 연결된다. `command()`는 actuator 제어값을 바꾸고, `mj_step()`으로 관절과 물체가 움직인다. 실행 중 큐브를 로봇에 강제 부착하는 제약은 해당 경로에 없다. 재관측과 최대 한 번의 재시도가 있고, 기본·가림·관측 뒤 이동·작업 범위 밖을 비교한다.

**이번 독립 확인:** `MUJOCO_GL=egl python -m pytest -q -p no:cacheprovider tests/test_manipulation.py`에서 9/9 통과(6.90초). Python 3.12, MuJoCo 4.0.1, OpenCV headless 5.0.0.93, pytest 9.2.0, CPU/EGL 환경이다. 빈 입력의 탐지 거부, RGB-D 위치, 두 번째 시점, 관절이 순간이동하지 않음, 실제 접촉 집기·해제, 가림 복구, 원본 평가의 짝 조건을 포함한다. Node `tests/test_studio.mjs` 4/4 통과, `npm run check`의 세 모듈 문법 검사도 통과했다. 전체 160회를 새로 돌리거나 이번 감사에서 공개 브라우저 데모를 직접 조작하지는 않았다.

**원본 결과 재계산:** `dist/bench/episodes.json` 160개를 읽으면 단일 관찰 20/80, 피드백 60/80이다. 네 조건별 각 20회이며 동일 seed·조건의 초기 대상 위치가 모두 짝을 이룬다. 평가 설정의 Python 소스 SHA-256도 현재 파일과 모두 일치한다. 실제 `retries>0`인 항목은 `shifted-107-feedback` 한 건뿐이다. 즉 25%→75%를 “재시도 단독 효과”로 주장할 수 없고, 추가 관찰과 재시도를 합친 개입 결과로 설명해야 한다.

[160회 원본](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/dist/bench/episodes.json) / [조건·성공 정의·소스 해시](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/dist/bench/config.json) / [집계](https://github.com/sokldjs554/reachbench/blob/9fc431b31156536dc2d4a18ba1cb69c17d381d30/dist/bench/summary.json)


**PickLoop에서 메워야 할 한계:**

- 학습된 검출기·상품 임베딩·unknown 판정이 없다. 적색 44 mm 큐브를 가정하며 Z는 `.382 m`로 고정한다. 가림·유사 상품·모르는 SKU를 다루는 상품 인식으로 일반화할 수 없다.
- 카메라 외부 파라미터는 `cam_xmat/cam_xpos`를 센서 메타데이터로 직접 준다. 실제 데이터로 외부 보정을 추정하거나 손눈 보정을 실행한 증거가 아니다.
- IK는 관절 범위를 clipping하지만 경로 전체 충돌 탐색·속도·가속도 제한 검증은 없다. 접촉 후 occluder collision을 성공 지표에서 탈락시키는 것과 충돌 없는 경로 계획은 다르다.
- 잡힘은 손가락 폭으로 추정한다. 최종 `result()`는 평가용 simulator truth와 트레이 범위·손가락 열림으로 성공을 판정한다. 정답을 IK 입력으로 넘기지는 않지만 운영용 카메라·압력 기반 완료 확인은 별도 구현해야 한다.
- 흡착·밸브·압력·Modbus/PLC, Behavior Tree, 센서 freshness, 명령 idempotency, cancel/restart/reconnect 계약이 없다. 이동 베이스·SLAM·도킹·충전·다중 로봇도 없다.

**기여 해석:** README는 사용자의 문제·요구사항 제시, 결과 피드백, 저장소 생성을 확인된 사용자 기여로 한정하고 구현·실험·문서·배포는 Codex 수행이라고 명시한다. 조사한 5개 커밋 author도 모두 Codex다. 이를 사용자가 직접 구현·실험한 경력으로 바꾸면 안 된다.

**재사용 권고:** MIT 원문·저작권 표시를 유지하면서 좌표 계약과 RGB-D 입력 경계, 평가 짝 구성, 물리 로딩/IK의 작은 부분을 검토할 수 있다. Panda 모델과 브라우저 vendor 자산은 별도 출처·라이선스·해시를 보존해야 한다. 이번 감사에서는 복사하지 않았다.

## 2. On-device PCB Inspection — 모델 지표와 검사 완료 지표의 차이

[학습](https://github.com/sokldjs554/ondevice-pcb-inspection/blob/648eeb8c455d97017aeae07605f090e169ecc4b8/src/train.py) / [패치 분할·jitter](https://github.com/sokldjs554/ondevice-pcb-inspection/blob/648eeb8c455d97017aeae07605f090e169ecc4b8/data/prepare_patches.py) / [보드 검사](https://github.com/sokldjs554/ondevice-pcb-inspection/blob/648eeb8c455d97017aeae07605f090e169ecc4b8/deploy/detect_board.py) / [보드 평가](https://github.com/sokldjs554/ondevice-pcb-inspection/blob/648eeb8c455d97017aeae07605f090e169ecc4b8/deploy/eval_detection.py) / [C++ 장치 버스](https://github.com/sokldjs554/ondevice-pcb-inspection/blob/648eeb8c455d97017aeae07605f090e169ecc4b8/deploy/cpp/src/serial_bus.cpp)


**구현 확인:** DeepPCB 공식 train/test 목록에서 패치를 만들고 jitter를 적용한다. PyTorch SimpleCNN/MobileNetV2 학습, ONNX 변환·양자화, 보드 슬라이딩 윈도우, 템플릿 비교·박스 정밀화·멀티스케일, C++ 포팅, SPI/I2C ioctl 경로와 CRC-16 프레임/루프백 self-test가 있다. SPI 수신 버퍼를 만드는 것만으로 장치 응답·행동 완료를 검증한 것은 아니다.

**기록 확인:** `results/metrics_mobilenet_v2.json`에 패치 6,140개 정확도 0.96042345와 클래스별 support가 있다. `results/benchmark.json`은 MobileNetV2 FP32 1.39 ms, INT8 2.12 ms를 기록한다. `results/npu_compile.json`의 U55-256 4.889 ms는 Vela 추정치이며 NPU 보드 실측이 아니다. 원본 DeepPCB 다운로드·학습·실제 SPI/I2C 파형 확인은 이번 감사에서 실행하지 않았다. 보드 검출의 여러 recall/precision/IoU 표는 코드가 있으나 모든 표에 대응하는 개별 예측 원본은 이 감사에서 확인하지 못했으므로 README 보고값으로 남긴다.

**평가상 주의:** `train.py`는 이미 추출한 패치를 `random_split`해 train/val을 만든다. 같은 원보드의 서로 다른 패치가 양쪽에 들어갈 수 있고 검증 subset이 train의 랜덤 flip transform도 공유한다. 공식 test와 별개이지만 검증 선정에는 장면 중복과 확률적 증강이 섞인다. PickLoop는 렌더 scene/상품 instance 단위로 train/dev/test를 먼저 나누고 검증 변환을 고정한다. README의 박스 pad 조정 과정도 최종 test에서 설정을 골랐는지 원본 실험별 확인 없이는 독립 최종 성능으로 강화하지 않는다.

**기여·재사용:** 관찰한 50개 커밋 author는 sokldjs554이지만 shallow history이며 git 문자열만으로 전부 직접 코딩했다는 결론은 내리지 않는다. 루트 라이선스가 없어 소스 복사보다는 “모델 정확도와 시스템 recall 분리”, FP32/INT8 동시 검증, 버스 프레임 오류 시험의 설계 원칙을 활용한다. 흑백 PCB 7클래스 모델을 상품 모델로 그대로 재사용할 이유는 없다.

**PCB 제작 경험과 별도:** 사용자는 보드를 처음부터 끝까지 직접 제작했다고 진술했다. 이 저장소는 PCB 영상 결함 검사 소프트웨어다. CAD·MCU·보드 목적·시기·공정·측정 장비는 아직 불명이며 KiCad나 로봇 연결 경험을 추정하지 않는다.

## 3. SceneProof — 운영 증거·이벤트·직접 수정 기여

[사건 묶기](https://github.com/sokldjs554/sceneproof/blob/1733a4cc0e2175969cd08852c6131bfa50699764/src/sceneproof/server/groups.py) / [내구성 큐](https://github.com/sokldjs554/sceneproof/blob/1733a4cc0e2175969cd08852c6131bfa50699764/gateway/internal/queue/queue.go) / [최종 원본](https://github.com/sokldjs554/sceneproof/blob/1733a4cc0e2175969cd08852c6131bfa50699764/docs/eval/bench/raw/bench_test_final.json) / [기본 결과](https://github.com/sokldjs554/sceneproof/blob/1733a4cc0e2175969cd08852c6131bfa50699764/docs/experiments/entry-confirm-20261113/base.json) / [확인 시간 변경 결과](https://github.com/sokldjs554/sceneproof/blob/1733a4cc0e2175969cd08852c6131bfa50699764/docs/experiments/entry-confirm-20261113/slow.json)


**구현 확인:** YOLOX/ByteTrack/구역 상태 전이, 사건 영상과 VLM 설명, 서버 API/관제 화면, Go의 bounded WAL queue·fsync·event_id/revision dedup가 있다. 미디어 시간과 벽시계 시간을 모두 확인하는 사건 묶기는 같은 영상을 다른 시점에 실행했을 때 잘못 합치지 않는다. 이 패턴은 PickLoop의 execution_id·observation timestamp·장치 command revision을 분리하는 근거가 된다. 사건 업로드의 dedup가 로봇 명령의 안전한 재실행을 이미 해결했다는 뜻은 아니다.

**독립 재실행:** 그룹·gap·edge-case 시험 13/13 통과(0.03초). 모델 추론·미세조정·GPU 벤치마크는 재실행하지 않았다.

**원본 대조:** 진입 확인 시간을 0.3→1.0초로 바꾼 4편 기록은 TP 12→9, missed 0→3, duplicate 6→2다. 최종 별도 34편 원본은 baseline TP160/207, 중복18과 미세조정 TP198/207, 중복49를 기록한다. 재현 가능한 원본과 실패 tradeoff를 함께 제시하는 방식이 유용하다. 사건 정답은 사람이 그린 box를 제품과 같은 구역 규칙에 통과시켜 만든 것이므로 완전히 독립적인 수동 사건 판독과도 구분한다.

**기여:** README는 대부분 제품 코드에 Claude Code를 썼고 사용자가 gap_s, min_box_height_px, concurrent_only의 3개 기능과 테스트 10개를 직접 작성했다고 구분한다. 실제 기능 변경 커밋 `01b64cf6c294b650184c62a4be2ddfae15b00c20`, `606a0d3a9d2457615d90ab6bf8ed7917307ff553`, `7e3b23954844450c0c1422c468339ffc3223f2ea`의 파일 diff와 테스트 추가를 확인했다. 개인 PR을 다인 팀 협업으로 표현하지 않는다. Apache-2.0 코드와 CAVIAR/MOT 등 데이터의 BY-SA/비상업 조건은 별도이므로 상품 학습 데이터로 섞지 않는다.

## 4. EdgeSight-SoC — 장치 경계·RTL 검증의 근거

[SPI–AXI bridge](https://github.com/sokldjs554/edgesight-soc/blob/73ce8bb38c4594b16df470bf1711a210680ea7ba/rtl/periph/spi_axil_bridge.v) / [CDC FIFO](https://github.com/sokldjs554/edgesight-soc/blob/73ce8bb38c4594b16df470bf1711a210680ea7ba/rtl/common/async_fifo.v) / [INT8 RTL](https://github.com/sokldjs554/edgesight-soc/blob/73ce8bb38c4594b16df470bf1711a210680ea7ba/rtl/npu/tinynpu2.v) / [시스템 시험](https://github.com/sokldjs554/edgesight-soc/blob/73ce8bb38c4594b16df470bf1711a210680ea7ba/tb/tb_edge_soc_e2e.v) / [11개 회귀 구성](https://github.com/sokldjs554/edgesight-soc/blob/73ce8bb38c4594b16df470bf1711a210680ea7ba/sim/Makefile)


카메라 DVP→CDC FIFO→전처리→정수 CNN→AXI4-Lite, SCCB/SPI, Linux driver 코드와 self-checking testbench가 존재한다. 시험 Makefile은 11개 스위트 각각의 `RESULT: PASS`를 확인해 전체 실패를 반환한다. 골든모델·가중치·입력 벡터가 추적되어 있다. README의 11/11 PASS, INT8 90.31%, 323,028 cycles·100 MHz 가정 3.23 ms는 과거 저장소 보고값이다. 이 환경에 iverilog/verilator가 없어 회귀를 재실행하지 않았다. RTL simulation·구조 합성·주파수 가정은 FPGA 보드에서의 카메라/NPU 실측과 다르며 원문도 실보드 검증을 향후로 둔다.

단일 author 커밋만 있어 변경 과정·개인 직접 구현 범위를 history로 세분화할 수 없다. CAD·PCB 제작 증거가 아니다. PickLoop는 레지스터 맵·상태 비트·타임아웃·테스트 상대 장치 모델을 설계하는 원칙을 활용할 수 있지만, 라이선스가 없고 로봇 제어에 FPGA NPU를 새로 넣는 것은 핵심 범위에 도움이 적다.

## 5. NPULoop — 변환 정확도와 추정 성능을 분리

[노드별 비교](https://github.com/sokldjs554/npuloop/blob/dd13cb558e49ef3a8ee87d54ab094df6aae06597/npuloop/intengine/verify.py) / [정수 시험](https://github.com/sokldjs554/npuloop/blob/dd13cb558e49ef3a8ee87d54ab094df6aae06597/tests/test_intengine.py) / [E11 원본](https://github.com/sokldjs554/npuloop/blob/dd13cb558e49ef3a8ee87d54ab094df6aae06597/results/e11_tflite_crosscheck.json) / [E13 원본](https://github.com/sokldjs554/npuloop/blob/dd13cb558e49ef3a8ee87d54ab094df6aae06597/results/e13_vela.json) / [검증 범위](https://github.com/sokldjs554/npuloop/blob/dd13cb558e49ef3a8ee87d54ab094df6aae06597/docs/VALIDATION_SCOPE.md)


NumPy/C++ 정수 실행, requantization, fake-quant의 local/propagated 차이, 구조 변경·학습 실험 코드가 있다. E11은 conv/MEAN/FC를 포함한 지정 TFLite reference 경로 1,000장과 모든 텐서 0 mismatch인 설정을 기록하며 다른 rounding 설정의 불일치도 보존한다. E13은 Vela와 자체 비용 모델을 모두 추정기로 명시한다. 이는 실제 NPU에서 몇 ms에 돌아간다는 근거가 아니다. 학습·C++ 엔진·TFLite/Vela를 이번에 다시 실행하지 않았다.

PickLoop에서는 최종 task 성공뿐 아니라 float→ONNX/INT8의 품목 정확도·unknown 거부·좌표·작업 결과 변화와 CPU 실제 지연을 함께 비교하는 방법을 참고한다. 전체 NPULoop 엔진을 이식할 필요는 없다. 라이선스 미발견이며 shallow 관찰 history에는 Claude/sokldjs554 author가 혼재한다. author별 개인 실험 수행은 별도 확인해야 한다.

## 6. 공개 프로필에서 추가 발견한 관련 저장소

| 저장소 | 실제 확인한 코드·기록 | PickLoop 관련성·한계 |
|---|---|---|
| [rtls-foresight](https://github.com/sokldjs554/rtls-foresight/blob/5bef49b8968249f7681877e48a61cdc6badea072/src/foresight/serving/risk.py) | 같은 joint sample의 작업자–차량 거리 위험, hysteresis/cooldown과 평가 원본 `results/collision_eval_dsafe2.json` | 이동체 위험 분석 참고. 궤적 예측은 SLAM·측위·경로 계획·다중 로봇 제어가 아니다. 합성 RTLS이며 실제 UWB 현장 검증 아님. |
| [DriveSplat](https://github.com/sokldjs554/DriveSplat/blob/ac2b6cb228ed81eaf7482f2bba49ef5d37f7b0bc/core/depth_to_pointcloud.py) | metric depth 역투영·camera-to-world, `core/scale_alignment.py`의 양수 median ratio 스케일 | 좌표/깊이 지식 근거. README는 affine 결과를 말하지만 현재 추적 소스에 affine 추정 구현·원본 학습/평가 로그가 없어 재현 확인 불가. 로봇 hand-eye·SLAM 증거 아님. |
| [inference-rail](https://github.com/sokldjs554/inference-rail/blob/8a2c9a4400af176362b1ded0808bbc984c617112/app/core/batcher.py) | deadline-aware bounded queue, cancelled future, backend 호출 전 만료 제거, breaker/fallback와 저장 runtime 증거 | 센서 추론 deadline·backpressure 설계 참고. mock/CPU Triton 결과는 로봇 장치 제어 증거 아님. LICENSE가 복사·수정을 금지하므로 개념만 참고. |

세 추가 저장소는 코드 읽기까지의 제한된 조사이며 모델/서비스/브라우저를 재실행하지 않았다. 다른 두 저장소도 루트 라이선스가 없어 복사를 허용한다고 추정하지 않는다.

## PickLoop의 신규 구현 경계와 우선 검증

| 기존 근거 | 새 프로젝트에서 추가할 실체 | 검증·정직한 남은 공백 |
|---|---|---|
| ReachBench RGB-D/IK/접촉 운반 | 유사 SKU 임베딩·학습·unknown 거부, depth 결측·보정 오차, 카메라 관측 기반 배치 검증 | train/dev/eval scene 분리, raw RGB-D/예측/평가 GT 분리; 물리 GT는 평가에만 사용 |
| ReachBench 제한 재관측/재시도 | BT recover/hold/cancel, stale 관측·낙하·blocked path·device timeout 분류 | 같은 seed/장면/장애의 복구 off/on, 중복 command/재시작/재연결 fault tests |
| PCB 검사 버스 framing·EdgeSight 레지스터 | 흡착 그리퍼의 밸브/압력 상태와 실제 TCP 프로토콜 emulator, command ID·상태 조회 | CRC/소켓 연결만으로 집기 완료 선언 금지; 재연결 뒤 물리 동작 중복 방지 |
| SceneProof 사건·근거·동일 실행 연결 | job_id로 센서/추론/계획/명령/압력/오류/복구를 추적하는 운영 화면 | live/replay/hardware를 분리하고 camera frame와 robot state의 동일 run/time 확인 |
| NPULoop/PCB float–INT8 비교 | 실제 상품 모델 학습과 ONNX 변환 후 end-to-end 판정 비교 | 추정 NPU 지연을 실측으로 쓰지 않고 host CPU wall time 기록 |
| RTLS 궤적 예측·DriveSplat 깊이 | 고정 셀 후 이동→도킹→피킹, 공유 구역 점유·작업 할당 | 기존 repo에 ROS2 SLAM·정밀 도킹·물리 충전 증거 없음; 아이콘 이동을 자율주행이라 부르지 않음 |
| 사용자 진술의 PCB 제작 경험 | 선택적 밸브/압력 I/O 보드 설계·인터페이스·BOM·시험 계획 | CAD/MCU 등 답변을 받은 뒤 기록. 설계 파일과 실물 제작/측정은 분리 |

기존 라이선스와 source commit을 고정해 실제로 가져온 파일·수정 목적·신규 시험을 reuse ledger에 기록한 후에만 재사용했다고 쓴다. 기존 기록 숫자는 PickLoop 성능으로 합치지 않는다. 이번 AI 도구 수행 범위와 사용자의 이후 직접 재현·수정·면접 설명 범위를 기여 문서에서 나눈다.
