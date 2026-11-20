# 매장 사진에서 Bravo 주스 두 종 판별

등록 포장의 인쇄 무늬와 색을 확인하는 판별기가 기존 시험 사진에서 주스 54장 중 **44장(81.5%)**의 맛을 맞혔다. 10장은 보류했다. 사과를 오렌지로, 오렌지를 사과로 바꿔 판정한 사례는 0건이었다. 같은 사진에서 기존 엄격한 거리 기준은 3장(5.6%)을 맞혔다. 미등록 포장의 오수락은 36/727에서 0/727로 줄었다. 실험과 학습 영역 표시는 Codex가 수행했다. [사진별 판정](experiments/carton-panels/predictions.csv) · [사전 명세](grocery-transfer-protocol.md)

| 매장 사진 평가 | 등록 주스 정답 / 54 | 두 맛 오분류 | 등록품 보류 | 미등록 포장 오수락 / 727 | 과일·채소 오수락 / 1,704 |
|---|---:|---:|---:|---:|---:|
| 줄무늬 인코더에 주스 등록 | 46 | 8 | 0 | 727 | 1,539 |
| 같은 인코더, 강화한 거리 기준 | 3 | 0 | 51 | 36 | 46 |
| ResNet-18와 세 클래스 선형 분류기 | 33 | 15 | 6 | 20 | 524 |
| **포장 인쇄 무늬와 색 확인** | **44** | **0** | **10** | **0** | **0** |

동일 이미지 SHA-256으로 전후 판정을 짝지었다. 기존에 보류한 등록품 42장을 새로 맞혔고, 기존 정답 중 한 장은 새 판별기가 보류했다. 사과주스는 15/23, 오렌지주스는 29/31이 정답이었다. 보류한 10장 중 6장은 인쇄 면의 위치를 확정할 수 없었고, 4장은 검출된 영역에서 두 맛의 색 차이가 작거나 색 유사도가 부족했다. [정답 사진](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/Bravo-Apple-Juice/Bravo-Apple-Juice_001.jpg) · [색 근거 부족으로 보류한 사진](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/Bravo-Apple-Juice/Bravo-Apple-Juice_002.jpg) · [인쇄 면을 확인하지 못한 사진](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/Bravo-Apple-Juice/Bravo-Apple-Juice_003.jpg)

## 사진 한 장 판별

저장소 루트의 프로젝트 Python 환경이나 Codespaces에서 실행한다. 아래 예시는 원 저자의 공개 사진 한 장을 받아 판별한다. 마지막 경로를 자기 사진으로 바꾸면 같은 판별기를 쓸 수 있다.

```bash
curl -fL -o /tmp/bravo-apple.jpg \
  https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/Bravo-Apple-Juice/Bravo-Apple-Juice_001.jpg
PYTHONPATH=src python -m pickloop.carton_matcher /tmp/bravo-apple.jpg
```

이 예시의 출력은 `Bravo-Apple-Juice`, `verified`, 기하 검증을 통과한 대응점 18개다. `panel_unverified`는 포장 표면을 확정하기 어려운 경우이고, `ambiguous_panel_color`는 해당 영역의 색으로 맛을 정하기 어려운 경우다. 두 경우 모두 `UNKNOWN`을 반환한다. `color_similarity`와 `color_gap`은 색 분포의 유사도와 두 후보 간 차이다. [판별 코드](../src/pickloop/carton_matcher.py) · [등록된 특징 데이터](experiments/carton-panels/gallery.npz)

## 무엇을 바꿨나

