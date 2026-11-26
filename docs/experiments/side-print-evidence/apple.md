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

## 2014년 스웨덴 실물 포장의 원재료 면

스톡홀름대학교의 Inga-Lena Bohm Fiederling은 스웨덴 소매용 포장의 각 면을 촬영했다. 논문 부록 A의 PDF 31번째 페이지에 사과주스 정면, 설명, 영양, 원재료 면이 한 사진으로 실렸다. 사과 정면 왼쪽 아래에 1 L가 보인다. 해당 사진에서 GTIN은 읽지 못했다. 같은 페이지의 단일 레드자몽 사진은 별개 표본이다. [2014년 논문](https://www.diva-portal.org/smash/get/diva2%3A784978/FULLTEXT01.pdf#page=31)

이 1 L 포장은 018과 인쇄판이 다르다. 논문의 스웨덴어 원재료 단락은 3줄이며, 각 언어가 끝난 뒤 재활용 지침과 제조사 로고가 아래쪽을 채운다. 018의 첫 단락은 약 7줄이고 아래에는 사과 단면 그림이 보인다. 정면의 ‘100%’도 논문 사진에서는 독립된 줄이다. 018과 구형 1.75 L 대조 사진에서는 뒤 문구가 같은 줄에서 시작된다. 인쇄 흔적이 남아 있다는 이유로 두 사진을 같은 규격으로 등록하지 않았다. [구형 1.75 L 실제 정면](https://images.openfoodfacts.net/images/products/731/086/508/1650/1.jpg)

기존과 같은 방법으로 2014년 1 L 원재료 첫 세 줄도 대조했다. 018의 상관은 **0.533**, 바코드로 1 L를 확인한 005는 **0.457**이었다. 같은 두 사진에서 1.75 L 원문의 상관은 각각 **0.633**, **0.611**이었다. 결과는 사진을 새로 확보하면 포장 세대가 맞는지도 확인해야 함을 보여 준다.

60쪽 PDF 원본은 7,257,221바이트이며 SHA-256은 `33ed2cc12fcb32988166faf79f57910f28b511e40355238f4ac553822c1cbea3`이다. PDF의 JPEG 객체 132는 711 × 404 px, 75,783바이트이며 SHA-256은 `3e4751e3778cc579f56f3c0e9ad8b87d7cd2a497212d4c29e89e0efa029041d0`이다. 두 DiVA 호스트에서 이 객체의 바이트와 JPEG 끝 표식이 일치했다. 아래 명령으로 무손실 추출한 JPEG 중 이 해시와 일치하는 파일을 넘긴다. [DiVA 미러](https://mdh.diva-portal.org/smash/get/diva2%3A784978/FULLTEXT01.pdf)

```sh
pdfimages -f 31 -l 31 -j paper.pdf /tmp/apple-appendix
sha256sum /tmp/apple-appendix-*.jpg
python docs/experiments/side-print-evidence/probe_apple.py /tmp/pickloop-apple-print --study-figure /tmp/apple-appendix-001.jpg
```

## 세 소실점으로 본 몸체 비율

정면의 가로·세로에 더해, 옆면에 인쇄된 글줄들이 사진의 어느 점으로 수렴하는지 측정했다. 기존 공식 훈련 사진 014의 정면에 대응점을 맞추고, 평가 사진마다 지정한 옆면 사각형 안에서 인쇄 기준선을 추적했다. 정사각 픽셀, 왜곡이 없는 핀홀 카메라, 직각을 이루는 몸체를 가정했다. 세 소실점의 직교 조건으로 주점·초점거리를 구한 뒤, 윗면의 공통 꼭짓점에서 앞쪽과 옆쪽 두 모서리의 길이 비를 추정했다. 방향·비율이 주어진 합성 상자에서는 세로/너비 2.6, 깊이/너비 1.1을 수치 오차 범위에서 복원했다.

각 사진을 가로 방향 네 구간에서 측정하고, 글줄을 홀짝으로 나누어 다시 계산했다. 각 구간에서 줄을 복원추출하고 지정한 모서리 좌표에 표준편차 1 px의 흔들림을 주는 계산을 500회 수행했다. 아래는 줄 전체를 쓴 네 구간별 5~95백분위의 가장 작은 값과 가장 큰 값이다. 인쇄 영역과 모서리를 수동 지정했으며, 단일 사진 안에서 여러 번 측정해 얻은 **민감도 범위**다. 제품의 실측 치수나 매장별 신뢰구간을 뜻하지 않는다.

| 원본 | 한 구간에서 추적한 줄 수 | 정면 인쇄의 세로/너비 | 모서리로 추정한 깊이/너비 |
|---|---:|---:|---:|
| RR-8e14… (018) | 35~38 | 2.59~2.67 | 0.77~0.96 |
| RR-7660… (005), 바코드 1 L 확인 | 34~37 | 2.08~2.31 | 0.47~0.62 |
| 외부 1 L 정면·옆면, 원본 82 × 225 px | 33~41 | 양의 초점거리를 얻지 못함 | 계산 불가 |

두 아카이브 사진은 같은 1 L 클래스인데도 자세에 따라 추정비가 크게 달랐다. 외부 1 L 사진의 옆면 너비는 약 18 px이고, 구형 1.75 L 참고 사진 1·3은 거의 같은 정면 구도여서 옆면 방향을 측정할 수 없다. 관측된 비율만으로 구형 두 규격을 가르는 경계값은 검증할 수 없었다. 공개 제조사 기록에는 **핀란드에도 God Morgon Classic 사과주스 1 L가 별도 GTIN 6415130050506으로 판매**된다고 명시돼 있다. 스웨덴 등록품은 7310865074225, 비교한 스웨덴 1.75 L는 7310865081650이다. 핀란드 실물 제품의 원재료 사진은 첫 단락이 FI로 시작한다. 018에서 국가 구별 문구와 용량을 동시에 읽었다는 근거도 없다. [스웨덴 1 L](https://www.dabas.com/productsheet/07310865074225) · [스웨덴 1.75 L](https://www.dabas.com/productsheet/07310865081650) · [핀란드 제조사와 GTIN](https://www.eckes-granini.fi/tuotehaku/god-morgon-classic-apple-juice-1-l) · [핀란드 1 L 원재료 면](https://images.openfoodfacts.net/images/products/641/513/005/0506/1.jpg) · [외부 스웨덴 1 L 사진](https://images.openfoodfacts.net/images/products/731/086/507/4225/1.jpg)

**이 상품을 확정할 수 있는 추가 단서 하나는 같은 팩에 인쇄된 바코드 전체다.** 앞뒤 여백과 막대가 잘리지 않게 한 장 더 찍어 EAN-13이 7310865074225로 해독되면, 등록품과 시장·용량을 함께 확인할 수 있다. 018 자체는 보류로 기록한다.

```sh
python docs/experiments/side-print-evidence/probe_apple_geometry.py /tmp/pickloop-apple-print
```

## 출처와 이용 범위

- 원재료 사진은 Open Food Facts에 게시한 기여자들의 자료다. 이 서비스는 데이터베이스에 ODbL, 기여자가 올린 사진에 CC BY-SA 조건을 안내한다. 포장에 담긴 로고·그래픽에는 제3자 권리가 있을 수 있다. [Open Food Facts 이용 조건](https://world.openfoodfacts.org/terms-of-use)
- 훈련·아카이브 사진은 Marcus Klasson, Cheng Zhang, Hedvig Kjellström의 Grocery Store Dataset 고정 커밋을 사용했다. 원본 저장소에 MIT 라이선스가 있다. 이 보고서는 링크와 해시를 제공한다. [데이터셋과 인용 정보](https://github.com/marcusklasson/GroceryStoreDataset/tree/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc) · [라이선스](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/LICENSE)
- DiVA 논문 사진과 Smaktestarna 시음 사진은 각각 학위 논문 저자와 시음 기사가 출처다. 사진의 별도 재배포 허가는 확인하지 못해, 원본은 외부 링크로 남겼다. Dabas·Eckes-Granini·God Morgon의 상품 정보는 GTIN, 외곽 치수와 뚜껑 변경 시기를 검증하는 데 사용했다.

## 용량 숫자만 따로 대조한 가림 시험

실제 스웨덴 1.75 L 사과주스 원재료 사진은 SE·FI·DK·NO·UK·DE 여섯 단락에 용량을 반복한다. 스웨덴 1 L 확대 사진은 SE 한 줄에서 ‘1 L’를 확인할 수 있고, 핀란드 1 L 사진은 FI·SE·UK 세 단락에서 확인할 수 있다. 반면 위 2014년 스웨덴 1 L 포장은 여섯 단락 모두 언어 기호 다음에 바로 상품 설명이 시작된다. **해당 위치에 용량을 쓰지 않은 포장**을 비교 후보에 포함한 이유다. [스웨덴 1.75 L](https://images.openfoodfacts.net/images/products/731/086/508/1650/2.jpg) · [핀란드 1 L 기준](https://images.openfoodfacts.net/images/products/641/513/005/0506/1.jpg) · [다른 핀란드 1 L 사진](https://images.openfoodfacts.net/images/products/641/513/005/0506/5.jpg)

세 후보에 실물이 있는 SE·FI·UK에서 언어 기호 끝과 용량의 예상 위치를 수동 지정했다. 같은 국소 이동·크기·기울기 범위 안에서 줄 평균을 제거한 상관을 계산했다. 가림 시험은 숫자가 있던 자리의 너비 2.4자 높이, 세로 1.4자 높이인 사각형을 인근 최저 밝기로 채운 뒤 다시 계산했다. **숫자를 가려도 1 L 점수가 더 높아지므로 이 방법은 ‘1 L’를 읽었다는 증거로 쓸 수 없다.**

| 018의 단락 | 원래 1 L 점수 | 원래 1.75 L 점수 | 원래 무표기 점수 | 용량 위치를 가린 뒤 1 L 점수 |
|---|---:|---:|---:|---:|
| SE | 0.855 | 0.545 | 0.662 | 0.900 |
| FI | 0.795 | 0.623 | 0.657 | 0.848 |
| UK | 0.768 | 0.619 | 0.586 | 0.908 |

핀란드 1 L 사진 5는 별도 등록 사진 1과 비교해 세 단락 모두 1 L가 가장 높았다. 바코드로 확인한 스웨덴 1 L 대조 005도 같은 결과를 냈다. 반례는 실물 **오렌지주스 1.75 L, GTIN 7310865074768**이다. 이 사진의 SE 단락은 가리기 전에는 1.75 L 점수가 0.618, 1 L 점수가 0.395였으나 가린 뒤에는 1.75 L 0.632, **1 L 0.786으로 역전**됐다. 주변 획과 빈 공간의 경계가 점수에 영향을 주는 경우가 있다. [1.75 L 오렌지 대조 사진](https://images.openfoodfacts.net/images/products/731/086/507/4768/4.jpg)

시장도 별도로 확인했다. 용량을 제외한 두 글자 기호만 비교하면 018의 두 번째 FI 단락을 SE로, 005의 두 번째 FI 단락을 UK로 판별했다. 기호와 숫자를 가리고 뒤따르는 첫 단어만 보아도, 별도 핀란드 사진 5의 실제 SE와 FI 첫 단어는 두 경우 모두 UK와의 점수가 가장 높았다. **여섯 단락처럼 보이는 배치와 숫자 후보 점수만으로는 언어 순서나 스웨덴 등록 GTIN을 확인할 수 없다.** 아카이브에서 018의 정답 클래스가 스웨덴 사과 1 L로 붙어 있다는 사실과, 업로드한 화소에서 그 상품을 확정할 수 있는지는 따로 기록했다.

같은 숫자 가림과 언어 시험을 재현하려면 위에서 추출한 JPEG 객체 132를 인자로 넘긴다. 추가 원문은 핀란드 사과 GTIN 6415130050506의 Open Food Facts 사진 1·5, 스웨덴 오렌지 GTIN 7310865074768의 사진 4다. 모든 출처와 원본 SHA-256, 단락별 좌표가 스크립트에 들어 있다. [국소 대조·가림 재현 코드](probe_apple_prefixes.py)

```sh
python docs/experiments/side-print-evidence/probe_apple_prefixes.py /tmp/pickloop-apple-print /tmp/apple-appendix-001.jpg
```

## 상품군과 등록 규격

별도 81품목 판별기의 일반 분류 경로도 실제 원본으로 재실행했다. 018의 상품군 예측은 `God-Morgon-Apple-Juice`였다. 옆면 15장 전체에서는 이 경로가 상품군까지 맞힌 사진이 5장이었다. 이 경로의 사과주스 클래스에는 용량이나 판매국 레이블이 없다. 018의 등록 규격 판정은 보류로 집계했다. [81품목의 사진별 기존 예측과 원본 해시](../grocery-catalogue/predictions.csv)
