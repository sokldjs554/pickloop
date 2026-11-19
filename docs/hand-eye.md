# 이동 손목 카메라의 핸드아이 보정

공개 실물 로봇의 손목 자세와 체커보드 원본 사진 88장을 사용했다. 66장의 로봇 자세와 영상으로 보정한 뒤 나머지 22장에서 로봇 자세만으로 보드가 나타날 픽셀을 예측했다. 사진에서 검출한 1,056개 코너와의 거리는 **RMS 5.156 px**였다. 보드 위치의 일관성 오차는 **11.820 mm**, 자세 오차는 **0.402°**였다. 이 결과는 USDA 연구진이 수집한 장비의 기록을 오프라인에서 재분석한 수치다. PickLoop 자체 피킹 셀은 고정 카메라 외부 보정을 사용하며, 실물 설치와 피킹 정밀도는 별도 검증 대상이다. [공개 데이터](https://doi.org/10.15482/USDA.ADC/1340592) · [실물 기록 결과](../runs/hand-eye/usda-report.json)

## 좌표계와 추정

`A_T_B`는 B 좌표를 A 좌표로 바꾸는 4×4 강체변환이다. 이동 단위는 m, OpenCV 광학 좌표는 x가 오른쪽, y가 아래쪽, z가 카메라 전방이다. 한 번의 촬영에서 얻는 값은 로봇이 보고한 `G_i = base_T_tool`과 체커보드 코너의 PnP로 구한 `C_i = camera_T_target`이다. 카메라가 손목에 고정되고 보드가 정지해 있으면 모든 촬영에서 다음 관계가 성립한다.

```text
G_i X C_i = Y       X = tool_T_camera, Y = base_T_target
A X = X B           A = inverse(G_j) G_i, B = C_j inverse(C_i)
```

OpenCV의 Park–Martin 방법으로 X를 구한다. 학습용 촬영의 `G_i X C_i`를 평균해 Y를 고정한다. 위치에는 산술평균, 회전에는 SciPy의 회전 평균을 쓴다. 검증 촬영에서는 `inverse(G_i X) Y`로 보드 자세를 예측하고 카메라 내부 파라미터와 왜곡 모델을 적용해 픽셀로 투영한다. 검증 사진에서 측정한 코너는 오차를 계산할 때만 사용한다. [추정 코드](../src/pickloop/hand_eye.py) · [실험 코드](../scripts/run_hand_eye.py)

## 공개 실물 기록과 합성 벤치 결과

| 자료 | 보정 / 검증 촬영 수 | 검증 코너 수 | 로봇 자세로 예측한 코너 RMS | 보드 위치 일관성 RMS | 보드 회전 일관성 RMS |
|---|---:|---:|---:|---:|---:|
| USDA Dataset 1, Denso 팔 + Sony 카메라 | 66 / 22 | 1,056 | 5.156 px | 11.820 mm | 0.402° |
| 합성 다축 손목, 알려진 카메라 내부 파라미터 | 32 / 16 | 768 | 0.659 px | 0.499 mm | 0.212° |

**실물 기록.** 장비는 Denso VS-6577GM-B와 Sony XCD IEEEb 카메라다. 640×480 사진마다 28.5 mm 간격의 내부 코너 8×6개를 검출하고 서브픽셀로 정제했다. 모든 사진에서 보드의 긴 축이 위쪽을 향하는 배치를 이용해 대칭 패턴의 점 번호를 통일했다. 원본 `robot_cali.txt`의 `tool_T_base`는 이동 단위를 mm에서 m로 변환한 뒤 역변환했다. 원본 사진 번호를 4로 나눈 나머지가 3인 22장을 보류했다. 카메라 내부 파라미터·렌즈 왜곡·손목 변환·고정 보드의 기준 자세를 모두 나머지 66장으로 추정했다. 전체 88장이 처리됐으며, 기준값을 넘는다는 이유로 제외한 촬영은 없다. 검증 촬영은 같은 장비와 수집 세션에서 나왔다. [추출한 실물 관측값](../runs/hand-eye/usda-observations.json)

**오차의 의미.** 실물 검증 사진 각각에 그 사진의 PnP를 따로 맞추면 코너 RMS는 0.134 px다. 손목 장착 오차와 로봇 자세를 포함하는 전체 체인으로 같은 코너를 예측하면 RMS는 5.156 px이고, 가장 큰 사진별 RMS는 `image83.png`의 9.799 px다. 위치·자세 일관성은 검증 촬영으로 다시 계산한 `G_i X C_i`와 보정 시 고정한 Y의 차이다. 이 실물 데이터에는 손목 장착 위치나 실제 피킹 지점의 독립 계측값이 없어 11.820 mm는 보드 원점의 일관성으로 해석한다. 첫 검증 사진에서 녹색 원은 검출 코너, 주황 십자는 로봇 자세로 예측한 코너다. [검증 사진](../runs/hand-eye/usda-heldout-image3.jpg) · [사진별 수치와 보정 행렬](../runs/hand-eye/usda-report.json)

**합성 벤치.** 48회 촬영에서 손목이 세 축으로 회전하도록 카메라 자세를 생성했다. 카메라 내부 파라미터를 고정하고, 이상 투영한 코너의 각 축에 표준편차 0.25 px의 가우시안 잡음을 더했다. 손목 보고 자세에도 축별 0.10 mm와 0.03°의 독립 잡음을 넣었다. 보정과 검증은 서로 다른 난수 시드 641, 1097을 사용한다. 알려진 장착 변환은 데이터 생성과 최종 오차 계산에만 쓰인다. 추정값과 생성 시 장착값의 차이는 **1.093 mm, 0.111°**였다. [합성 관측값](../runs/hand-eye/synthetic-observations.json) · [결과와 생성값 기준 오차](../runs/hand-eye/synthetic-report.json)

## SCARA에서 확인한 제약

PickLoop의 순기구학으로 XYZ 위치와 yaw를 바꾼 12개 자세를 만들었다. 단일 회전축으로는 그 축 방향 장착 이동량을 일반적인 6자유도 AX=XB로 식별할 수 없다. 모든 상대 회전벡터를 특이값 분해하고 자세 쌍 개수의 제곱근으로 나누면, 두 번째 독립 성분은 **0.000° RMS**였다. 함수는 `INSUFFICIENT_ROTATION`을 반환했다. 이 벤치에서는 두 번째 성분이 2° 이상이고 첫 성분의 5% 이상인 경우에만 보정을 시도한다. 실물 데이터의 첫 두 성분은 11.110°, 6.978°였다. SCARA 셀에서 축 방향 이동량을 얻으려면 별도의 치구 측정이나 독립 제약이 필요하다. [단일 축 결과](../runs/hand-eye/synthetic-report.json) · [회귀 테스트](../tests/test_hand_eye.py)

## 재현

저장소 루트에서 프로젝트 의존성과 테스트 도구를 설치한 Python으로 실행한다. 첫 명령은 저장된 실물 픽셀·손목 자세에서 내부 파라미터, PnP, AX=XB와 검증 수치를 다시 계산한다. 두 번째는 독립 합성 벤치와 SCARA 대조군을 재생성한다.

```bash
PYTHONPATH=src python scripts/run_hand_eye.py --observations runs/hand-eye/usda-observations.json --out-dir /tmp/pickloop-hand-eye-replay
PYTHONPATH=src python scripts/run_hand_eye.py --out-dir /tmp/pickloop-hand-eye-replay
PYTHONPATH=src python -m pytest -q tests/test_hand_eye.py
```

사진에서 코너 검출까지 반복하려면 아래 원본 ZIP을 사용한다. 스크립트는 ZIP의 SHA-256을 검사한다. 실물 관측 JSON과 오버레이 사진은 이 원본에서 생성했다.

```bash
curl -fL https://ndownloader.figshare.com/files/44531195 -o /tmp/pickloop-usda-DS1.zip
PYTHONPATH=src python scripts/run_hand_eye.py --usda-zip /tmp/pickloop-usda-DS1.zip --out-dir /tmp/pickloop-hand-eye-raw
```

원본은 Amy Tabb (2017), *Data from: Solving the Robot-World Hand-Eye(s) Calibration Problem with Iterative Methods*, USDA Agricultural Research Service, Dataset 1이다. Ag Data Commons는 이 자료를 **U.S. Public Domain**으로 표시한다. `DS1.zip`의 SHA-256은 `5ea8ab9b0781ea4431d5ea0316d0df695c1b0244eb7b22d6341a6f241c3a279d`이다. [데이터와 이용 조건](https://agdatacommons.nal.usda.gov/articles/dataset/24667896) · [Tabb와 Ahmad Yousef의 논문](https://doi.org/10.1007/s00138-017-0841-7)
