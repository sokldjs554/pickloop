# 실물 연결 인수 계획과 선택 I/O 보드

이 문서는 **제안 명세와 미수행 시험 계획**이다. 실제 전기 회로·PCB CAD·Gerber·조립품·측정 결과가 아니다. 구현·실행된 범위는 [Modbus TCP emulator/Python·C++ client](device-protocol.md)이며, 흡착 압력과 물체 상태는 현재 MuJoCo 물리 모델에서 온다. [사용자의 PADS·ATmega128 경험](pcb-experience.md)은 별도 보드 경험이며 이 로봇에 연결된 상태가 아니다.

## 후보 판단과 설계 보류 범위

소형 I/O 보드는 밸브 구동·압력 취득·유지 상태·통신 감시를 한 경계로 묶는 후보로 유용하다. 다만 이번 프로젝트의 실행 핵심은 완성된 프로토콜 어댑터와 피킹 검증이다. 밸브 정격/정상 상태/코일 전류, 센서 전원/출력/압력 범위, MCU/통신 모듈, 현장 전원과 안전회로가 확인되지 않았으므로 **부품 확정·회로도·배치·BOM 확정·발주는 보류**한다. 별도 [KiCad 압력 입력 실습 회로와 PCB](../hardware/kicad-pressure-bench/)에서 150 Ω 변환 예를 검증했다. 벤치 실습의 범위는 저전압·전류 제한 조건의 설계 파일과 CAD 규칙 검사다.

아래는 검토를 위한 **24 VDC 산업 I/O 가정의 연결 후보**다. 실제 부품 정격이 다르면 전원/드라이버/보호를 다시 계산해야 하며 핀 배치도 확정 생산 사양이 아니다. ATmega128 재사용을 전제로 하지 않는다.

| 커넥터/핀 | 제안 신호·방향 | 전기/기능 조건 |
|---|---|---|
| J1-1 / J1-2 | +24V_FIELD / FIELD_0V, 입력 | 외부 인증 SELV 전원 후보. 역극성·과전류·서지 보호, 밸브/논리 전원 분리 검토 |
| J1-3 | CHASSIS/SHIELD | 케이블 차폐·접지 방식은 설치 접지 정책에 맞춰 결정. 신호 0V와 무조건 직결하지 않음 |
| J2-1 / J2-2 | VALVE_SUPPLY / VALVE_RETURN, 출력 | 정격·구동 방식 확인 후 MOSFET/절연 드라이버·flyback/TVS·퓨즈 선정. MCU 핀으로 코일 직접 구동 금지 |
| J2-3 / J2-4 | VALVE_FEEDBACK / FIELD_0V, 입력 | 선택적 전류/스풀 피드백. valve intent와 실제 밸브 상태를 구분; 미장착 시 미확인 상태 |
| J3-1 / J3-2 | SENSOR_SUPPLY / SENSOR_0V, 출력 | 센서 정격 확정 후 보호 전원. 센서/코일 리턴 전류 경로 분리 |
| J3-3 / J3-4 | PRESSURE_LOOP_IN / PRESSURE_LOOP_RETURN, 입력 | 4–20 mA 후보. 예: 150Ω 정밀 shunt이면 0.6–3.0 V; ADC 입력 보호·필터·공통모드/절연 검토. 0–10 V 센서는 이 핀 회로에 직접 연결하지 않음 |
| J4-1 / J4-2 | LOAD_PRESENT / INPUT_RETURN, 입력 | 광전/흡착스위치 등 독립 물체 존재 센서 후보. 전압·PNP/NPN 확정 전 연결 금지. 압력만으로 운반 완료 판정하지 않음 |
| J5 | Ethernet, 양방향 | 보호된 Ethernet module/PHY를 통한 Modbus TCP. MCU raw GPIO Ethernet 직결 아님. protocol v1 register map 준수 |
| J6-1 / J6-2 | SAFETY_OK / SAFETY_RETURN, 입력 | 독립 안전회로 상태 모니터 전용. 이 보드나 네트워크 명령으로 emergency stop을 우회·복귀시키지 않음 |

후보 BOM 기능군: 전원 보호/DC-DC, MCU+비휘발 저장장치, Ethernet 모듈, 보호 밸브 드라이버, 정밀 shunt/ADC/필터, 절연 또는 적합한 디지털 입력, locking terminal, watchdog/reset supervisor. 개별 제조사 부품·가격·전류 용량은 미정이며 구매 BOM으로 사용할 수 없다. 레이아웃은 코일 전류/귀환과 ADC 기준 분리, 보호소자 커넥터 인접 배치, 절연 선택 시 거리 확보, test point 확보를 요구한다. 사용자 PADS 경험은 이 검토에 연결 가능한 배경이지 신규 배치 완료 근거가 아니다.

