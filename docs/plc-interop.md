# S7 software PLC and Modbus TCP interoperability

The existing POSIX C++17 client operated a valve register through an independent Modbus server and a cyclic PLC program. Awlsim 0.78.0 executed S7 statement list in organization block OB1. pyModbusTCP 0.3.1 parsed the TCP requests and encoded the responses. The checked run exercised 13 client invocations over 18 loopback TCP connections. OB1 processed seven mailbox writes and applied two valve commands. [Recorded summary](../runs/plc-interop/summary.json) · [Awlsim](https://pypi.org/project/awlsim/0.78.0/) · [pyModbusTCP](https://pypi.org/project/pyModbusTCP/0.3.1/)

## What the client observed

| Step | Observation on the wire and in C++ |
| --- | --- |
| Energize and observe feedback | Command 2147483681 turned the valve on. Pressure stayed at 0 kPa and attachment was false. A separate fixture update set pressure to −52.3 kPa and attachment to true. The PLC exported the signed pressure word `0xFDF5`. |
| Repeat on a fresh connection | The same ID and payload preserved an execution count of one. Changing the payload under that ID returned Modbus exception 3. |
| Cancel while held | The PLC set the cancellation flag while preserving the valve, pressure, attachment and count. A replay of the fenced ID returned exception 3. |
| Lose a request | The relay consumed release request 2147483682 before forwarding it. The client's FC03 read on its next connection still reported 2147483681. The C++ process exited with an uncertain-command error. A separate status read confirmed the held state. |
| Lose a response | After the bench changed its fixture input to 0 kPa and detached, it explicitly issued release using the **same** ID 2147483682. OB1 applied the command. The relay received and withheld the server's FC16 echo. The client reconnected, read the matching released state and returned success. The count reached two. |
| Submit an old ID | The PLC rejected the stale grip ID. The final fresh C++ status read returned the released valve with an execution count of two. |

The gate checks the C++ stdout and exit status, every request and response byte in order, and every command scan's process image. A dropped response is stored in the wire trace with `delivered=false`. A dropped request has `forwarded=false` and an empty response. These fields document the fixture's knowledge. The client inferred each outcome using its own readback. [Client results](../runs/plc-interop/steps.jsonl) · [Wire frames](../runs/plc-interop/wire.jsonl) · [PLC scans](../runs/plc-interop/scans.jsonl)

## PLC program and interface

The bridge gives OB1 one command per write strobe. On each nominal 10 ms cycle, it copies the command and independent simulated sensor values into the CPU's input process image, executes OB1 and captures the output image. The Modbus adapter delays its FC16 echo until the scan finishes. OB1 owns ID ordering, duplicate suppression, cancellation and the valve output. pyModbusTCP converts the block's result into a normal FC16 echo or an exception. [S7 program](../plc/pickloop.awl) · [Bench adapter](../plc/bench.py) · [C++ client](../cpp/modbus_client.cpp)

| PLC image | Contents |
| --- | --- |
| ID0, IW4, IW6 | 32-bit command ID, operation, valve request from holding-register addresses 100–103 |
| IW8, IW10, IW12 | Signed pressure in tenths of kPa, attachment flag, one-cycle mailbox strobe |
| QW0–QW22, every two bytes | Twelve FC03 holding registers at addresses 0–11, in the project's version-1 status layout |
| QW24 | Application result for the bridge, zero on success or three on a rejected command |

The two IDs cross the signed 32-bit boundary relative to the initial ID of zero. The frames carry `0x80000021` and `0x80000022`. The PLC compares them as unsigned and C++ decodes the high and low words. The scan trace records monotonic start offsets, scan execution duration, fixture inputs, command words and thirteen output words. The summary reports observed scan intervals and command-line process duration, including process startup. Timing varies with the host scheduler. [Register contract](device-protocol.md) · [Timing record](../runs/plc-interop/summary.json)

This is a single-station software simulation with volatile CPU state and the latest reserved ID in memory. The application rejects earlier IDs. PickLoop's SQLite-backed controller has a separate journal and broader replay behavior. Pressure and attachment here are scripted inputs. Physical PLC commissioning, electrical I/O, actual pressure acquisition, power-loss retention, machine interlocks and real-time deadlines require separate tests. [Hardware acceptance procedure](hardware-acceptance.md)

## Repeat the run

The recorded run used Linux x86-64, Python 3.12 and g++. From the repository root, create a dedicated virtual environment. The two optional packages are pinned by version and archive hash. A new output directory keeps each run's evidence intact.

```bash
python3.12 -m venv /tmp/pickloop-plc-venv
. /tmp/pickloop-plc-venv/bin/activate
AWLSIM_CYTHON_BUILD=0 python -m pip install --require-hashes -r plc/requirements.txt
python plc/run_interop.py --out /tmp/pickloop-plc-run
python plc/run_interop.py --check /tmp/pickloop-plc-run
```

For the checked-in recording, the Python standard library is sufficient. The gate validates the summary against the three JSONL traces and exits nonzero on a mismatch.

```bash
python plc/run_interop.py --check runs/plc-interop
```

같은 배치를 새 프로세스에서 다시 실행하고 결과를 별도로 보관했다. 클라이언트 확인 13단계, TCP 연결 18회, 명령 스캔 7회와 밸브 상태 변경 2회를 확인했다. 실제 PLC 단자에 연결한 배선·전기 출력 결과는 0건이다. [재시험 원문](../runs/plc-interop-retest/) · [물리 장비 검증에 필요한 항목](hardware-acceptance.md#실제-토크와-plc-출력에-필요한-장비)
