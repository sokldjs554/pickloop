# 주문 SKU를 카메라로 찾아 상자에 놓기

같은 상에 있는 오렌지주스, 오렌지·레드자몽 혼합주스, 미등록 민트차 중 주문과 일치하는 상자를 고른다. MuJoCo가 그린 RGB-D로 상품 후보와 목적지 상자를 찾고, 좁은 화각의 카메라로 후보의 인쇄면을 다시 읽는다. 판독이 끝난 뒤에만 SCARA가 접근해 흡착·이송·해제한다. 일곱 시나리오를 실행해 세 건을 배치했고 네 건을 접근 전에 보류했다. [전체 실행 색인](../runs/order-pick/index.json)

## 어떤 일이 일어났나

| 주문과 장면 | 실제 작업 결과 | 근거 |
|---|---|---|
| 기본 배치, 오렌지 | 측정 x 354.7 mm의 상자를 집어 오렌지 1개 배치 | [결과](../runs/order-pick/orange/result.json) · [운반 영상](../runs/order-pick/orange/motion.mp4) |
| 같은 주문, 두 주스 위치 교환 | 목표가 x 495.9 mm로 이동. 오렌지 1개 배치 | [결과](../runs/order-pick/orange-swapped/result.json) · [영상](../runs/order-pick/orange-swapped/motion.mp4) |
| 교환된 배치, 혼합주스 | x 354.7 mm의 혼합주스 1개 배치 | [결과](../runs/order-pick/mixed/result.json) · [영상](../runs/order-pick/mixed/motion.mp4) |
| 기본 배치, 혼합주스 | 대상은 실제로 존재했지만 81종 모델 1위가 단일 레드자몽주스. 주문을 확정하지 못해 보류 | [후보별 원시 점수와 판정](../runs/order-pick/mixed-standard/result.json) |
| 오렌지의 두 맛 표기를 테이프로 가림 | 모델은 오렌지를 수락. 두 번의 확대 촬영에서 브랜드만 읽혀 보류 | [실제 판독 영상](../runs/order-pick/unreadable/source-2-face.png) · [결과](../runs/order-pick/unreadable/result.json) |
| 동일한 오렌지 두 상자 | 확인된 후보가 2개여서 보류 | [결과](../runs/order-pick/ambiguous/result.json) |
| 혼합주스와 미등록 민트차 두 상자, 오렌지 주문 | 확인된 주문 후보 0개로 보류 | [카메라 장면](../runs/order-pick/absent/overview.png) · [결과](../runs/order-pick/absent/result.json) |

배치 세 건 모두 목적지에서 SKU를 다시 읽었고, 별도 물리 판정에서 주문 상품만 상자 내부에 정지해 있었다. 세 건의 금지 충돌·낙하·잘못된 배치는 모두 0회였다. 네 보류 기록의 사건 순서는 OBSERVE → HELD이며 흡착 명령은 0회다. 혼합주스를 놓친 기본 배치의 1·2위 결합 점수 차이는 0.0049였다. 같은 인쇄물도 위치·빛·샘플링에 따라 잘못 분류되는 사례를 포함한다.

## 판독과 로봇 제어

1. **후보 위치.** 고정 RGB-D 카메라의 깊이와 6점 PnP 보정으로 탁자 위에서 분리된 상면 후보와 기준 좌표를 얻는다. 육안 확인용 확대 카메라는 이 측정점으로 향한다. 4.2° 화각에서 얻은 RGB와 깊이로 상면의 네 모서리, yaw와 정면으로 편 이미지를 계산하고, 4.6° 화각에서 다시 촬영한다. 두 읽기는 같은 인쇄물을 다른 광학 샘플링으로 본 것이다. [상면 검출·좌표](../src/pickloop/perception.py) · [카메라 모델](../src/pickloop/simulation.py)
2. **품목 판정.** 첫 확대 이미지에서 동결한 DINOv2 특징과 기존 81종 헤드가 1위, 지지점수, 마진과 수락·거부를 낸다. 기존 상용 팩 전면용 판독 결과도 `carton_gate`에 보존한다. 이번 모형의 출하 라벨은 전면 팩 갤러리에서 대응 패널을 찾지 못했다. 별도의 `shipping_label` 판독기는 두 확대 이미지의 공통 하단 영역을 Tesseract로 읽는다. 브랜드와 맛 단어가 두 번 확인되고 수락된 81종 품목과 일치해야 한다. 기존 헤드가 거부한 후보, 서로 충돌하거나 일부만 읽힌 표기는 보류한다. 주문명은 후보별 판독이 끝난 뒤 유일한 일치 항목을 고를 때 사용한다. [판독·선택 구현](../src/pickloop/order_pick.py) · [실제 혼합주스 확대 영상](../runs/order-pick/mixed/source-2-face.png)
3. **실행.** 출발점을 새 깊이 관측으로 다시 확인한다. 관절 궤적을 실행하고, 컵에 측정된 진공이 −35 kPa 이하일 때 들어 올린다. 목적지 역시 RGB-D로 측정한 개구부 중심·바닥을 사용한다. 영상은 물리 시간이 진행되는 동안 장면 카메라를 6 fps로 샘플링한 것이다. 각 프레임과 사건에는 시뮬레이션 시각이 있다. [목적지 박스 추정](bin-perception.md) · [정상 실행 사건과 압력](../runs/order-pick/orange/result.json)
4. **배치 확인.** 팔이 물러나면 상자 안 상품을 확대해 재판독한다. 0.2초 뒤 위치 변화 4 mm 이하, 상품의 상면 높이, 밸브·진공 해제를 검사한다. 종료 후 별도 평가기가 물리 물체에 연결한 재질·SKU 명세로 배송된 상품을 확인한다. 실제 여덟 모서리의 XY 투영이 회전된 상자 내부에 있고, 최저점은 바닥에서 4 mm 이내이며, 속도는 0.02 m/s 미만이고 흡착은 풀려 있어야 한다. 이 정답 정보는 제어 목표 계산 이후에 조회한다.

