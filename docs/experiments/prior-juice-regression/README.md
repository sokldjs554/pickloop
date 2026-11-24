# 기존 공식 시험 사진의 판정 변화

Grocery Store Dataset 공식 test 분할에서 실제 품목이 God Morgon 사과·오렌지·오렌지+레드자몽인 60장을 전수 재평가했다. 사과 19장, 오렌지 22장, 혼합주스 19장이다. 이미 발표한 혼합주스 19장이 이 60장에 포함된다. [사진별 판정](predictions.csv) · [전체 전이표·품목별 집계](summary.json)

| 과거 사진 60장 | 정확한 품목명 | 잘못된 품목명 | 보류 |
|---|---:|---:|---:|
| 기존 기본값, 81종 모델과 Bravo 확인 | 25 | 32 | 3 |
| 이전 선택 옵션 `--juice-gate` | 31 | 4 | 25 |
| 동결한 새 기본값 | 34 | 5 | 21 |

기존 기본값과 비교하면 정확했던 8장이 보류로 바뀌었고, 새로 발생한 잘못된 이름은 0건이었다. 이전 `--juice-gate`와 비교하면 이전에 보류한 5장을 맞혔으나, 정확했던 사과 007번은 보류했고 정확했던 혼합주스 004번은 오렌지로 잘못 판정했다. 세 정책에서 **기존 혼합주스 19장만** 보면 정확/오답/보류는 각각 0/19/0, 7/0/12, 7/1/11이다.

아카이브한 기존 81종+Bravo 판정의 파일 SHA-256, 공식 test 목록, 선택된 원본 사진 60장의 SHA-256을 검사한 뒤 같은 사진 바이트의 EXIF 회전 보정 RGB를 이전 게이트와 새 기본값에 전달했다. 학습 특징을 다시 계산한 횟수는 0회다. 기존 혼합주스 19장의 이전 게이트 판정은 발표된 19개 행과 모두 일치했다. 보류와 오분류를 따로 세며, 새 오분류는 이전에 정확했거나 보류했던 사진에서 잘못 이름을 붙인 경우다. [모델·소스 동결 해시](model-freeze.json) · [재실행 코드](../../../scripts/audit_prior_juice.py)

새 사진 평가의 공통 모델 동결 명세와 별도 대조했다. 이 재평가에 필요한 소스·모델 파일 12개의 SHA-256과 Tesseract 실행 파일·영어 OCR 데이터의 SHA-256이 모두 일치했다. [공통 모델 명세](../new-photos/model-freeze.json)

```bash
git worktree add --detach ../pickloop-photo-freeze 1d39baa22fb65c0a9f58fea23e3b5c6a104a722c
cd ../pickloop-photo-freeze
PYTHONPATH=src python scripts/audit_prior_juice.py \
  --archive /path/to/GroceryStoreDataset-fc80ba90.zip \
  --freeze docs/experiments/prior-juice-regression/model-freeze.json \
  --out /tmp/reproduced-prior-juice --workers 2
```