## 정상·통신 단절·취소의 상태 계약

`VALVE_ON`은 물체 부착 증거가 아니다. host는 밸브 intent, 신선한 압력, 물체 존재, command acknowledgement를 각각 확인한다. 현재 [프로토콜 v1](device-protocol.md)은 pressure를 signed 0.1 kPa로 전송한다. 실물에는 **센서 timestamp/sequence·watchdog·power-good·실밸브 feedback 확장**이 필요하며 버전 협의 없이 v1 주소를 바꾸지 않는다. 결측 피드백을 마지막 정상값으로 무한 유지하지 않는다.

| 조건 | 제안 안전 동작 |
|---|---|
| 정상 seal | 정의된 진공 임계·유지 시간과 신선한 센서값을 만족해야 lift 허가 |
| 취소/ACK 손실/통신 timeout | 새 동작·새 command ID 재발행을 중단, 로봇 감속/정지, 기존 파지의 진공/물체 지지 유지. 물체 상태 대조 후 보류 |
| 부착 물체가 없는 통신 단절 | 새 seal/이동을 금지하고 현장 위험평가에 정한 대기 상태. 통신 복귀만으로 자동 재시작하지 않음 |
| 전원 상실/호스트 죽음 | 소프트웨어 last intent 보존만으로 파지 유지 불가. check valve/진공 reservoir/기계 지지·낙하 방지와 밸브 정상 상태를 실물에 맞게 설계·검증 |
| 압력 저하/센서 stale/선 단락 | 이송 중지·낙하 위험 격리, 가능하면 지정 지지 위치로만 제한 복구; 상태 미확인에서는 자동 release 금지 |
| 독립 emergency stop | 위험 모션의 하드웨어 차단/안전 정지는 독립 안전회로가 담당. vacuum 유지에 필요한 공급/체크밸브는 낙하 위험평가와 일치해야 함. 모든 출력을 일괄 off하는 규칙은 사용하지 않음 |
| 재부팅/미완료 intent | 실제 밸브·압력·물체·최대 command ID 대조 전 새 동작 금지. 기존 SQLite journal 삭제를 복구 절차로 삼지 않음 |

현재 emulator의 cancel은 command tombstone이며 motion stop 자체가 아니다. coordinator가 별도로 제동한다. SQLite pending→applied 사이 crash는 불확실로 보류하며 정확히 한 번의 물리 구동을 증명하지 않는다. 실물 안전 제어와 safety certification은 이번 구현 범위에 없다.

## 실물 시험 순서와 제안 인수 기준

**아래 전 항목은 미수행이다.** 임계값은 인수 기준 후보이며 부품 데이터시트와 위험평가 후 확정한다. 전류 제한 전원·퓨즈·더미 부하·기계 지지물·차폐된 작업구역으로 시작하고, 오실로스코프/전류·압력 기준계/온도계 등 실제 사용 장비와 교정 정보를 기록한다. 이 목록은 사용자가 이미 해당 장비를 사용했다는 뜻이 아니다.

