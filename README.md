# PickLoop

**상품을 집어 옮기고, 실패를 감지해 복구하거나 보류하는 로봇 시스템.**

PyBrain AI AI Robot Engineer(S/W) 지원 검토용 프로젝트다. MuJoCo CPU 물리 시뮬레이션에서 RGB-D 관측 → 학습한 상품 임베딩 → 3D 상면 추정 → SCARA 계획·구동 → Modbus 흡착 → 운반·해제 → 영상과 별도 정답으로 배치 확인을 실행한다. 기존 ReachBench의 실제 pick/place 구현을 조사한 뒤, 품목 구분·실패 복구·장치 통신·운영 증거를 신규 범위로 구현했다.

- [운영 데모](https://pickloop-robot-ops.ykh13571.chatgpt.site): 로그인 없이 링크로 접근 가능한 실제 기록 재생. 브라우저에서 새 물리 조건을 계산하는 화면이 아니다.
- [공고 대응표](docs/job-requirements-matrix.md) · [아키텍처](docs/architecture.md) · [기여 기록](docs/contributions.md)
- [동결 조건 비교 결과](runs/final/summary.md) · [원본 집계 JSON](runs/final/metrics.json) · [trial CSV](runs/final/trials.csv)
- [학습·변환 평가](docs/vision-model.md) · [ROS2 실제 통신](docs/ros2-integration.md) · [모바일 확장](docs/mobile-extension.md)

## 설치와 첫 실행

검증 환경: Linux x86_64, Python3.12, MuJoCo3.3.7, PyTorch2.7.1 CPU, EGL/Mesa 소프트웨어 렌더링, g++. 실물 로봇이나 GPU는 필요 없다. Linux와 다른 OS의 EGL/소켓/파일 잠금 호환성은 확인하지 않았다.

Ubuntu24.04 계열의 시스템 의존성 예:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv libegl1 libgl1-mesa-dri libopengl0 g++ ffmpeg fonts-dejavu-core
python3 -m venv .venv
.venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-lock.txt
.venv/bin/pip install --no-deps -e .
export MUJOCO_GL=egl
export LIBGL_ALWAYS_SOFTWARE=1
.venv/bin/pytest -q
```

훈련된 소형 체크포인트와 생성된 텍스처는 포함되어 있다. Python 환경 lock은 실제 검증 환경에서 추출했다. `scripts/install.sh`도 같은 설치·검증을 실행한다.

```bash
# 정상 / 일시적 흡착 실패 복구 / 복구 불가 보류
.venv/bin/pickloop run --seed 7 --fault normal --out runs/local
.venv/bin/pickloop run --seed 7 --fault suction_once --out runs/local
.venv/bin/pickloop run --seed 7 --fault suction_permanent --out runs/local

# 실제 새 작업을 계산하는 로컬 운영 화면
.venv/bin/pickloop serve --host 127.0.0.1 --port 8000
# 브라우저: http://127.0.0.1:8000
```

로컬 화면의 실시간 모드에서는 주문 실행과 취소가 실제 API를 호출한다. 같은 job ID·내용의 완료 요청은 기존 결과를 반환한다. 한 셀은 한 작업만 실행한다. 중단된 작업은 자동 재실행하지 않고 HOLD_RECOVERY_REQUIRED로 조회된다.

## 재현 명령

```bash
# 저장된 최종 평가를 원본 result.json에서 다시 집계
.venv/bin/pickloop aggregate runs/final

# 새 디렉터리에서 동일 120개 조건을 전부 재실행
.venv/bin/pickloop evaluate --out runs/reproduced --seeds 1000 1001 1002 1003 1004

# 모바일 이동→도킹→실제 피킹→셀 퇴장→다음 이동
.venv/bin/python scripts/run_mobile.py --help

# CNN 합성 데이터 훈련 및 검증; 아래 명령은 모델을 교체할 수 있으므로 별도 checkout 권장
.venv/bin/python scripts/train_vision.py --help

# C++ 실제 Modbus 클라이언트
mkdir -p work
g++ -std=c++17 -O2 -Wall -Wextra -Werror cpp/modbus_client.cpp -o work/modbus_client
.venv/bin/pytest tests/test_device.py -q

# 운영 화면 계약 검사
node tests/ui-contract.mjs
```

ROS2 Jazzy는 `ros2/Dockerfile`의 고정 공식 이미지로 빌드한다. [실행 명령과 DDS evidence](docs/ros2-integration.md)에 정상 Action, 취소, 중복 요청, 카메라·관절·clock 실제 수신 기록이 있다. Python 코어용 루트 Dockerfile도 제공하지만 이 세션에서 빌드 검증한 컨테이너는 ROS2 이미지이며 코어는 호스트의 고정 venv에서 검증했다.

## 결과의 의미

최종 비교는 개발 seed0..99와 분리한 seed1000..1004, 12개 조건, 기준/복구 2개 정책이다. 성공 조건·제한·출처 해시는 실행 전 `runs/final/manifest.json`에 고정했다. 원본 전체를 집계하며 유리한 사례만 선택하지 않는다. 각 조건 5개 표본은 현장 일반화나 통계적 성능 보장을 하기에는 작다.

작업 완료율, 첫 시도 lift 성공률과 첫 시도 최종 완료율, 복구율, 잘못된 배치, 낙하, 금지 충돌, 보류, 재시도, 시간, 처리량을 구분한다. 실패 시간도 처리량 분모에 포함한다. simulator throughput과 measured CPU wall throughput은 별개이며 실물 현장 생산성·ROI를 주장하지 않는다. 장애 제거 조건과 지표 정의는 [아키텍처](docs/architecture.md)에 공개했다.

학습 모델은 직접 생성한 두 가지 붉은 줄무늬 상자와 합성 미등록 패턴으로 검증했다. 최종 합성 평가에서 known240/240, 지정 unknown120/120을 구분했지만, 이 수치는 실제 상품·임의의 unknown 전반에 대한 성능이 아니다. 초기 확인한 평가 분할은 개발 자료로 재분류했고, 모델 동결 후 새로운 seed30000대에서 최종 평가했다.

## 코드 읽기 순서

`types.py` → `geometry.py` → `perception.py`/`vision_model.py` → `simulation.py` → `device.py`와 `cpp/modbus_client.cpp` → `engine.py` → `journal.py`/`server.py` → `evaluation.py`. 관련 회귀 테스트와 `runs/final/*/events.jsonl`을 함께 읽는다. 자세한 질문·설계 판단은 [면접 가이드](docs/interview-guide.md)에 있다.

## 확인된 범위와 남은 공백

실제 물리 시뮬레이션, CPU 모델 훈련·추론·TorchScript, TCP Modbus/C++, ROS2 Action/DDS, 동일 작업 엔진을 호출하는 모바일 운동학 시나리오를 실행했다. 웹 데모는 해당 기록을 재생한다. 원본 소스에는 GitHub Actions CI 정의가 있으나 원격 GitHub CI 실행은 아직 수행하지 않았다.

실물 로봇에 모델 배포, 실제 흡착 누설·안전 회로·PLC, 실전 SLAM, 휠 접촉 동역학, 실물 정밀 도킹·충전은 검증하지 않았다. 모바일와 고정 셀은 별도 시뮬레이션 세계를 docking gate로 연결한다. 카메라는 고정형 PnP 외부 보정이며 hand-eye AX=XB를 구현했다고 표현하지 않는다. [실물 인수시험 절차](docs/hardware-acceptance.md)를 별도로 제공한다.

사용자가 확인한 PCB 경험은 PADS·ATmega128의 회로 설계/부품 배치/배선과 도구 검증이다. KiCAD나 실물 측정 경험을 추정하지 않는다. [확인 내용과 지원서 표현](docs/pcb-experience.md)을 참고한다. 이번 프로젝트의 구현·훈련·실험은 AI 에이전트가 수행했고, 사용자의 직접 작성 코드로 포장하지 않는다.
