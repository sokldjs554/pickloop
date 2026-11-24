# God Morgon 주스의 포장 문자 확인

**기존에 오수락했던 혼합주스 19장 중 7장은 포장의 글자를 읽어 올바르게 고쳤고, 12장은 보류했다.** 새로 확보한 외부 사진에서는 81종 인식기가 먼저 전부 보류해 개선을 관측할 수 없었다. 별도의 시뮬레이션에서는 기존 정답 10건까지 보류했다. 아래의 세 모집단은 각각 집계했다. [고정한 평가 규칙](experiments/juice-gate/protocol.md)

| 사진과 출처 | 수량 | 기존 정답 / 오답 / 보류 | 문자 확인 후 정답 / 오답 / 보류 | 이름을 반환한 비율 | 기존 정답 → 보류 |
|---|---:|---:|---:|---:|---:|
| 외부 사진, 사전 중복 검사 통과 | 6 | 0 / 0 / 6 | 0 / 0 / 6 | 0% → 0% | 0 |
| MuJoCo 카메라, 전면·15° 기울임·부분 가림 | 24 | 15 / 0 / 9 | 5 / 0 / 19 | 62.5% → 20.8% | 10 |
| 이전에 확인한 공식 테스트의 오렌지·레드 자몽 혼합주스 | 19 | 0 / 19 / 0 | 7 / 0 / 12 | 100% → 36.8% | 0 |

**외부 사진.** 출처 담당자가 바코드와 제조사·판매처 상품 설명으로 사과, 오렌지, 오렌지·레드 자몽, 미등록 블러드오렌지·사과를 구별했다. 원본 7장에 비식별 ID와 SHA-256을 부여하고 정답표를 고정했다. 평가 코드는 GTIN·제품명·파일명을 인식기에 전달하지 않고, 추론이 끝난 뒤 정답표를 결합한다. 5,502개 기존 원본과 외부 사진 상호 간의 바이트·디코딩 RGB·지각 해시를 검사했다. 사전 규칙으로 제외한 한 장은 사과 사진과 디자인이 유사한 오렌지 스튜디오 사진이다. 서로 다른 GTIN이지만 pHash 거리가 2, dHash 거리가 1이었다. 이 사진도 별도 확인에서 전후 모두 보류했다. 주 집계의 6장은 실물 촬영 2장과 상품 스튜디오 사진 4장이다. 미등록 상품 1장도 보류했다. [원본 URL·바코드·권리 정보](experiments/juice-gate/external-manifest.csv) · [중복 검사](experiments/juice-gate/deduplication.csv) · [외부 사진별 판정](experiments/juice-gate/external-predictions.csv) · [제외 사진 판정](experiments/juice-gate/external-screened-predictions.csv)

**카메라 및 과거 사진.** 시뮬레이션은 기존 학습 사진 7개와 가상 미등록 상품 1개의 표면을 세 조건으로 촬영했다. 같은 표면의 세 시점은 서로 연관되며 새 실물 상품을 촬영한 자료와 별도로 평가했다. 과거 사진 19장은 기존 인식기가 오렌지 13번, 사과 6번으로 판정한 동일한 혼합주스다. 새 규칙의 오류 분석용으로 다시 실행했다. [카메라 설정·원본](experiments/juice-gate/camera-sources.csv) · [카메라 판정](experiments/juice-gate/camera-predictions.csv) · [과거 19장 OCR 원문·판정 사유](experiments/juice-gate/historical-predictions.csv)

## 판정 방법

`pickloop recognize IMAGE --juice-gate`는 기존 인식기가 세 제품 중 하나에 이름을 붙인 경우 포장 앞면의 맛 표기를 읽는다. 기존 보류는 유지한다. 등록한 앞면의 기하학적 특징으로 글자 영역을 펴거나 밝은 단색 배경의 단일 포장을 분리한다. 세 가지 OCR 읽기 중 둘 이상이 일치하고 다른 과일 표기와 충돌하지 않아야 이름을 반환한다. 사과, 오렌지, 혼합주스 사이의 수정이 가능하다. 글자를 확인할 수 없거나 OCR 실행에 실패하면 보류한다. `top1`은 기존 후보이며 `prediction`이 최종 판정이다. `juice_gate_original`, `juice_gate_text`, `juice_gate_reason`으로 해당 결정을 확인할 수 있다. [전처리·판정 코드](../src/pickloop/juice_gate.py)

## 재현

저장소 루트에서 catalogue 추가 패키지, 영어 언어 자료가 포함된 Tesseract, EGL을 지원하는 MuJoCo 환경을 사용한다. 아래 변수는 내려받은 파일의 위치다. DINOv2 체크포인트와 Grocery Store Dataset ZIP의 출처는 기존 재현 문서에 있다. [환경 및 원본 다운로드](grocery-catalogue.md)

```sh
export MUJOCO_GL=egl OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
archive=/tmp/pickloop-grocery.zip
weights=/tmp/dinov2-small.safetensors
cache=/tmp/pickloop-independent-juice
evidence=docs/experiments/juice-gate
python scripts/fetch_juice_sources.py "$cache"
python scripts/evaluate_juice_gate.py external --archive "$archive" --weights "$weights" \
  --external-manifest "$evidence/external-manifest.csv" --external-root "$cache"
python scripts/evaluate_juice_gate.py camera --archive "$archive" --weights "$weights" \
  --camera-output /tmp/pickloop-juice-camera
python scripts/evaluate_juice_gate.py historical --archive "$archive" --weights "$weights"
pytest -q tests/test_juice_gate.py
```

원본 학습 사진에서 등록 특징을 다시 만들려면 `python scripts/prepare_juice_gate.py "$archive" --out /tmp/juice_gate.npz`를 실행한다. SHA-256과 생성 환경은 고정 프로토콜에서 확인할 수 있다. 패키지에는 네 사진에서 추출한 특징을 포함한다. 외부 데이터는 URL·해시·판정 기록을 배포하며, 각 사진의 출처와 이용 조건은 명세에 기록했다. [등록 코드](../scripts/prepare_juice_gate.py) · [외부 사진 명세](experiments/juice-gate/external-manifest.csv)