| 단계 | 제안 시험·계측 | 제안 합격 조건·기록 |
|---|---|---|
| H01 무전원 검사 | CAD ERC/DRC·핀 continuity·극성·단락 검사 | 확정 netlist 대비 불일치 0, 전원 단락 0, 검사 종류·설정·보고서 보존 |
| H02 전원/출력 | 전류 제한 상태의 논리 전압·reset·dummy coil 전류·전원 cycle | 데이터시트 범위 내 전압, 의도치 않은 valve pulse 0. 최대 전류/온도는 선정 부품 derating 기준 이하 |
| H03 센서 보정 | 압력 기준계로 최소 5점·상하 sweep, 단선/단락 | 후보 허용 오차 ±2 kPa 이내, sample ≥20 Hz, 관측 age >200 ms이면 stale. 단선/단락을 정상 진공으로 판정 0 |
| H04 seal/부하 | 지지대 위 실제 흡착컵·표면·최대 payload 반복 | 임시 lift gate −35 kPa 이하 200 ms 유지+물체 센서 신선. 재질별 누설·접근 오차·보유 시간 원본 기록 후 실물 임계 재조정 |
| H05 통신 fault | TCP 지연·ACK drop·케이블 분리·중복/충돌 ID | 같은 ID 재수신 100회에서 밸브 재구동 증가 0, payload 충돌은 거부, uncertainty는 hold. host 제한 시간 이내 판정, 신규 동작 0 |
| H06 reboot crash window | intent 기록 전/후·출력 전/후 장치/host 재부팅 | 미확인 pending은 자동 재실행 0, 최대 ID 역행 0, 물체 파지 유지/지지 확인. 대조·수동 복귀 절차 기록 |
| H07 취소/비상 정지 | 물체 없는 상태→지지대 위 부착 상태→제한 운동 순서 | 취소 후 의도치 않은 release 0. 제동 시간·거리와 emergency stop 응답은 로봇 위험평가/안전 제조사 기준 이하로 실측 |
| H08 운반/배치 | 손상 없는 시험품, 동일 초기 조건, 영상·압력·로봇 로그 | lift·운반·박스 안 release·안정 확인 모두 필요. 목표 도착만으로 성공 처리 0; 오품/낙하/충돌/보류 별도 기록 |
| H09 모델 배포 | 실제 RGB-D의 별도 train/dev/final 분할·고정 모델 | 실물 영상 최종 평가, unknown·유사품·가림·반사 포함. 추론 지연/오류와 작업 성공 동시 측정. simulation 결과로 대체 금지 |
| H10 모바일·충전 | 실제 지도/측위/도킹 기준물·전기 연결·BMS | SLAM 지도 품질·정지 오차 실측, 접촉/전류/온도/BMS 상태 증거 필요. battery 숫자 변경을 충전 합격으로 처리하지 않음 |

납품 기록에는 HW revision, schematic/PCB hash, BOM·firmware version, host commit/model hash, 장비/교정/환경·payload, test IDs·시각·원본 파형/압력/영상·실패/재시험을 연결한다. 미제작·미측정 상태에서는 H01–H10을 PASS로 채우지 않는다.

## 실제 토크와 PLC 출력에 필요한 장비

| 확인할 값 | 필요한 장비와 접근 권한 | 남길 기록 |
|---|---|---|
| 실물 로봇 관절 토크 | 실제 로봇과 컨트롤러. 제조사 문서에서 단위·갱신률·측정 방식을 확인한 뒤 읽기 전용 토크 또는 관절 effort 피드백을 취득한다. 피드백이 모터 전류 기반 추정이면 추정값으로 기록한다. 독립 실측에는 캘리브레이션된 토크 센서와 측정 장치가 필요하다. | 관절 번호, 시간, 기준 자세, 하중, 명령값, 보고값, 측정 방식과 단위 |
| 실물 PLC 배선·출력 | 정확한 PLC CPU와 I/O 모듈, 해당 제조사 엔지니어링 도구, 모듈 정격에 맞는 시험 전원·테스트 부하·전압 또는 전류 측정기. 기종에 따라 엔지니어링 소프트웨어 라이선스나 제어기 접근 권한이 필요하다. | 명령과 레지스터, 출력 단자에서 얻은 전압·전류, 차단·응답 유실 시 출력, 측정기와 부하 정격 |

두 시험 모두 생성형 AI API 키를 요구하지 않는다. [소프트웨어 PLC의 13단계 재시험](../runs/plc-interop-retest/)에서는 TCP 교환과 S7 논리의 출력 이미지를 검증했다. 실제 단자 출력·배선 시험의 증거는 위의 전기 측정으로 남겨야 한다.

## Isaac Sim 실행 환경

NVIDIA 공식 요구사항에서 Linux 컨테이너와 RTX 지원 GPU를 확인했다. 현재 실행 환경에서 NVIDIA 장치와 런타임을 찾지 못해 Isaac Sim 실행 증거는 0건이다. Mac에서 GPU 워크스테이션에 접속하는 방식은 NVIDIA가 안내하는 별도 스트리밍 구성이다. 이 저장소의 MuJoCo 결과를 Isaac Sim 실행으로 집계하지 않는다. [시스템 요구사항](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html) · [Linux 컨테이너 설치](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html) · [스트리밍 설명](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_faq.html)

사용자가 노트북에서 조회한 장치는 Tesla T4 두 장(각 15,360 MiB), 드라이버 580.178.04였다. [Colab·Kaggle 점검 노트북](experiments/isaac-sim/notebook.ipynb)은 GPU 정보를 저장하고, 선택 실행 시 별도 Python 3.11 환경에 Isaac Sim 5.1.0을 설치해 상자의 시작·종료 높이와 정지 속도를 확인한다. 현재 확보한 것은 장치 조회 결과다. 해당 세션의 물리 실행 결과는 아직 0건이다.