## 자료와 적용 범위

실험 상품은 64×52×50 mm 상자다. 두 주스의 표면에는 Grocery Store Dataset의 **모델 학습용 fit 사진**을 일부 자르고 사람이 읽을 수 있는 브랜드·맛 설명을 덧붙여 만든 모의 출하 라벨을 사용했다. 민트차는 직접 생성한 미등록 도안이다. 두 주스의 라벨에서 사진과 글자는 모두 MuJoCo 재질로 렌더링되어 카메라 원본에 나타난다. 컨트롤러는 재질 파일을 모델 입력으로 읽지 않는다. 출하 라벨은 개발 과정에서 시험한 자재다. 일곱 작업의 결과는 이 두 라벨·한 시드·정면 배치에서의 통합 동작을 보여준다. [파일·원본 사진·SHA-256](../assets/order-pick/manifest.json) · [원본 저장소의 라이선스와 저작권 표시](../assets/order-pick/LICENSE-GroceryStoreDataset.txt)

모형의 확대 카메라는 명령한 각도·화각으로 즉시 향하며 두 촬영 사이에 장면 물리 시간은 진행하지 않는다. 실물 PTZ의 이동 시간·진동·재보정, 상자가 임의 각도로 뒤집히는 경우, 밀집 적재, 가려진 뒷면, 실물 진공·PLC는 이 시나리오에서 검증하지 않았다. 이 실행은 `Cell`의 진공 물리 모델을 직접 구동하며 기존 Modbus 통신은 별도의 실험에서 검증한다. 알려진 상품 사진의 재사용과 정해진 인쇄 위치 때문에 이 결과로 새 포장이나 실물 매장의 인식 정확도를 추정할 수 없다.

## 직접 실행하고 기록 확인하기

프로젝트 가상환경에 카탈로그 추가 의존성, Tesseract 영어 데이터, ffmpeg를 설치한다. 고정 DINOv2 체크섬을 검증하며, `--weights`를 생략하면 기존 카탈로그 도구와 같은 캐시/다운로드 경로를 쓴다. 새 경로를 `--out`에 지정한다. [기존 카탈로그 설치·가중치 안내](grocery-catalogue.md)

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pickloop.order_pick \
  --case swapped --order God-Morgon-Orange-Red-Grapefruit-Juice \
  --out /tmp/one-grocery-order

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_order_pick.py \
  --out /tmp/pickloop-order-experiment

python -m pytest -q tests/test_order_pick.py
```

각 실행의 `result.json`에는 원본·확대 카메라 관측 ID와 시뮬레이션/수신 시각, 보정 행렬, 상면 모서리·중심·yaw, 두 확대 이미지, 모델 점수, 원문 OCR, 밸브·압력 사건, 최종 물리 판정이 있다. PNG는 실제 판독에 사용한 픽셀을 무손실로 보존한다. 깊이 NPZ의 `depth_f32_u32_dx`를 `cumsum(axis=1, dtype=np.uint32).view(np.float32)`로 복원하면 원래의 미터 단위 float32 깊이가 나온다. [전체 기록 생성기](../scripts/run_order_pick.py) · [저장된 카메라로 상면 추출을 반복하는 테스트](../tests/test_order_pick.py)
