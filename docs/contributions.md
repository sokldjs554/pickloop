# 기여·재사용·실행 주체

이 프로젝트는 사용자의 채용 지원 목표와 상세 요구에 따라 **AI 코딩 에이전트가 조사·설계·구현·학습·시험·문서 작업을 수행한 결과물**이다. 저장소 소유와 코드 생성 주체, 사용자가 직접 수행한 경험을 구분한다. 이 문서를 사용자가 모든 코드를 직접 작성·실험·배포했다는 진술로 바꾸면 안 된다.

| 주체/범위 | 확인된 내용 | 현재 주장할 수 없는 내용 |
|---|---|---|
| 사용자 — 문제·요구 정의 | 회사·공고·GitHub·프로젝트 목표 지정. 물체 운반·배치 확인, 실패 복구, 실제 추론·프로토콜, 정답 유입 금지, 근거/한계/기여 분리 요구 | 이것만으로 구현 전체·모델 학습·시험 수행을 직접 했다는 경력 |
| 사용자 — PCB 자기 보고 | PADS·ATmega128, 회로 설계·부품 배치·배선, 도구 검증 success. 복잡한 배선을 재배치하고 숙련 동료 조언으로 정리 | KiCAD, 실물 발주/실장·전기 기능 측정·로봇 연결. success 검사 종류와 측정 장비 미확인 |
| AI 에이전트 — 조사 | Wanted 원문·제품/UI·8개 기존 repo 코드/결과/기여 이력 감사. 고정 커밋·출처·일부 독립 재실행 구분 | 기존 repo 모든 실험·브라우저·실물 결과를 이번에 재현했다는 주장 |
| AI 에이전트 — 신규 소프트웨어 | MuJoCo SCARA, 외부 보정·RGB-D 분할, CNN/prototype, BT coordinator, TCP emulator·독립 C++ client, journal/API·운영 UI, 모바일/ROS2 코드 | 사용자 단독 수작업 구현, 현장 로봇 제품 출시/인증 |
| AI 에이전트 — 학습·검증 | 합성 텍스처/데이터 생성·CPU 학습·TorchScript export·평가·시험 명령 수행. 최종 결과는 원본 로그와 보고서 참조 | 실상품/실카메라 일반화·실물 로봇 모델 배포·실제 PLC/충전기 검증 |
| 사용자 — 복구 규칙 수정·검증 | 개발 seed 200에서 경로 차단 재시도만 높이를 올리도록 수정하고 코드와 전후 결과를 병합했다. [PR #1](https://github.com/sokldjs554/pickloop/pull/1) | 추가 seed 201~209의 45쌍은 Codex 독립 실행 |

PCB 경험은 [pcb-experience.md](pcb-experience.md)의 확인 문장을 따른다. `ondevice-pcb-inspection`은 별도 PCB 영상 검사 소프트웨어이며 같은 보드나 동일 제작 경험으로 합치지 않는다.

## 기존 프로젝트 재사용 장부

**이번 신규 구현에는 조사한 기존 GitHub 저장소의 소스 파일을 복사·수정하여 가져오지 않았다.** 코드 참고를 통해 문제와 검증 원칙을 파악했으며 신규 코드로 작성했다. 기존 프로젝트 성과 수치를 PickLoop 결과로 합산하지 않는다. 커밋별 근거와 원 저자의 AI 활용 공개는 [기존 감사](research/existing-projects.md)에 보존한다.

| 기존 프로젝트 | 참고한 아이디어/한계 | 이번 신규 구현 경계 |
|---|---|---|
| ReachBench | 이미 존재하는 물리 집기·운반·배치·가림 복구; RGB-D/IK·짝 실험 | 새 SCARA/흡착·CNN·PnP·제약 경로·BT·장치 내구 계약·영상 완료 확인. Panda 코드/모델을 복사하지 않음 |
| ondevice-pcb-inspection | 분류 정확도와 시스템 검사 지표 분리, 변환/버스 시험 원칙 | 상품용 신규 합성 데이터·CNN·prototype/TorchScript. PCB 모델·DeepPCB 데이터를 재사용하지 않음 |
| SceneProof | execution/event identity·시간·증거 연결과 bounded queue 원칙 | 새 job/command journal·run/image trace. 기존 dedup를 물리 exactly-once로 확대 주장하지 않음 |
| EdgeSight-SoC | register·fault/testbench 경계 | 신규 Modbus map·emulator·TCP/C++ 시험. RTL/IP 복사 없음 |
| NPULoop | export 전후 출력·정확도·실측 지연 분리 | PyTorch/TorchScript 비교. NPU/Vela 결과 이식 없음 |
| 추가 3개 repo | RTLS·깊이 역투영·deadline 원칙 | 개념만 참고. 지도/SLAM·기존 CAD 경력으로 과장하지 않음 |

라이브러리의 기능도 직접 만든 기능과 나눈다. MuJoCo는 강체 적분·접촉·렌더링, OpenCV는 PnP/연결 성분, PyTorch는 학습/추론/export, py_trees는 BT 기본 실행, FastAPI는 HTTP/Pydantic 경계를 제공한다. 직접 추가한 부분은 셀 모델/흡착 조건, 관측 계약·선택/완료 gate, 복구 정책·내구 ID·프로토콜, 데이터/평가 조건·원본 기록·운영 연결이다. 일반 충돌 탐색/ROS robot driver/SLAM은 해당 라이브러리를 썼다는 이유로 구현되었다고 하지 않는다.

`assets/textures/`는 이번에 생성한 독자 합성 자산이며 해당 [사용 조건](../assets/textures/LICENSE.txt)을 따른다. 모델·학습 데이터 출처/분할과 초기 개발 데이터 재사용 구분은 [vision-model.md](vision-model.md)에 있다. 외부 UI 이미지는 조사 참고이며 PickLoop 실행 증거로 사용하지 않는다.

## 지원자가 직접 재현한 결과

직접 실행한 [변경 전](experiments/retry-height/seed-200-before.json)과 [변경 후](experiments/retry-height/seed-200-after.json) 기록에서 경로 차단 완료는 유지됐고, 보정 오차 작업 시간이 2.530초 줄었다. 판정 조건은 다음 시도 번호, 복구 정책, 직전 오류 코드다. [코드·검증 변경](https://github.com/sokldjs554/pickloop/pull/1/files)과 [Codex의 독립 재현](experiments/retry-height/independent-validation.md)을 각각 확인할 수 있다.

## Codex가 추가 수행한 직무 검증

공개 매장 사진의 81품목 카탈로그 학습과 미등록품 시험, USDA 손목 카메라 실측 기록 분석, 모의 RGB-D 상자 배치·오프라인 라이다 SLAM·두 AMR 충전·S7 소프트웨어 PLC 통신 시험은 Codex가 구현하고 실행했다. 원본 사진과 로봇 자세는 각 데이터셋 저자가 수집했다. [직무별 코드와 실행 원본](job-requirements-matrix.md)

모의 포장 상품의 주문 피킹, 고드 모르곤 주스의 추가 표기 확인 및 외부 사진 전후 평가, 물리 모델을 고정한 운반 높이 20쌍 실험은 Codex가 추가로 수행했다. 지원자가 직접 수정하고 재현한 범위는 위 PR #1과 개발 seed 200이다. [주문 피킹](order-pick.md) · [맛 판별 전후](juice-gate.md) · [높이 비교와 개인 재현 명령](current-height.md)

새 실물 사진 수집·블라인드 평가, 포장 글자·바코드 판독, 미등록 규격 대조와 웹 사진 판독기는 Codex가 수행했다. 사진 저자와 이용 조건은 개별 출처에 기록했다. [사진 인식 범위와 재현](new-photo-recognition.md)

## 공개 데모 리뷰 반영

사용자는 공개 화면과 보고서를 직접 확인하고 시도 예산 혼재, seed 다양성, 재생 사례 부족, HELD 단계 이력, 인식 점수, 가독성 및 빈 흡착기의 밸브 유지 문제를 구체적으로 지적했다. AI 에이전트가 이에 따라 4정책 절제 실험, 조건 생성/동결, 보류 출력 분기, UI/원문 연결을 구현·실행했다. 사용자 리뷰 수행을 AI 구현과 구분하며, 이를 사용자가 직접 작성한 로봇 제어 코드나 실물 배포 경력으로 바꾸지 않는다.

작업 모니터의 영상은 Codex가 PickLoop의 MuJoCo 시뮬레이션을 실행하고 그때 저장한 카메라 프레임으로 만들었다. 사용자가 4초와 6초의 장면을 짚어 주었고, Codex가 수직축 모델을 수정해 같은 조건으로 다시 녹화했다. 이전 모델은 흡착기가 내려가면 축 윗끝과 팔 사이에 약 14 cm의 틈이 생겼다. 현재 모델에서는 팔 끝의 고정 가이드 안에서 중간 슬리브와 흡착축이 함께 움직인다. [이전 실행](../web/data/runs/suction_once-3000-recovery-aaff86/run.json) · [수정 후 실행](../web/data/runs/suction_once-3000-recovery-f5e7ef/run.json)

| 영상 경과 시간 | 수정 전 카메라 | 수정 후 카메라 |
|---|---|---|
| 4초 · 첫 흡착 실패 직후 | [팔과 흡착축 사이의 틈](../web/data/runs/suction_once-3000-recovery-aaff86/frames/00023-scene.jpg) | [내려간 축과 가이드](../web/data/runs/suction_once-3000-recovery-f5e7ef/frames/00023-scene.jpg) |
| 6초 · 빈 흡착기 상승 | [팔 위로 드러난 축](../web/data/runs/suction_once-3000-recovery-aaff86/frames/00032-scene.jpg) | [가이드 안으로 들어간 축](../web/data/runs/suction_once-3000-recovery-f5e7ef/frames/00033-scene.jpg) |

사용자가 요청한 용량별 오인식 재검사, 새로운 상품 코드로 분리한 사진 평가, 중복 상품 한 개 선택 및 배치 검증, PLC 응답 유실 기록의 공개 화면 반영은 Codex가 수행했다. [사진별 판정](experiments/fresh-size-eval/) · [동일 상품 두 개의 주문 실행](../runs/order-pick/duplicate/result.json) · [설비 통신 시험](plc-interop.md)

등록 상품의 포장 비교와 브라우저 판독, 제조사 디자인 등록, 매장·공개 사진 재검사는 Codex가 수행했다. 첫 평가의 결과와 이미 본 실패 사진을 다시 확인한 결과는 따로 공개했다. [등록품 평가와 기여 범위](experiments/registered-recall/production.md)

Codex가 옆면 사진 판독을 수정하고 기존 매장 사진과 추가로 수집한 유사 상품 옆면에서 검증했다. [판독 전후 기록](experiments/oblique-packages/)
