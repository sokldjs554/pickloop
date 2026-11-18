# 실행 근거를 웹에서 확인하기

`web/data/evidence.json`은 화면에서 읽는 5개 근거 카드의 배열입니다. 각 항목은
`title`, `description`, `links: [{label, url}]`을 가지며, URL은 웹 루트 기준의
`data/evidence/...` 경로입니다. 웹에 첨부한 원문은 `web/data/evidence/`에 있습니다.

## 재생성

저장소 루트에서 다음 명령을 실행합니다.

```bash
.venv/bin/python scripts/export_evidence.py
```

이 스크립트는 **기존 실행 기록만 읽습니다**. 엔진·ROS 컨테이너·소켓 서버를 시작하거나
결과를 새로 만들어내지 않습니다. 표준 라이브러리만 사용하며 아래 사항을 검사한 뒤
원문을 바이트 단위로 복사합니다.

- ROS action JSONL의 실제 최종 결과·feedback 횟수와 저장된 integration summary의 일치
- 정상 완료, core 취소 확인, 중복 job·최종 이미지 replay의 동일 run ID
- 별도 DDS sensor probe의 실제 수신 횟수·대표 샘플과 summary의 일치
- 실제 C++ subprocess/TCP 테스트의 통과 기록
- 모바일 원문 SHA, 원문에서 독립 재계산한 메트릭, 도킹→피킹→이탈→다음 작업 순서,
  동일 job ID와 비전·진실 배치 검증, 경로 막힘·경합에서 피킹 미호출

검사 실패 시 근거 카드 생성을 중단합니다. `manifest.json`은 첨부한 각 파일의 원래
저장소 경로, 바이트 수, SHA-256과 검사 범위를 담습니다. 원본 파일의 provenance는
해당 실행 시점의 출처이며 현재 소스가 당시 실행과 항상 같다는 뜻은 아닙니다.
테스트 전체 개수는 카드 설명에 고정하지 않습니다. 각 로그의 명령 범위와 출력이
그 실행에 대한 기준입니다.

## 첨부한 실행의 정확한 범위

**ROS 2:** 기존 Jazzy colcon 빌드 로그와 실제 DDS action 정상·초기 취소·중복 요청·최종
이미지 재접속 로그를 첨부했습니다. 연결된 core 정상/취소 결과와 정상 이벤트도
제공합니다. 센서 probe 원문은 clock·상태·관절·카메라의 수신 횟수 및 대표 메타데이터로,
전체 rosbag이나 모든 JPEG payload를 저장한 자료는 아닙니다. JPEG 한 장은 정상 작업의
실제 관측 원본이며, topic probe의 마지막 이미지와 같다고 주장하지 않습니다.
이 구성은 ROS 작업을 로컬 HTTP 엔진에 연결하는 브리지입니다. `ros2_control`,
TF·CameraInfo, 물리 하드웨어 인터페이스나 실물 제어 인증은 구현 범위 밖입니다.
취소 실험은 파지 전에 수행됐습니다.

**C++ 장치 통신:** 기존 `tests/test_device.py`를 별도로 실행한 verbose 로그를 첨부했습니다.
해당 테스트는 `g++ -std=c++17 -Wall -Wextra -Werror -O2`로 독립 POSIX 소켓 클라이언트를
컴파일하고 별도 subprocess를 통해 실제 TCP 서버와 통신합니다. 중복 명령 억제,
ACK 유실 후 상태 조회·복구, 취소와 상태 응답을 검증합니다. 클라이언트와 해당 테스트
소스도 함께 첨부했습니다. 실물 PLC가 연결된 결과가 아니며, 밸브 명령 수락과
압력·부착의 관측은 구분됩니다.

**모바일:** `normal-seed-0-final`, `blocked-seed-1-final`,
`contention-seed-2-final`의 결과·센서/제어 trace·계산 궤적을 제공합니다. 정상 실행은
도킹 허용 뒤 동일 job으로 실제 MuJoCo 피킹을 수행하고, zone 이탈 후 두 번째 로봇을
재배치했습니다. 나머지 두 실행은 피킹을 호출하지 않고 보류했습니다. 원문에서
encoder·LiDAR·landmark·EKF·wheel·zone 측정값과 단위/좌표계를 확인할 수 있습니다.
lease 만료 시 재할당 거부 및 취소 감속 정지는 별도의 기존 모바일 테스트 실행 로그로
확인합니다. 알려진 지도 EKF이며 **SLAM은 아닙니다**. 모바일은 차동구동 운동학이며
**바퀴·지면 접촉 물리가 아닙니다**. 이동체와 팔 셀은 도킹 권한·job ID로 연결되는
분리된 시뮬레이터이며, 공유 강체 장면이나 실물 하중 전달은 구현하지 않았습니다.

첨부량은 약 2.1 MB로, 대부분은 재계산에 필요한 모바일 raw trace입니다. 대량의 실행
프레임·영상·가상환경·SQLite 파일은 복제하지 않았습니다. 모든 근거는 로컬 시뮬레이션과
소프트웨어 통신 실행이며 **실물 로봇은 미연결**입니다. 충전·실차 자율주행·실물 안전성을
입증하는 자료로 해석하지 않습니다.

## 이번 첨부 로그를 생성한 명령

다음은 이미 구현된 테스트만 실행했으며 물리 피킹 엔진은 시작하지 않았습니다.

```bash
.venv/bin/python -m pytest tests/test_device.py -vv > web/data/evidence/device-tests.txt 2>&1
.venv/bin/python -m pytest tests/test_mobile.py -vv > web/data/evidence/mobile-tests.txt 2>&1
```

모바일 orchestration 테스트는 명시적인 경량 runner를 주입합니다. 실제 피킹 실행의
근거는 테스트 대체 runner가 아니라 함께 첨부한 `mobile-pick-result.json`과
`mobile-pick-events.jsonl`입니다.
