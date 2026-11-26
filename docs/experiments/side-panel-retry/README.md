# 같은 매장 사진에서 사과와 혼합주스 다시 판독하기

기존 118장의 원본을 Chromium 파일 선택창에 다시 올렸다. 촬영 장소와 사진은 이전 평가와 같다. 새 매장에서 촬영한 전체 옆면 원본은 사과 0건, 혼합주스 0건이다. [이전 브라우저 판정](../side-panel-lettering/browser.jsonl) · [이번 브라우저 판정](browser.jsonl) · [판독기 체크섬](browser-freeze.json)

| 촬영 조건 | 이전 | 이번 |
|---|---:|---:|
| 사과 1 L 옆면 정답 | 0/2 | 1/2 |
| 혼합주스 1 L 옆면 정답 | 3/5 | 4/5 |
| 오렌지 1 L 옆면 정답 | 3/8 | 3/8 |
| 등록품 전체 옆면 정답 | 6/15 | 8/15 |
| 등록품 전체 앞면 정답 | 32/45 | 32/45 |
| 미등록 단일 레드자몽에 등록 이름 부여 | 0/14 | 0/14 |
| 미등록 사과 1.75 L에 등록 이름 부여 | 0/9 | 0/9 |

**사과.** 한 장에서 앞면과 이어진 옆면의 작은 바코드 위치를 찾았다. 원본 화소를 겹치지 않는 두 띠에서 읽고, 양쪽 모두 가드 패턴과 체크섬을 통과해 13자리 `7310865074225`가 일치할 때 사진에 사과 1 L 이름을 붙였다. 후보 코드는 바의 위치·기울기 추정에 쓰고 각 띠의 개별 숫자, 패리티와 가드 패턴을 검증한다. 현재 이 보완 경로는 원본 화소 수가 490,000 이하인 입력을 대상으로 한다. 나머지 한 장에서는 1 L와 1.75 L를 가를 증거가 부족했다.

**혼합주스.** 기울어진 포장 면을 펴고 브랜드, ‘ORANGE’, ‘GRAPEFRUIT’가 인쇄된 세 영역을 대조했다. 학습용 사진 두 장이 같은 팩의 같은 위치를 각각 찾아야 새 경로가 이름을 붙인다. 반사가 강한 마지막 한 장은 ‘GRAPEFRUIT’를 확인하기 어려워 보류했다. [두 기준 사진의 출처·체크섬·픽셀 영역](../side-panel-lettering/oblique-enrollment.json)

**사진 판정과 주문.** 새로 식별한 두 장의 실행 기록은 `RR-7660e2282261b043`(사과)과 `RR-d70ea18dee87e263`(혼합주스)로 확인할 수 있다. 두 건 모두 상품 이름을 표시했고 주문 확정은 보류했다.

전체 118장 중 나머지 116장의 상품명·보류 결과는 이전과 같았다. 이 평가에서 주문 규격 확정은 0건이었다.

## 같은 사진으로 재현하기

저장소 루트에서 Pillow, Playwright, Chromium을 사용한다. 아래 명령은 기존 등록품·미등록품·공개 사진 102장을 원본 해시로 검증해 내려받고, 파일 이름을 숨겨 브라우저의 파일 선택창으로 실행한다. 이어서 매장 촬영분 7개의 원본에서 기록된 영역을 다시 잘라 같은 경로로 업로드한다.

```sh
run=$(mktemp -d)
study=docs/experiments/registered-recall
for cohort in archive public legacy-validation; do
    python scripts/evaluate_registered_production.py fetch --cohort "$cohort" --photos "$run/photos"
    python scripts/evaluate_registered_browser.py "$study/$cohort-blind.csv" "$run/photos" --chromium /usr/bin/chromium --out "$run/$cohort.jsonl"
done
python docs/experiments/oblique-packages/landskrona/replay.py --release side-retry --out "$run/field.jsonl"
```

나머지 9장은 [사과 1.75 L 대조 사진 목록](../side-panel-lettering/apple-controls.csv)에 있는 URL에서 가져온다. 같은 셸에서 실행한다.

```sh
python - "$run/photos" <<'PY'
import csv, sys
from pathlib import Path
from urllib.request import urlopen
with open("docs/experiments/side-panel-lettering/apple-controls.csv") as manifest:
    for row in csv.DictReader(manifest):
        with urlopen(row["url"], timeout=30) as response:
            (Path(sys.argv[1]) / row["path"]).write_bytes(response.read())
PY
python scripts/evaluate_registered_browser.py docs/experiments/side-panel-lettering/apple-controls.csv "$run/photos" --chromium /usr/bin/chromium --out "$run/apple-controls.jsonl"
```

혼합주스의 특징 자료를 재생성할 때는 [기존 등록 목록](../store-package-recovery/enrollment.json)과 [추가 각도의 등록 목록](../side-panel-lettering/oblique-enrollment.json)에 있는 원본을 같은 폴더에 둔다. 각 목록의 `source`에서 받아 `file` 이름으로 저장한다. 생성기는 원본의 SHA-256을 검증한다.

```sh
PYTHONPATH=src python scripts/build_printed_regions.py docs/experiments/store-package-recovery/enrollment.json "$run/references" "$run/gallery.json" --additional docs/experiments/side-panel-lettering/oblique-enrollment.json
cmp "$run/gallery.json" web/data/registered-detail-gallery.json
```
