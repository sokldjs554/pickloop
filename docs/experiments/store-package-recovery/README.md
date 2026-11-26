# 잘린 포장과 기울어진 바코드 판독

Willys Landskrona Infarten의 같은 입력을 기본 파일 선택창에서 다시 읽었다. 사과 1 L는 서로 떨어진 두 줄에서 옆면 EAN 13자리가 일치했다. 혼합주스 1 L는 기준 포장을 투영한 뒤 로고와 두 맛 표기가 일치했다. 두 경우 모두 상품 사진 판정만 반환했다. 등록 코드의 일반 광학 판독과 인쇄 충돌 검사는 주문 규격 확정에 별도로 필요하다. [이전 판정](../oblique-packages/landskrona/browser.jsonl) · [수정 후 판정](field-browser.jsonl)

| 시험 입력 | 결과 |
|---|---|
| 보완에 사용한 스웨덴 사과 1 L, 혼합주스 1 L | 보류 2건에서 상품명 정답 2건 |
| 같은 곳의 사과 1.75 L | 보류 |
| 같은 원본의 옆 팩 두 개 | 혼합주스 정답, 바코드가 잘린 사과주스 보류 |
| 노르웨이 두 매장의 사과 1.75 L | 두 건 모두 보류 |
| 기존 사과 옆면 2장, 혼합주스 옆면 5장 | 사과 0 → 0, 혼합주스 0 → 2 |
| 기존 등록품 옆면 전체 15장, 앞면 45장 | 옆면 3 → 5, 앞면 29 → 29 |
| 기존 미등록 단일 레드자몽 14장 | 등록 이름 오인 0 → 0 |

스웨덴 사진 두 장은 한 매대에서 같은 날 촬영했다. 인접한 팩을 자른 두 건도 같은 원본이다. 노르웨이 사과 1.75 L는 Kiwi Bøhmergaten과 Bunnpris Møllendalsbakken의 서로 다른 사진이다. 기존 아카이브 전체 74장에서는 혼합주스 옆면 두 장의 판정만 바뀌었다. 새 매장에서 촬영한 두 등록 상품의 전체 옆면 평가 사진은 사과 0건, 혼합주스 0건이다. [원본·좌표·바코드·해시](field-inputs.csv) · [아카이브 74장](archive-browser.jsonl) · [이전 결과](../oblique-packages/archive-browser.jsonl)

기존 공개 사진 8장의 판정은 같았다. 과거 검증용 사진 20장에서는 혼합주스 1장이 보류에서 정답으로 바뀌었다. [공개 사진](public-browser.jsonl) · [과거 검증용 사진](legacy-validation-browser.jsonl)

## 판정 근거

- **기울어진 바코드**. 방향이 유사한 줄무늬를 찾아 여러 투영과 평행선을 시험한다. 등록 코드 패턴으로 샘플링 위치를 제안한 뒤 각 숫자와 선두 패리티를 다시 판독한다. 체크섬이 유효하고 최소 8픽셀 떨어진 두 줄에서 전체 코드가 일치해야 한다. 이 제한된 탐색은 등록된 후보를 위한 사진 판정에만 사용한다.
- **맛 이름이 보이는 일부 앞면**. 제조사 사진 한 장과 공식 학습 분할 사진 두 장에서 특징을 추출했다. 사진 중앙 근처에 있는 포장의 로고, 오렌지 표기, 레드자몽 표기가 동일한 투영에서 각각 맞아야 한다. 단일 레드자몽 포장에 잘못 이름 붙이는 것을 막기 위해 두 맛 표기를 따로 검사한다. 참고 사진에는 매장 시험 이미지가 포함되지 않는다. [등록 원본·영역](enrollment.json)
- **식별 한계**. 기존 사과 사진에는 비슷한 1.75 L 구형 포장과 같은 맛 이름과 과일 그림이 보인다. 두 사진에서 규격을 가를 표기까지 검증하지 못했다. 문자·바코드·시각 판정이 충돌하면 보류한다.

## 재현

아래 명령은 원본 4장을 내려받아 기록된 좌표에서 7개 입력을 만들고, 파일명을 숨겨 브라우저에서 실행한다. PNG 입력과 판별기 파일은 체크섬을 검증한다. 저장소 루트에서 Pillow, Playwright와 Chromium이 있는 환경으로 실행한다.

```sh
python docs/experiments/oblique-packages/landskrona/replay.py --release recovery --out /tmp/pickloop-store-results.jsonl
```

인식 기준 자료를 다시 만들려면 enrollment.json의 각 source를 file 이름으로 다운로드한 뒤 다음 명령을 실행한다. [판별기 체크섬](browser-freeze.json)

```sh
PYTHONPATH=src python scripts/build_printed_regions.py docs/experiments/store-package-recovery/enrollment.json /tmp/reference-images /tmp/registered-detail-gallery.json
cmp /tmp/registered-detail-gallery.json web/data/registered-detail-gallery.json
```

공개 예시 PNG 두 장은 freso가 제공한 Open Prices 원본에서 상품 영역만 자른 파일이다. 두 파생 파일에 CC BY-SA 4.0을 적용한다. [사과 원본](https://prices.openfoodfacts.org/img/0328/1L2xNrXpR1.webp) · [혼합주스 원본](https://prices.openfoodfacts.org/img/0328/zWHdSjgtcV.webp) · [Open Prices 이미지 이용 조건](https://prices.openfoodfacts.org/about) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
