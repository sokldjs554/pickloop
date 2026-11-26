# God Morgon 사과·혼합주스 매장 사진 판독 기록

2026년 10월 21일 스웨덴 Willys Landskrona Infarten에서 촬영한 매대 원본 2장에서 상품 영역 3곳을 골랐다. 공개 v23과 같은 포장 특징 비교기, 기준 사진 데이터, 화면 판정 스크립트의 SHA-256을 확인하고 로컬 Chromium 156.0.8078.79의 사진 선택창으로 실행했다. 두 원본의 촬영자는 Open Prices 사용자 freso다. 상품 코드는 해당 지점의 가격 기록과 각 상품 바로 아래의 가격표로 대조했다. 원본 좌표와 입력 파일 해시는 판독 전에 정했다. 가격표는 판별기 입력에서 제외했다. [혼합주스 매대](https://prices.openfoodfacts.org/img/0328/zWHdSjgtcV.webp) · [사과주스 매대](https://prices.openfoodfacts.org/img/0328/1L2xNrXpR1.webp) · [실행 버전](../candidate-models.json)

| 입력 | 확인한 상품 | 보이는 면 | 브라우저 판정 |
|---|---|---|---|
| L01 | 사과 1 L, 7310865074225 | 왼쪽 팩의 일부 앞면과 오른쪽 옆면. 팩 윗부분이 잘렸다. | 보류 |
| L02 | 오렌지·레드자몽 1 L, 7310860007259 | 왼쪽에서 두 번째 팩의 앞면과 윗면 | 보류 |
| L03 | 사과 1.75 L, 7310865081650 | 오른쪽 팩의 앞면과 일부 옆면. L01과 같은 사진이다. | 보류 |

세 입력 모두 바코드를 읽지 못했고 등록 포장을 구별할 특징이 부족하다고 표시했다. L02의 OCR은 영어 맛 설명 일부를 읽었으나 오렌지와 레드자몽이라는 상품 표기는 복원하지 못했다. 미등록 대조품 L03에 등록 1 L 이름을 붙인 경우는 없었다. 이 세 영역은 한 지점, 한 촬영일의 두 원본에서 나온 관찰이다. 매장 전체의 인식률을 추정하기에는 부족하다. [브라우저 응답](browser.jsonl) · [같은 입력에서 다시 확인한 OCR 원문](ocr.json) · [혼합주스 가격·바코드 기록](https://prices.openfoodfacts.org/api/v1/prices?proof_id=142500) · [사과 두 규격의 가격·바코드 기록](https://prices.openfoodfacts.org/api/v1/prices?proof_id=142501)

## 옆면 시험의 현재 범위

해당 촬영일·매장의 공개 증빙 목록과 스웨덴 과즙 음료 가격표 사진을 추가 조사했다. 등록 팩의 옆면이 온전히 보이고 지점과 규격까지 확인된 새 입력은 사과 0장, 혼합주스 0장이었다. L01은 새 매장 부분 옆면 사례로 남긴다. L02는 앞면 비교 사례다. 두 사진은 이후 판별기 개발에 참조하면 재시험 자료로 표시한다. [매장의 당일 자료](https://prices.openfoodfacts.org/api/v1/proofs?location_id=942&date=2026-10-21&size=100)

기존 옆면 원본 7장도 같은 브라우저의 파일 선택창으로 재실행했다. 사과 0/2장, 혼합주스 0/5장이 정답이었다. 5장은 판별할 특징이 부족하다고 표시했고, 2장(사과 1장과 혼합주스 1장)은 다른 규격과 구별하기 어렵다고 표시했다. 오인과 실행 오류는 없었다. 새 매장과 기존 아카이브는 각각 집계했다. [7장의 재실행 결과](archive-replay.jsonl)

## 재현

저장소 루트에서 Pillow, Playwright와 Chromium이 있는 환경으로 실행한다. 아래 명령은 원본을 임시 디렉터리에 다운로드하고 사전에 기록한 좌표로 자른다. 원본과 입력 바이트를 확인한 뒤 기존 평가 스크립트로 사진을 제출한다. 원본, 정답 바코드, 주변 가격표에 대한 메타데이터는 판별기에 전달하지 않는다. [입력 좌표·해시](inputs.csv) · [재현 스크립트](replay.py)

```sh
git worktree add --detach /tmp/pickloop-v23 cf4c035135677480ef137c8b7a9439e1476e10c0
python docs/experiments/oblique-packages/landskrona/replay.py --web /tmp/pickloop-v23/web --out /tmp/landskrona-results.jsonl
```
