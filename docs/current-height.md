# 현재 물리 모델에서 운반·복귀 높이 규칙 비교

**같은 물리 모델에서 두 규칙 모두 20건 중 16건을 완료했다.** 오류 종류를 보는 현재 규칙은 흡착 실패만 있는 작업에서 2.530초를 줄였지만, 흡착 실패와 경로 차단이 겹친 작업에서는 추가 재시도로 0.605초가 늘었다. 모든 시간 차이는 시뮬레이션 시간이다.

이 기록은 **Codex가 2026-11-24에 실행한 새 비교**다. 지원자가 직접 변경·실행한 [PR #1의 기존 기록](experiments/retry-height/)은 그대로 별도 증거로 유지한다. 이번 결과를 지원자의 직접 실행 기록으로 표시하지 않는다.

- [동결 입력과 실행 환경](experiments/current-height/manifest.json)
- [기계 판독 요약·전체 쌍·원본 해시](experiments/current-height/summary.json)
- [20쌍 CSV](experiments/current-height/pairs.csv) · [자동 생성 요약](experiments/current-height/summary.md)
- [실행·감사 스크립트](../scripts/compare_transport_height.py) · [개인 실행 기록 양식](experiments/current-height/personal-run-template.md)

## 무엇을 같게 두고 무엇을 바꿨나

두 쪽 모두 현재 가이드형 리프트를 포함한 `5643fd6bd35897370cfb31ccc96057f093ab91cf`의 소스·에셋·모델을 `git archive`로 추출해 실행했다. 이전 물리 모델의 결과를 현재 모델 결과와 빼서 비교하지 않았다. 공유 작업 폴더에서 동시에 진행된 주문·상품 인식 변경은 이 스냅샷에 들어가지 않는다.

| 항목 | before: 이전 높이 규칙 | after: 현재 오류별 규칙 |
|---|---|---|
| 첫 시도 | 0.30 m | 0.30 m |
| 두 번째 이상 시도 | 항상 0.40 m | 직전 오류가 `PATH_BLOCKED`일 때 0.40 m, 나머지는 0.30 m |
| 적용 지점 | `transport()`와 `release()`의 운반·복귀 높이 | 동일 |
| 공통 | `recovery`, 최대 3회, sim 60초 / wall 90초, RGB-D 인식, 동일 제어·물리·안전 검사 | 동일 |

스크립트는 프로덕션 파일을 수정하지 않고 `Controller.transport_height` 속성만 실행 중 교체한다. before는 이전 식을 적용하고, after는 스냅샷의 원래 속성을 호출한다. 종료·예외 시 원래 속성을 복원한다. 속성 조회는 [높이 결정 기록](experiments/current-height/raw/mixed-64000/after/height-trace.json)에 남는다. `PLAN`에서 조회한 값 자체는 실행된 이동이 아니므로 실제 단계와 함께 읽어야 한다.

대상은 기존 합성 `SKU-RED-A`, 고정 목적지 bin이다. 새 주문 카탈로그·실물 상품 사진·이동한 bin 인식 기능의 성능 시험은 이 비교의 범위에 포함되지 않는다.

## 실행 전에 고정한 사례

새 seed **64000–64003**, 조건 5개, 높이 규칙 2개로 **20쌍 / 40회**를 실행했다. 기존 `heldout` 조건 생성 범위를 재사용했으며, 새로운 분포에 대한 일반화 검증으로 표현하지 않는다. 전체 조건 JSON과 해시를 첫 엔진 호출 전에 저장했고 결과를 본 뒤 사례를 추가·제외·교체하지 않았다.

1. `normal`: 정상 작업
2. `path_blocked`: 샘플링한 높이의 장애물
3. `suction_once`: 절대 시뮬레이션 시간으로 정해진 일시 흡착 공급 중단
4. `suction_permanent`: 영구 흡착 공급 중단
5. `mixed`: 같은 seed의 `path_blocked` 조건에 같은 seed의 `suction_once` 중단 구간을 합친 사례

mixed의 변경된 전체 조건으로 조건 ID를 다시 계산했다. 두 규칙에 전달한 조건은 완전히 동일하다. 중단 해제는 정책이나 시도 번호가 아닌 절대 시뮬레이션 시각으로 결정된다. 실행 순서는 seed·조건 순서에 따라 before/after를 번갈아 먼저 실행했다.

## 관측 결과

| 조건, 각 4쌍 | before 완료 | after 완료 | before 평균 sim s | after 평균 sim s | after − before |
|---|---:|---:|---:|---:|---:|
| 정상 | 4/4 | 4/4 | 16.390 | 16.390 | 0.000 |
| 경로 차단 | 4/4 | 4/4 | 19.525 | 19.525 | 0.000 |
| 일시 흡착 실패 | 4/4 | 4/4 | 27.445 | 24.915 | −2.530 |
| 영구 흡착 실패 | 0/4 | 0/4 | 21.318 | 21.318 | 0.000 |
| 흡착 실패 + 경로 차단 | 4/4 | 4/4 | 27.445 | 28.050 | +0.605 |

| 전체 지표, 각 20건 | before | after |
|---|---:|---:|
| 완료 / 보류 | 16 / 4 | 16 / 4 |
| 평균 sim s, 실패 포함 | 22.4245 | 22.0395 |
| 총 sim s | 448.490 | 440.790 |
| 재시도 횟수 | 20 | 24 |
| 낙하 / 금지 접촉 / 잘못된 배치 / timeout | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| 평균 wall s | 1.976 | 1.960 |

일시 흡착 실패 후에는 현재 규칙이 불필요한 높은 운반·복귀 경로를 선택하지 않아 각 seed에서 2.530초가 줄었다. mixed에서는 첫 실패가 흡착 실패여서 현재 규칙의 두 번째 시도가 0.30 m 경로를 선택했다. 그 경로의 충돌 사전 검사가 `PATH_BLOCKED`를 반환하고 세 번째 시도에서 0.40 m로 바뀌었다. 이전 규칙은 두 번째 시도부터 0.40 m를 선택했으므로 mixed의 추가 검사·정지·재시도 0.605초가 없었다.

대표 증거:

- 시간 감소: [흡착 실패 before 결과](experiments/current-height/raw/suction_once-64000/before/result.json), [after 결과](experiments/current-height/raw/suction_once-64000/after/result.json), [after 이벤트](experiments/current-height/raw/suction_once-64000/after/events.jsonl).
- 반대 방향 사례: [mixed before 이벤트](experiments/current-height/raw/mixed-64000/before/events.jsonl), [after 이벤트](experiments/current-height/raw/mixed-64000/after/events.jsonl), [after 높이 결정](experiments/current-height/raw/mixed-64000/after/height-trace.json).
- 복구 불가: [영구 흡착 실패 after 결과](experiments/current-height/raw/suction_permanent-64000/after/result.json). 두 규칙 모두 3회 제한 후 보류했다.

0.385초의 전체 평균 감소는 **이 다섯 조건을 같은 비중으로 섞은 작은 표본**의 결과다. 조건 비중이 달라지면 평균 차이도 달라진다. 네 seed는 조건별로 공유되므로 40회를 독립적인 현장 표본으로 취급하지 않는다. 완료율 우위나 보편적인 최적 규칙을 주장할 근거가 아니다.

wall 시간은 다른 테스트가 함께 수행된 공유 CPU 환경의 측정값이다. wall 차이를 규칙의 속도 향상으로 해석하지 않는다. 실제 TCP 응답은 운영체제 스케줄링 영향을 받으므로 재실행에서 불확실한 응답·보류가 생기면 그대로 남긴다. 금지 접촉 0회는 구현된 MuJoCo 접촉 판정 기준의 집계이며 실물 안전 인증이 아니다.

## 원본 감사와 식별자

감사는 20개의 완전한 쌍, 40개의 native 결과와 terminal 이벤트 일치, 조건·초기 물리 상태·소스·모델 동일성, 모든 조회 높이, 원본 파일 해시를 확인한다. 실패 실행 시간도 분모에 포함한다. 기존 출력 폴더 재사용과 불완전한 배치 집계를 거부한다.

- 소스 SHA-256: `42ad174eadc44ec75e50b90f8d14ea5d8ad28170dbd0328afe232e4fc6bb680b`
- 모델 SHA-256: `9a111d8a584cd48a681d80a4a6f0fc7681aedba611f1afbd43fc81d7cf459bec`
- 사례 SHA-256: `1aca3255b91c4ad709a0abc5503d74ac13693bbe93f669e50aeebdbf4155852f`
- 실행 스크립트 SHA-256: `fbb324748b7fd51a7fdc2aee66818e4f1ce68f6ee1c78c30e9e7d000ec609301`

실행용 추출 폴더에는 `.git`이 없어서 native 결과의 `provenance.git_commit`은 `uncommitted`다. 이는 수정된 물리 코드를 사용했다는 뜻이 아니다. 해당 소스의 Git 식별자는 manifest의 `snapshot_commit`이며, 추출 archive·각 소스 파일·모델 해시로 내용을 확인할 수 있다.

## Codespaces에서 직접 다시 실행하기

저장소 루트에서 기존 프로젝트 환경을 활성화한 뒤 실행한다. 기본 revision은 위 스냅샷으로 고정되어 있어 이후 코어 변경과 섞이지 않는다. 최신 동작을 별도로 시험하려면 `--revision`을 명시하고 새 출력 폴더에 기록한다. 서로 다른 물리 모델의 결과는 같은 쌍으로 합치지 않는다.

저장된 Codex 결과만 읽기 전용으로 감사하려면:

```bash
python scripts/compare_transport_height.py audit --out docs/experiments/current-height
```

개인 실행은 이름을 실제 실행자로 바꾸고 **새 폴더와 실행 전에 선택한 seed**를 사용한다. seed 하나는 조건 5개 × 규칙 2개, 총 10회다.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python scripts/compare_transport_height.py run \
  --out work/my-height-65000 --seed 65000 --executor "YOUR_NAME"

python scripts/compare_transport_height.py audit --out work/my-height-65000
cp docs/experiments/current-height/personal-run-template.md \
  work/my-height-65000/personal-record.md
```

명령의 실행자 문자열은 신원 인증이 아니다. 실제 실행 날짜, 가설, 본인이 수정한 범위, 전체 결과와 실패 사례를 `personal-record.md`에 직접 작성하고 원본 파일과 함께 보관한다. 스크립트가 이미 바뀌었거나 환경이 다른 경우 각 manifest의 해시·환경을 함께 비교한다.

이 문서의 40회를 같은 입력으로 다시 계산하려면 새 폴더에서 `--seed 64000 64001 64002 64003 --revision 5643fd6`을 사용한다. 새 실행 결과는 기존 Codex 결과를 덮어쓰지 않는다. 기존 PR #1 개인 실험은 [기여 기록](contributions.md)과 기존 원본을 유지한다.
