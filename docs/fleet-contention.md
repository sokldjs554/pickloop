# Fleet contention over loopback TCP

On November 26, 2026, two single-host simulations completed 192 of 192 and 384 of 384 healthy tasks through one capacity-one shared zone. The larger run used 48 competing robot processes plus a separate fault-injection robot process. All 48 contenders waited behind the fenced owner. Peak modeled occupancy was one and replay found zero unsafe grants. [24-contender result](../runs/fleet-contention/result.json) · [48-contender result](../runs/fleet-contention/48-robots/result.json)

## How the run works

Each robot runs in an independent spawned OS process and sends commands over TCP to an in-memory coordinator on `127.0.0.1`. The coordinator verifies the observed worker PIDs against the processes it launched and serves the wait queue in arrival order. It reuses the mobile simulator's exclusive-zone lease for acquisition, entry, expiry and release. Each worker uses stable task IDs, performs eight simulated crossings with a seeded 8–18 ms dwell, and resubmits its final completed ID to confirm that it cannot receive a new lease. A startup gate releases all healthy workers in one burst. [Runner](../src/pickloop/fleet_contention.py) · [Existing lease](../src/pickloop/mobile.py#L157)

The fault robot enters the zone before the burst, then closes its actual TCP connection while still occupying the zone in the model. A 500 ms lease expires and fences that owner while all healthy workers queue. The fault process reconnects with the same identity and receives denials for stale entry and release without clearance. A separate synthetic supervisor first supplies a negative clearance signal, then supplies positive clearance. Only after the positive signal does the coordinator grant the next lease. [24-contender event trace](../runs/fleet-contention/events.jsonl.gz) · [48-contender event trace](../runs/fleet-contention/48-robots/events.jsonl.gz)

| Measurement | 24 contenders, seed 41 | 48 contenders, seed 19 |
| --- | ---: | ---: |
| Spawned robot processes, including fault | 25 | 49 |
| Healthy tasks completed / submitted | 192 / 192 | 384 / 384 |
| Completed-ID retries without a second grant | 24 | 48 |
| Peak queue depth / contenders blocked while fenced | 24 / 24 | 48 / 48 |
| Peak modeled occupancy | 1 | 1 |
| Unsafe grants / trace violations | 0 / 0 | 0 / 0 |
| Queue wait p50 / p95 / maximum, ms | 327.726 / 741.552 / 848.494 | 695.794 / 913.476 / 1179.274 |
| Owner disconnect to observed fence, ms | 514.564 | 504.859 |
| Observed fence to positive clearance, ms | 13.609 | 19.261 |
| Positive clearance to last healthy release, s | 2.721 | 5.663 |

Queue wait starts when the coordinator records a task's arrival and ends when it grants the lease. The monotonic clock records event order and elapsed time. The result records UTC start and finish, runtime, run parameters, event SHA-256 and source SHA-256. Replay checks FIFO order, unique grants and completions, completed-ID retries, peak occupancy and the fault sequence without invoking the lease implementation. The negative-control test moves an actual grant ahead of clearance and verifies that replay counts one unsafe grant. [Regression and negative control](../tests/test_fleet_contention.py)

The runs cover a burst at one synthetic traffic bottleneck on one Linux host. Lease arbitration is centralized. Release clearance is an injected signal, and occupancy is reconstructed from accepted protocol events. Multi-host networking, coordinator failover, physical traffic geometry, and operational warehouse throughput remain unverified.

## Reproduce

From the repository root, with the project dependencies installed, run these commands to generate new artifacts and replay the recorded traces.

```bash
PYTHONPATH=src python -m pickloop.fleet_contention --robots 24 --tasks 8 --seed 41 --out /tmp/pickloop-fleet-24
PYTHONPATH=src python -m pickloop.fleet_contention --robots 48 --tasks 8 --seed 19 --out /tmp/pickloop-fleet-48
PYTHONPATH=src python -m pickloop.fleet_contention --check runs/fleet-contention
PYTHONPATH=src python -m pickloop.fleet_contention --check runs/fleet-contention/48-robots
PYTHONPATH=src python -m pytest tests/test_fleet_contention.py tests/test_mobile.py -q
```
