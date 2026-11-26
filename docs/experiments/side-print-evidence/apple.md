# 사과주스 구형 포장의 옆면에서 용량을 구별할 수 있는가

아카이브의 사과주스 사진 두 장에서 같은 맛의 1 L와 1.75 L를 구별하는 방법을 시험했다. 옆면 원재료 문구를 대조하자 두 장 모두 1.75 L 원문과의 상관이 더 높았다. 그중 한 장은 바코드에서 1 L가 확인된다. 이 결과로는 나머지 한 장의 용량을 판정할 수 없다. 이 실험은 기존 평가 사진에서 보류 원인을 조사한 기록이다. 새 매장 평가 건수에 포함하지 않았다.

## 무엇을 비교했나

| 용도 | 출처 | 원본 SHA-256 |
|---|---|---|
| 등록 1 L 원재료 원문. 1,791 × 336 px | [Open Food Facts / blackfatrat, 사진 3](https://images.openfoodfacts.net/images/products/731/086/507/4225/3.jpg) | `00b7083b7cd829cb0b10dd80d7680a67d1f63e7d00879279aa37ca8e4e0a8f4c` |
| 1.75 L 원재료 원문. 969 × 1,200 px | [Open Food Facts / kiliweb, 사진 2](https://images.openfoodfacts.net/images/products/731/086/508/1650/2.jpg) | `7ab853525829a5aae3f9f53039d96fc67277995e7e2c4c04c7a695428747696e` |
| 용량을 읽지 못한 옆면. 348 × 348 px | [GroceryStoreDataset 공식 test, 018](https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/God-Morgon-Apple-Juice/God-Morgon-Apple-Juice_018.jpg) | `8e1405c5d1997279c67f93b9e81effd077c3bc60ac673194e8c1b479337cc800` |
| 바코드 7310865074225를 별도로 읽은 1 L 대조 사진. 348 × 348 px | [GroceryStoreDataset 공식 test, 005](https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/God-Morgon-Apple-Juice/God-Morgon-Apple-Juice_005.jpg) | `7660e2282261b043c6cc72f671782a349c095f46a2fb74fb85d8bd51f30df168` |

등록품 GTIN은 7310865074225, 다른 규격은 7310865081650이다. Open Food Facts의 서로 다른 GTIN 아래 등록된 확대 사진에서는 두 규격의 인쇄가 다르다. 스웨덴어 원재료 표기의 첫 부분에서 용량 표기와 뒤따르는 단어의 위치가 바뀐다. 두 참고 사진의 등록 시점·인쇄판도 다를 수 있다. 같은 문구가 모든 시기에 유지됐다는 자료는 확보하지 못했다. 두 평가 사진은 대조를 받는 쪽으로만 사용했다. 바코드 결과와 클래스명은 옆면 점수 계산에 입력하지 않았다. [1 L 사진 메타데이터](https://world.openfoodfacts.net/api/v2/product/7310865074225.json?fields=code,images) · [1.75 L 사진 메타데이터](https://world.openfoodfacts.net/api/v2/product/7310865081650.json?fields=code,images) · [바코드 판독 기록](../side-panel-retry/browser.jsonl)

## 원재료 문구

018에서 옆면의 윗변은 약 72 px이고, 005에서는 약 58 px이다. 글자 한 줄이 원본에서 차지하는 높이는 수 픽셀이다. 사람이 원본에서 옆면 네 꼭짓점을 지정하고 투시를 보정했다. 원재료 첫 세 줄의 확대 원문과 각 사진을 대조하면서 위치, 축척, 기울기와 원근을 두 후보에 같은 범위로 허용했다. 줄 단위로 평균 밝기를 제거한 뒤 정규화 상관계수를 최대화했다. 수동 영역 지정을 포함한 진단 실험으로, 자동 판독기의 정확도나 정답 확률을 뜻하지 않는다.

| 평가 사진 | 1 L 인쇄와 최대 상관 | 1.75 L 인쇄와 최대 상관 | 결과 해석 |
|---|---:|---:|---|
| RR-8e14… (018) | 0.552 | 0.633 | 1 L를 고를 근거 부족 |
| RR-7660… (005) | 0.453 | 0.611 | 최대값으로 선택하면 바코드로 확인한 1 L를 잘못 분류 |

재현 스크립트가 네 원본을 작업 디렉터리에 받고 SHA-256을 검사한다. 참조 이미지나 원본 매장 사진을 저장소에 배포하지 않는다. 검증 환경은 Python 3.12.14, NumPy 2.2.6, OpenCV 4.11.0, SciPy 1.15.3이다. 동일 입력과 난수 시드로 소수 셋째 자리까지 재현했다. [영역 좌표·왜곡 범위·탐색 코드](probe_apple.py)

```sh
python docs/experiments/side-print-evidence/probe_apple.py /tmp/pickloop-apple-print
```

## 외형과 포장 치수

상품정보의 낱개 너비 × 깊이 × 높이는 1 L가 70 × 80 × 230 mm, 1.75 L가 91 × 91 × 248 mm다. 이 수치는 뚜껑과 지붕을 포함한 외곽 치수다. 옆면에서 보이는 종이 몸체의 사각형 높이는 별도로 주어지지 않는다. 제조사는 2024년 두 용량에 고정형 뚜껑을 순차 도입했다고 밝혔다. 촬영 시기, 경사와 가림에 따라 보이는 뚜껑 너비가 달라져 현재 규격만으로 구형 포장의 용량을 정하지 않았다. [Dabas 1 L](https://www.dabas.com/productsheet/07310865074225) · [Dabas 1.75 L](https://www.dabas.com/productsheet/07310865081650) · [God Morgon 포장 변경](https://www.godmorgon.se/hallbarhet-/foerpackningsloesningar/)

정면의 평면 비율이 촬영 보정값에 얼마나 민감한지도 확인했다. 기존 훈련 사진 014의 정면 228 × 580 px와 평가 사진 사이의 호모그래피를 SIFT 특징과 RANSAC으로 추정했다. 수평·수직 소실점이 직교하도록 초점거리를 구했고, 주점의 두 좌표를 각각 영상 폭·높이의 30%, 40%, 50%, 60%, 70%로 바꿨다. 초점거리가 영상 긴 변의 0.45~1.9배인 조합에서 정면 세로/가로 추정비는 018에서 **1.96~3.25** (22개 조합), 005에서 **1.81~3.02** (16개 조합)였다. 이는 가정한 보정값에 대한 민감도 범위다. 확률 구간이나 실측 치수로 사용할 수 없다. 두 사진 모두 카메라 내부 보정값이 없고 018은 아래쪽이 잘렸다. [훈련용 정면 좌표와 출처](../registered-photo-recall/enrollment.json)

## 다른 매장과 촬영 출처

2026-11-26에 Open Prices를 GTIN별로 검색했다. 등록 사과 1 L, 혼합주스 1 L의 가격 기록은 각각 한 건이었고 둘 다 이미 사용한 스웨덴 Willys Landskrona 사진이었다. 사과 1.75 L의 가격 기록 16건에 연결된 매대 사진을 모두 확인했다. 촬영일은 2025-03-22~2026-10-21이며 현대 포장이 보인다. 구형 사과 옆면의 용량을 독립 검증할 사진을 이 검색에서 찾지 못했다. 같은 매장·포장을 다시 확인한 사진은 새 평가 건수에서 제외했다. 이 저장소에는 가격 기록의 링크만 담았다. Open Prices의 데이터 안내는 ODbL을 명시한다. [사과 1 L 검색](https://prices.openfoodfacts.org/api/v1/prices?product_code=7310865074225&size=100) · [혼합 1 L 검색](https://prices.openfoodfacts.org/api/v1/prices?product_code=7310860007259&size=100) · [사과 1.75 L 검색](https://prices.openfoodfacts.org/api/v1/prices?product_code=7310865081650&size=100) · [Open Prices 이용 조건](https://openfoodfacts.github.io/open-prices/guides/data/#license)

2016년 스웨덴 시음 기사 사진에서는 정면 아래의 1 L 표기를 직접 확인했다. 이 사진에는 GTIN과 원재료 옆면이 보이지 않으며 매장 촬영 여부나 재배포 조건도 확인할 수 없었다. 구형 디자인을 비교하는 출처 링크로만 남겼다. 원본 SHA-256은 `e6472f0e9996bde449f26279dfbc2c170c6063b4f6e99cef3cb0e03b85dfadc2`이다. [Smaktestarna 시음 기사](https://smaktestarna.wordpress.com/smaktester/applejuicetest/) · [2016년 원본 사진](https://smaktestarna.wordpress.com/wp-content/uploads/2016/03/test-c3a4ppeljuice-046.jpg)
