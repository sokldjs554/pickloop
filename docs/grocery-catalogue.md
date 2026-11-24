# 사진에서 81개 식료품 이름 판별하기

과일 28종, 포장 상품 31종, 채소 22종을 등록했다. 두 주스 실험에서 미등록으로 분류한 2,656장의 공식 상품명을 모두 복원했다. 사진을 새로 받았을 때 모델이 붙이는 이름과 데이터셋 저자가 기록한 정답을 한 행에서 비교할 수 있다. [공개 데모에서 사진별 정답 조회](https://pickloop-robot-ops.ykh13571.chatgpt.site/evidence#previous-photos) · [이전 사진 전체](experiments/grocery-catalogue/previous-cohort.csv) · [오분류·보류한 사진과 공식 이름](experiments/grocery-catalogue/previous-unknown-review.csv)

기본 사진 판별기는 보류했거나 고드 모르곤 주스 세 종류 중 하나를 선택하면 사진에서 글자와 바코드를 확인한다. 아래 표는 기존 81품목 판별기의 동결 기록이며, 현재 기본값의 외부 사진 평가는 별도로 공개한다. [새 실물 사진 결과와 직접 실행](new-photo-recognition.md)

## Codespaces에서 사진 한 장 판별하기

이 저장소의 새 Codespace를 열고 아래 명령을 실행한다. 예시 사진은 평가에 사용한 공개 매장 사진이다. 자기 사진은 저장소에 업로드한 뒤 마지막 줄의 파일 경로를 바꾸면 된다. 코드가 사진의 픽셀을 읽어 이름을 예측한다. 첫 실행 때 인코더 가중치를 내려받아 SHA-256을 확인하고 로컬에 보관한다.

```bash
curl -fL -o /tmp/pickloop-juice.jpg \
  https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/God-Morgon-Apple-Juice/God-Morgon-Apple-Juice_001.jpg
pickloop recognize /tmp/pickloop-juice.jpg
```

기존 Codespace에서 `main`을 사용 중이면 먼저 다음 명령을 실행한다.

```bash
git pull --ff-only
python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.7.1' 'torchvision==0.22.1'
python -m pip install -e '.[catalogue]'
```

`prediction`이 최종 이름이다. `UNKNOWN`은 등록 상품으로 수락할 근거가 부족해 보류한 결과다. `top1`에는 보류했을 때도 가장 가까운 이름이 남는다. `support`는 해당 품목의 가까운 등록 사진 세 장과의 평균 유사도, `score`는 선형 분류기 출력, `margin`은 결합 점수 1위와 2위의 차이다. 세 수치는 확률로 보정하지 않았다. 일반 분류기의 1위가 브라보 주스이면 기존 포장 검증기가 원본의 인쇄 면과 색을 확인한 뒤 최종 맛 또는 보류를 결정한다. 이때 일반 판정은 `generic_top1`과 `generic_prediction`, 포장 판정 근거는 `panel_reason`에 남는다.

## 평가 결과

| 사진 집합 | 장수 | 이름 정답 | 다른 이름 | 보류 |
|---|---:|---:|---:|---:|
| 과거 미등록 사진 | 2,656 | 2,091 | 321 | 244 |
| 공식 시험 | 2,485 | 1,982 | 304 | 199 |
| 공식 검증 | 296 | 217 | 34 | 45 |
| 상품 대표 사진 | 81 | 10 | 2 | 69 |
| 목록 밖 외부 시험 | 176 | 해당 없음 | 3 | 173 |

첫 행은 과거에 미등록으로 다뤘던 공식 시험 2,431장, 검증 196장, 상품 대표 사진 29장의 합이다. 나머지 공식 행과 겹친다. 외부 사진에서는 등록 상품명을 붙이면 오수락이다. [사진 3,038장의 판정 원문](experiments/grocery-catalogue/predictions.csv) · [품목별 집계](experiments/grocery-catalogue/per-class.csv) · [어떤 상품끼리 혼동했는지](experiments/grocery-catalogue/confusion.csv)

공식 시험에서 81종 중 80종을 한 번 이상 정확히 식별했다. 고드 모르곤 오렌지·레드 자몽 혼합주스는 19장 모두 다른 상품으로 판정했다. 외관이 가까운 포장과 과일 품종의 식별이 어렵다. 촬영 조건이 다른 상품 대표 사진은 보류율이 높다. 현장 카메라나 로봇 집품 영상에서의 성능은 별도 평가가 필요하다. [품목별 정답·오분류·보류](experiments/grocery-catalogue/summary.json)

포장 글자를 한 번 더 읽는 선택 옵션을 같은 혼합주스 19장과 새 외부 사진으로 비교했다. 모의 포장에 주문을 내고 상자 안까지 추적한 실행도 재생할 수 있다. [사진별 전후 비교](juice-gate.md) · [주문부터 배치까지](order-pick.md)

## 학습과 분할

등록에는 Grocery Store Dataset의 공식 학습 사진 2,640장을 사용했다. 81개 품목마다 연속한 파일 블록을 떼어 529장을 개발용으로 두고 나머지 2,111장으로 분류기를 학습했다. 고정한 DINOv2 ViT-S/14의 전체 사진 특징과 중앙 패치 특징, 중앙 색 분포를 결합한다. 이름 분류는 클래스 균형을 맞춘 선형 회귀와 등록 사진의 유사도를 이용한다. 기존 주스 2종의 포장 검증기는 공식 학습 사진 16장에서 등록한 특징과 이전에 동결한 판정 기준을 사용한다. 16장 중 5장은 이번 일반 분류기의 개발용 529장에도 들어간다. 따라서 529장 개발 수치는 일반 분류기와 보류 기준에만 적용한다. 이 검증기를 고를 때 사용했던 과거 개발·평가 이력은 두 주스 실험에 보존했다. 모델에는 상품 이름과 학습한 수치가 들어간다. 판정 시 시험 사진의 경로, 해시, 정답표는 사용하지 않는다. [모델 코드](../src/pickloop/catalogue_model.py) · [DINOv2 가중치](https://huggingface.co/timm/vit_small_patch14_dinov2.lvd142m/tree/4610ca143709d58a633b6397a74412c2c3842454)

첫 81품목 모델은 공식 시험을 채점하기 전에 고정했다. 첫 결과에서 기존 미등록 사진 2,022장을 맞혔고 외부 사진에 이름을 붙인 사례는 0건이었다. 후속 실험은 개발 사진과 외부 보정용 사진의 점수로 수락 기준을 재산정했다. 같은 평가 사진에서 과거 미등록 정답은 69장 늘고, 일반 분류기 단독의 목록 밖 상품 오수락은 5장 늘었다. 기존 브라보 포장 검증기를 연결한 최종 모델은 목록 밖 오수락을 5장에서 3장으로 줄였다. 기존 등록 주스의 매장 사진 54장에서 일반 분류기는 41장 정답·13장 오분류였고, 최종 모델은 44장 정답·0장 오분류·10장 보류였다. 오수락 3장은 시리얼 1장을 사워크림으로, 설탕 2장을 두유로 판정한 사례다. 같은 사진을 다시 본 재분석이며 사전학습 모델의 전체 학습 자료와의 중복 여부는 확인하지 못했다. [실험 명세](grocery-catalogue-protocol.md) · [첫 모델 집계](experiments/grocery-catalogue/first-pass.json) · [조정한 일반 분류기](experiments/grocery-catalogue/general-only.json) · [최종 설정](experiments/grocery-catalogue/fit.json)

외부 사진은 Freiburg Groceries의 22개 미등록 상품군에서 품목당 16장씩 골랐다. 보정용 11개 상품군의 176장과 시험용 11개 상품군의 176장은 품목이 겹치지 않는다. 주스·우유 등 등록품과 겹치는 상품군을 제외했다. 이 사진에는 다양한 매대 배경과 회색 여백이 있어 매장이나 미등록 상품 종류가 달라지면 거부 성능도 달라질 수 있다. [선정·검증 코드](../scripts/catalogue_outside_source.py)

## 전체 결과 재현

저장소 최상위에서 실행한다. 첫 명령은 고정 버전의 원 자료를 받는다. 마지막 감사는 공식 시험·이전 실험 사진을 경로, 이름, SHA-256으로 검증하고 보고서와 데모용 JSON을 생성한다. 원본 사진은 저자의 저장소에서 가져온다.

```bash
curl -fL -o /tmp/pickloop-grocery.zip https://codeload.github.com/marcusklasson/GroceryStoreDataset/zip/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc
python scripts/catalogue_outside_source.py /tmp/pickloop-outside
python scripts/cache_catalogue_features.py --archive /tmp/pickloop-grocery.zip \
  --outside-manifest /tmp/pickloop-outside/manifest.csv --cache /tmp/pickloop-features \
  train outside_calibration test val catalogue outside_test
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python scripts/run_grocery_catalogue.py fit --cache /tmp/pickloop-features \
  --out /tmp/pickloop-results --head /tmp/pickloop-results/head.npz
python scripts/run_grocery_catalogue.py evaluate --cache /tmp/pickloop-features \
  --archive /tmp/pickloop-grocery.zip --outside-manifest /tmp/pickloop-outside/manifest.csv \
  --out /tmp/pickloop-results --head /tmp/pickloop-results/head.npz
python scripts/audit_grocery_catalogue.py --evidence /tmp/pickloop-results \
  --web-data /tmp/pickloop-results/web.json
python scripts/export_previous_photos.py --evidence /tmp/pickloop-results \
  --output /tmp/pickloop-results/photos.json
```

Grocery Store Dataset은 Marcus Klasson, Cheng Zhang, Hedvig Kjellström의 WACV 2019 자료다. Freiburg Groceries는 Philipp Jund, Nichola Abdo, Andreas Eitel, Wolfram Burgard의 연구 자료이며 상업적 이용에는 저자의 동의가 필요하다. Freiburg 평가에는 원 저자의 fold 0 파일 목록과 224픽셀 RGB 미러를 고정했다. PickLoop 배포물은 사진의 원본 링크·해시·판정 기록을 제공한다. [Grocery Store 논문](https://arxiv.org/abs/1901.00711) · [공식 데이터와 이용 안내](https://github.com/marcusklasson/GroceryStoreDataset/tree/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc) · [Freiburg 논문](https://arxiv.org/abs/1611.05799) · [이용 조건](http://aisdatasets.informatik.uni-freiburg.de/freiburg_groceries_dataset/) · [원본 fold](https://github.com/PhilJd/freiburg_groceries_dataset/blob/8827d2f61c2838756a069562b1c2ff53568ae33b/splits/test0.txt) · [이미지 미러](https://github.com/aleksandar-aleksandrov/groceries-object-detection-dataset/tree/456a9cbbdfdb1695d0050a0d9431a6298604bc15)

기존 두 주스 전용 판별기의 44/54는 당시 두 품목에 한정한 실험이었다. 일반 모델의 1위가 브라보 주스일 때는 그 검증기가 두 맛을 구분한다. 실물 사진용 `pickloop recognize`와 시뮬레이터의 줄무늬 A/B 집품 작업은 서로 다른 경로에서 실행된다. 이번 모델 구현과 평가는 Codex가 수행했다. [두 주스 실험](carton-recognition.md) · [프로젝트 기여 기록](contributions.md)
