# 실물 상품 사진에서 측정한 품목 인식

기존 PickLoop 모델에 실제 매장에서 스마트폰으로 촬영한 포장 상품 사진 781장을 입력했다. 기존 모델은 우유 사진 2장을 두 줄 표식 상품인 `SKU-RED-B`로 오인했다. 같은 인코더에 실제 주스 두 종을 새로 등록한 실험에서는 등록 상품 54장 중 46장을 맞혔고, 등록하지 않은 상품 727장 모두를 주스로 받아들였다. 이 결과는 상품 등록 시 미등록품 거부 기준을 다시 검증해야 한다는 근거다.

| 시험 | 등록품 정답 / 전체 | 등록품 오분류 | 등록품 거부 | 미등록품 오수락 / 전체 |
|---|---:|---:|---:|---:|
| 기존 빨간 상자 A/B, 배포 체크포인트 그대로 | 실물 A/B 사진 0장, 미측정 | — | — | 2/781 (0.26%) |
| Bravo 사과·오렌지주스 새 등록, 같은 인코더와 거부 임계값 | 46/54 (85.19%) | 8/54 | 0/54 | 727/727 (100%) |

사과주스는 23장 중 22장이 정답이고 1장을 오렌지주스로 판정했다. 오렌지주스는 31장 중 24장이 정답이고 7장을 사과주스로 판정했다. 미등록품은 사과주스 683장, 오렌지주스 44장으로 판정했다. 각 비율의 단위는 사진 한 장이다. 같은 상품을 여러 번 촬영했으므로 781개 독립 상품에 대한 추정으로 확대할 수 없다.

기존 모델의 오수락 두 건은 모두 Arla Standard Milk였다. 최근접 프로토타입 거리는 0.9573과 0.9176으로, 고정 임계값 1.08327 안에 들었다. 사진과 거리를 함께 살펴볼 수 있다. [우유 015 원본](https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Milk/Arla-Standard-Milk/Arla-Standard-Milk_015.jpg) · [우유 028 원본](https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Milk/Arla-Standard-Milk/Arla-Standard-Milk_028.jpg) · [새 등록 실험에서 틀린 사과주스 022](https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/Bravo-Apple-Juice/Bravo-Apple-Juice_022.jpg)

## 사진과 평가 방법

