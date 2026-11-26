# 기존 매장 사진의 옆면 판독 재시험

브라우저 파일 선택창으로 같은 원본을 넣어 v24와 v25의 상품명 판정을 비교했다. 이미 확인한 아카이브를 보완에 사용했으므로 결과는 회귀 비교다. 새 매장에서 촬영한 전체 옆면 평가 사진은 사과 0건, 혼합주스 0건이다. [사진 원본과 정답](../registered-recall/archive-labels.csv) · [v24 브라우저 기록](../store-package-recovery/) · [v25 브라우저 기록](browser.jsonl)

| 조건 | v24 | v25 |
|---|---:|---:|
| 사과 1 L 옆면 정답 | 0/2 | 0/2 |
| 오렌지·레드자몽 1 L 옆면 정답 | 2/5 | 3/5 |
| 오렌지 1 L 옆면 정답 | 3/8 | 3/8 |
| 등록품 전체 옆면 정답 | 5/15 | 6/15 |
| 등록품 전체 앞면 정답 | 29/45 | 32/45 |
| 미등록 단일 레드자몽에 등록 이름 부여 | 0/14 | 0/14 |

기존 판별기는 단일 레드자몽과 비슷한 색과 앞면 배치를 먼저 발견하면, 혼합주스의 이름을 읽기 전에 보류했다. v25는 이 경우 앞면 후보와 같은 위치에서 브랜드와 두 맛 표기를 다시 대조한다. 더 큰 해상도에서 가로로 펼친 투영을 추가해 눌린 글자를 복원한다. 기존 혼합주스 기준 사진과 점수 기준을 사용한다. 이름과 주문 규격은 브라우저에서 각각 기록했다. 공개 사진 8장, 이전 검증 20장, 스웨덴·노르웨이 재시험 7장의 상품 판정은 같았다. 사과 1.75 L 대조 사진 9장은 모두 등록 상품 판정을 보류했다. 전체 118장에서 주문 규격 확정은 0건이었다.

사과 1 L 한 장의 바코드는 해상도가 낮았다. 원본 화소로 1 L 코드와 대조했을 때 약한 한 자리 때문에 독립 영역의 해독 결과가 일치하지 않았다. 다른 한 장은 용량을 가를 바코드나 인쇄 표기 근거를 확보하지 못했다. 혼합주스 두 장은 높은 촬영 각도와 반사로 두 맛 표기를 함께 대조하기 어려웠다.

## 재현

저장소 루트에서 Pillow, Playwright와 Chromium으로 실행한다. [대조군 원본과 해시](apple-controls.csv) · [Willys와 노르웨이 매장 재현](../store-package-recovery/README.md#재현) · [판별기 해시](browser-freeze.json)

```sh
inputs=docs/experiments/registered-recall
run=$(mktemp -d)
for cohort in archive public legacy-validation; do
    python scripts/evaluate_registered_production.py fetch --cohort "$cohort" --photos "$run/photos"
    python scripts/evaluate_registered_browser.py "$inputs/$cohort-blind.csv" "$run/photos" --chromium /usr/bin/chromium --out "$run/$cohort.jsonl"
done
```