1. **실물 사진용 특징을 학습한 대조 실험.** ImageNet 사전 학습 ResNet-18을 고정하고 공식 train 582장으로 사과·오렌지·배경 선형 분류기를 학습했다. 특징을 사진 전체에서 뽑는 방식은 미등록 과일·채소에서 524건의 오수락을 냈다. 이 결과를 보고 포장 면을 먼저 확인하는 방식을 추가했다. [학습 입력·모델·집계](experiments/grocery-transfer/) · [시험 전 모델 동결 커밋](https://github.com/sokldjs554/pickloop/commit/81b8393)
2. **인쇄 무늬로 위치 확인.** 공식 train에서 맛별 8장의 포장 면을 다각형으로 표시했다. 입력 사진의 SIFT 특징과 등록 특징이 같은 평면 변환을 따르는지 본다. 인쇄 무늬가 우연히 맞거나 매대 뒤에 작게 보이는 상자를 줄이기 위해 대응점 수, 면적, 화면 내 위치, 대응점이 차지하는 면적을 함께 검사한다. [등록 영역](../configs/bravo-template-regions.json)
3. **찾은 포장의 색으로 맛 구분.** 추정한 면 안에서 색상 분포를 측정한다. 특정 옆면이 다른 맛과 비슷한 경우를 줄이기 위해 맛별 8개 표본과의 유사도 중앙값을 쓴다. 높은 유사도가 0.65 이상이고 두 맛의 차이가 0.08 이상일 때 수락한다. 개발 자료에서 고른 규칙과 등록 특징을 고정한 뒤 시험했다. [동결 커밋](https://github.com/sokldjs554/pickloop/commit/c279415) · [개발 결과](experiments/carton-panels/development.json)

## 검증 범위

- **기존 시험셋 재평가.** 포장 781장과 과일·채소 1,704장은 앞선 실험의 결과가 이미 알려져 있다. 최종 판별기는 학습 이미지에서 등록한 특징을 사용했고 각 시험 사진을 정답 라벨 없이 판정했다. 개발 단계에서 제외한 미등록 포장 10종 250장은 모두 거부했다. 이 250장은 727장의 부분집합이다.
- **다른 촬영 조건.** 같은 데이터셋의 카탈로그 포장 사진은 등록품 2/2 정답, 미등록품 0/29 오수락이었다. 두 번째 방법에서 처음 평가한 공식 검증용 과일·채소 40종 196장은 전부 거부했다. 이 196장은 모두 미등록품이므로 등록품 정답률을 추가로 검증하지는 못한다. [분할별 원본](experiments/carton-panels/summary.json)
- **사용 범위.** 실제 매장에서 찍은 정지 사진에서 화면 중앙 부근의 두 Bravo 포장을 확인하는 용도다. 독립적인 새 매장의 등록품 사진, 디자인이 바뀐 포장, 집품 카메라 스트림은 더 검증해야 한다. 실물 사진 판별기는 오프라인 명령으로 제공한다. 시뮬레이터는 기존 줄무늬 A/B 모델을 사용한다. 사진 원본은 데이터셋 저자의 저장소에서 내려받는다. [출처·이용 조건](real-photo-evaluation.md)

## 전체 재현

프로젝트 환경에서 아래 명령을 실행한다. `register`는 공개한 학습 영역으로 등록 특징과 개발 결과를 만든다. `evaluate`는 저장한 특징 파일을 읽어 시험 결과를 낸다. 기본 병렬 처리 수는 4이며 `--workers 1`로 조정할 수 있다.

```bash
curl -fL --retry 2 -o /tmp/pickloop-grocery.zip \
  https://codeload.github.com/marcusklasson/GroceryStoreDataset/zip/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc
PYTHONPATH=src python scripts/run_carton_matcher.py register \
  --archive /tmp/pickloop-grocery.zip --out /tmp/bravo-panels
PYTHONPATH=src python scripts/run_carton_matcher.py evaluate \
  --archive /tmp/pickloop-grocery.zip --out /tmp/bravo-panels
diff -qr docs/experiments/carton-panels /tmp/bravo-panels
```

ResNet 대조 실험은 아래처럼 재현할 수 있다. 가중치의 SHA-256을 로드 시 검사한다. 두 방법 모두 이미지 한 장을 지표 한 건으로 집계한다. 동일 환경에서의 재실행과 다른 CPU·수치 라이브러리에서의 소수점 단위 차이를 구분한다.

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torchvision==0.22.1'
curl -fL --retry 2 -o /tmp/resnet18-f37072fd.pth \
  https://download.pytorch.org/models/resnet18-f37072fd.pth
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python -m pickloop.grocery_transfer fit \
  --archive /tmp/pickloop-grocery.zip --weights /tmp/resnet18-f37072fd.pth --out /tmp/bravo-transfer
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 python -m pickloop.grocery_transfer evaluate \
  --archive /tmp/pickloop-grocery.zip --weights /tmp/resnet18-f37072fd.pth \
  --fit-dir /tmp/bravo-transfer --out /tmp/bravo-transfer
```