- **출처.** Klasson, Zhang, Kjellström의 *A Hierarchical Grocery Store Image Dataset with Visual and Semantic Labels* (WACV 2019)에서 매장 자연 사진만 사용했다. 저자들은 18개 매장에서 촬영했고 한 매장에서 찍은 같은 상품의 사진을 한 분할에 넣었다. 촬영 거리·방향과 배경은 실제 매장 조건을 따른다. 사진별 카메라 자세, 가림 비율, 조도는 제공되지 않는다. [논문 3절](https://arxiv.org/abs/1901.00711) · [출처 및 저자 이용 안내](https://github.com/marcusklasson/GroceryStoreDataset/tree/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc)
- **대상 선정.** 평가 전에 공식 클래스 표에서 포장 상품의 첫 두 ID인 28과 29를 등록 대상으로 지정했다. 비슷한 외관의 같은 브랜드 주스 두 종이다. 공식 `train.txt`의 사과 25장과 오렌지 32장만 등록에 사용했다. 평가는 공식 `test.txt`의 `Packages/` 전량인 31개 상품 781장으로 고정했다. 새 등록 기준으로 나머지 29개 상품이 미등록이다. 기존 A/B 기준으로는 31개 모두가 미등록이다. 838개 등록·평가 파일의 SHA-256이 모두 달랐다. [클래스 표](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/classes.csv)
- **모델 입력.** 저자가 배포한 각 사진 전체를 EXIF 방향 보정 후 RGB로 변환했다. 실제 `AppearanceModel.predict`가 이를 64×64로 리사이즈한다. 사진에는 선반, 손, 주변 상품이 들어갈 수 있으며 채점 단위는 해당 사진에 지정된 상품이다. 검출기, 깊이 좌표, 그리퍼를 거치지 않는 사진 단위 시험이다.
- **등록과 거부.** 기존 모델은 배포된 가중치·프로토타입·임계값으로 추론했다. 별도 실험에서는 57장의 동결 인코더 임베딩으로 각 주스의 평균을 구해 L2 정규화했다. 이 두 프로토타입에만 실제 상품 이름을 붙였다. 거리 임계값 1.0832704403과 마진 0.0은 그대로 적용했다. 두 시험 모두 테스트 사진으로 임계값을 조정하지 않았다. 새 등록품에 기존 A/B 분류기의 confidence 값은 의미가 없어 채점에 사용하지 않았다.
- **이용 조건.** 원 저장소는 MIT License, Copyright (c) 2019 Marcus Klasson을 명시하고, 저자는 데이터 다운로드 및 모델 적용을 허용한다. 이 저장소에는 사진·아이코닉 이미지·상품 로고를 복제하지 않고 원본 경로, 해시, 수치만 남겼다. [라이선스 원문](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/LICENSE)

## 후속 시험에서 거부 임계값을 낮춘 결과

727건의 오수락을 확인한 뒤 **새로 등록한 주스 프로토타입만** 대상으로 오프라인 후속 시험을 진행했다. 사전에 검증용 미등록 사진의 최대 5%만 수락하는 거리 기준을 정하고, 아직 점수를 보지 않은 공식 테스트 세트의 모든 과일·채소 사진을 추가 평가 대상으로 정했다. 5%는 이 시험의 검증 표본 내 예산이다. 현장 오류율을 보장하지 않는다.

| 공식 분할과 용도 | 등록품 정답, 기존 → 조정 | 조정 후 등록품 거부 | 미등록품 오수락, 기존 → 조정 |
|---|---:|---:|---:|
| 검증용 포장 상품, 임계값 산정 | 7/9 → 0/9 | 9/9 | 91/91 → 4/91 (4.40%) |
| 앞서 확인한 테스트 포장 상품, 재분석 | 46/54 → 3/54 | 51/54 | 727/727 → 36/727 (4.95%) |
| 처음 평가한 과일·채소 50종, 전부 미등록 | 해당 없음 | 해당 없음 | 1,539/1,704 → 46/1,704 (2.70%) |

공식 검증용 포장 상품 100장 중 등록 주스는 9장, 미등록품은 91장이었다. 미등록품 거리 오름차순에서 다섯 번째 거리보다 작은 가장 가까운 부동소수점 값과 기존 임계값 중 작은 값을 택했다. 경계에 같은 거리가 여럿이면 함께 거부한다. 이 규칙으로 얻은 임계값은 0.06458793580532073이었다. 마진, 57장의 등록 집합, 인코더 및 프로토타입은 앞선 실험과 같다. 두 테스트 집합을 확인한 뒤 추가 조정은 하지 않았다. 등록 57장, 검증 100장, 재분석 781장, 신규 미등록 1,704장을 합한 2,642장의 원본 바이트 해시는 모두 달랐다.

재분석에서 미등록 오수락은 691건 줄었지만 등록품 정답도 46건에서 3건으로 줄었다. 바뀐 기준으로 등록품 51건을 보류했고 다른 등록품으로 잘못 수락한 건수는 0이었다. 같은 출처에서 따로 보관한 과일·채소 결과는 이 50종에 대한 거부 성능만 보여 준다. 새 등록의 두 설정 모두 운영 로봇의 상품 선택에 적용하지 않았다. [후속 집계·실험 설정](experiments/real-photos-calibrated/summary.json) · [검증·재분석·신규 평가의 사진별 판정](experiments/real-photos-calibrated/predictions.csv)

## 공개 사진 실험 재현

저장소 루트에서 프로젝트 ML 의존성을 설치한 Python 환경으로 실행한다. 입력 ZIP은 약 119 MiB다. 아래 비교 명령은 최초 평가와 후속 시험의 집계 및 사진별 판정을 각각 대조한다.

```sh
curl -fL --retry 2 -o /tmp/pickloop-grocery.zip \
  https://codeload.github.com/marcusklasson/GroceryStoreDataset/zip/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc
PYTHONPATH=src python -m pickloop.grocery_evaluation \
  --archive /tmp/pickloop-grocery.zip --out /tmp/pickloop-grocery-results
diff -qr docs/experiments/real-photos /tmp/pickloop-grocery-results
PYTHONPATH=src python -m pickloop.grocery_evaluation --calibrated \
  --archive /tmp/pickloop-grocery.zip --out /tmp/pickloop-grocery-calibrated
diff -qr docs/experiments/real-photos-calibrated /tmp/pickloop-grocery-calibrated
```

측정 시 ZIP SHA-256은 `f2434611ed5dd472dae830d6c7fbdf4b75dfd1697ba25f1280f0a1d0ce9170b0`, 체크포인트 SHA-256은 `9a111d8a584cd48a681d80a4a6f0fc7681aedba611f1afbd43fc81d7cf459bec`였다. 스크립트는 ZIP 압축 방식이 달라져도 평가 입력을 검증할 수 있도록 등록·테스트 목록 순서, 상대 경로 및 각 JPEG 바이트의 결합 해시를 검사한다. CPU의 부동소수점 연산 구현이 다르면 거리의 마지막 자리가 달라질 수 있다.

| 결과 파일 | 내용 |
|---|---|
| [summary.json](experiments/real-photos/summary.json) | 체크포인트·분할 해시, 등록 프로토타입, 혼동행렬, 상품별 집계 |
| [registration.csv](experiments/real-photos/registration.csv) | 등록 57장의 상품, 원본 경로, SHA-256 |
| [predictions.csv](experiments/real-photos/predictions.csv) | 테스트 사진당 두 줄. 시험명, 원본 경로, 실제 상품, 정답, 예측, 거리, 판정, SHA-256 |

## 원래 A/B 실물 표식의 촬영·채점

기존 등록 상품의 실물 정답률은 별도 촬영이 필요하다. 빨간 상자의 흰 띠 한 줄을 A, 두 줄을 B로 라벨링한다. 데모의 인쇄 페이지와 저장소의 원본 텍스처를 사용할 수 있다. [인쇄용 A/B 표식](../web/labels.html) · [원본 텍스처](../assets/textures/)

1. 같은 크기의 상자에 원래 표식을 부착한다. A와 B 모두 같은 카메라·배경·거리 조건을 사용한다. 미등록군에는 빨간 유사 포장, 다른 줄 수, 다른 색 상자를 포함하고 `item_id`로 개체를 구별한다.
2. 각 물건을 들어 다시 놓고 정면, 약 30°와 60° 비스듬한 시점에서 촬영한다. 각 시점을 확산광과 한쪽 조명에서 반복한다. 표식이 전부 보이는 경우와 일부(예시 25%) 가린 경우 모두 촬영한다. 세션·실물 개체·시점·조명·가림을 기록하고, 결과를 보기 전에 평가할 사진과 정답을 확정한다. 연사 프레임을 독립 반복으로 세지 않는다.
3. 한 행에 대상 한 개를 기록한다. EXIF 방향을 반영해 표시한 원본에 대해 왼쪽 위 원점의 픽셀 경계 `x0,y0,x1,y1`를 표시한다. 오른쪽과 아래 경계는 제외한다. 표식만 잘라내지 말고 상자 전체와 좁은 여백을 포함한다. 가린 영역도 원본 그대로 유지한다. 이미 잘라 둔 사진은 네 칸을 모두 비우면 전체가 입력된다. A/B/미등록에 같은 크롭 규칙을 적용한다.

다음은 형식 예시다. 파일 이름과 숫자는 실제 촬영값으로 교체한다. `path`는 CSV 기준 상대 경로를 받으며 필수 열은 `path,truth`다.

```csv
path,truth,x0,y0,x1,y1,session,item_id,view,lighting,occlusion
photos/a01.jpg,SKU-RED-A,120,90,410,385,S1,A1,front,diffuse,0%
photos/b01.jpg,SKU-RED-B,135,80,420,355,S1,B1,30deg,side,25%
photos/u01.jpg,UNKNOWN,,,,,S1,other1,60deg,side,0%
```

```sh
PYTHONPATH=src python -m pickloop.photo_evaluation manifest /path/to/labels.csv \
  --out /tmp/pickloop-physical
```

`predictions.csv`에 사진별 정답·예측·거리·파일 해시·크롭·촬영 조건이 남는다. `summary.json`에 정답, 오분류, 등록품 거부, 미등록품 오수락을 각각 집계한다. 분모가 0인 비율은 `null`이다. 부분 지정된 크롭, 허용되지 않은 라벨 및 동일 원본 바이트의 중복은 오류로 처리한다.
