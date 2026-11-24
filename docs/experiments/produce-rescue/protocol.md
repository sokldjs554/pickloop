# 보류된 과일·채소 사진 재확인

선택 기능은 기존 기본 판정과 81종 헤드가 모두 보류했고 헤드의 1위가 등록된 과일·채소일 때만 실행한다. 출력 범위는 바나나, 파인애플, 오이다. 이미 이름이 붙은 사진, 포장 상품 후보, 바코드 증거, 주스·우유 등 포장 표기와 충돌하는 경우에는 기존 판정을 유지한다. 이 기능의 결과는 사진의 품목명이며 주문 GTIN은 별도 바코드 검사에서 확인한다.

기본 모델과 다른 학습 자료를 쓴 torchvision ResNet-18 ImageNet-1K V1을 사용한다. 224px 중앙 크롭과 원본 화각을 유지한 패딩 이미지에서 1위 ImageNet 이름이 모두 같은 등록 품목이어야 한다. 81종 헤드의 1위까지 같으면 두 softmax 점수의 최솟값 0.75, 두 1·2위 점수 차의 최솟값 0.55가 필요하다. 헤드가 다른 과일·채소를 지목하면 점수 하한을 0.90으로 높이고 헤드 지지점수 0.50 이상을 요구한다. 딸기, 주키니 등 다른 ImageNet 이름을 세 품목 중 하나로 바꾸지 않는다. 확률 수치는 해당 분류기의 softmax이며 실제 현장 정확도로 보정한 확률은 아니다. [모델 동결 기록](model-freeze.json) · [구현](../../../src/pickloop/produce_rescue.py)

개발 시 이미 조사한 Open Images validation 실물 16장을 사용했다. 등록 품목 12장 중 정답이 6장에서 10장으로 늘었고 미등록 딸기 4장은 계속 보류했다. 이전 주스 실물·제품 사진 40장, 기존 공식 시험 분할에서 뽑은 유사 채소·과일 20장에서 전후 판정 변화는 각각 0장이었다. 각 유사 품목에서 파일명 순서대로 처음 4장을 선택했다. 스트레스 검사에서는 실서비스에서 조건 미충족으로 건너뛸 사진도 모델에 별도로 통과시켜 원시 ImageNet 결과를 보존했다. 기존 주스 오인식은 이 기능의 개선 범위에서 제외했다. [개발 사진별 결과](development.csv) · [개발 집계](development.json)

동결 이후의 시험은 별도 수집자가 만든 이미지 ID·경로·SHA-256만 읽는다. 공식 원본 5,502장, 이전 외부 후보 58장과 시험 사진 상호 간 파일·픽셀·지각 해시를 비교한다. 원본 또는 단색 테두리 제거본에서 pHash와 dHash가 모두 8비트 이내인 경우도 제외한다. 최종 수락된 사진당 기존 기본값과 선택 기능을 한 차례만 실행하고 예측 로그에 SHA-256을 부여한다. 별도 정답 명세는 예측 봉인 후에 읽어 사진별 결과와 짝지은 전이를 집계한다. DINOv2·ImageNet 사전학습 자료 전체와의 원본 중복 여부는 확인할 수 없다. 원본 외부 사진은 저장소에 포함하지 않는다.

## 가중치와 재현

ResNet-18 가중치의 공식 파일은 약 44.7 MiB다. 전체 SHA-256은 `f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec`다. 파일을 제공하지 않으면 공개 PyTorch 배포 위치에서 받아 검증 후 캐시에 보관한다. [모델 설명](https://pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html) · [고정 가중치](https://download.pytorch.org/models/resnet18-f37072fd.pth) · [기존 81종 모델 설치](../../grocery-catalogue.md)

```bash
# 기존 58개 외부 사례를 원본 해시로 복구
python scripts/fetch_recognition_photos.py /tmp/prior-photo-cache

# 발표한 익명 시험 명세와 동일한 독립 시험 사진을 원본 출처에서 복구
python scripts/fetch_recognition_photos.py /tmp/prior-photo-cache --cohort produce
BLIND_CSV=/tmp/prior-photo-cache/produce/blind.csv
LABELS_CSV=/tmp/prior-photo-cache/produce/labels.csv
LABELS_SHA256=$(sha256sum "$LABELS_CSV" | cut -d ' ' -f 1)

# 기존 개발 사진 및 근접 품목 재평가
python scripts/evaluate_produce_rescue.py development \
  --archive "$GROCERY_ARCHIVE" --prior-cache /tmp/prior-photo-cache \
  --out /tmp/produce-development

# 별도 수집자가 정답 파일의 SHA-256을 제공하면 먼저 익명 추론만 실행
python scripts/evaluate_produce_rescue.py infer \
  --archive "$GROCERY_ARCHIVE" --prior-cache /tmp/prior-photo-cache \
  --blind "$BLIND_CSV" --labels-sha "$LABELS_SHA256" --out /tmp/produce-heldout-run

# 봉인된 예측에 정답을 연결
python scripts/evaluate_produce_rescue.py score \
  --labels "$LABELS_CSV" --out /tmp/produce-heldout-run
```
