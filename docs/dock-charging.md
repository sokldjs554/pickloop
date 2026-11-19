# Two AMRs sharing an automatic charging dock

Two vehicles in the known-map kinematic simulator request one charging dock when their initial state of charge falls below 20%. In the recorded healthy-dock run, both navigated from their parking positions, charged to 20.5%, and drove back to park. AMR-1 received **0.336370 Wh** and AMR-2 received **0.288264 Wh** at their simulated battery terminals. The second vehicle acquired the zone at **77.80 simulated seconds**, after the first had returned to park and passed its clearance check. [Run result](../runs/dock-charging/normal-seed-0/result.json) · [Raw telemetry, gzip JSONL](../runs/dock-charging/normal-seed-0/telemetry.jsonl.gz)

## Rerun and inspect

Use the repository's Python environment. The runner creates a fresh directory for each invocation. An explicit mission ID must be unique. A completed run returns exit code 0. A held mission writes its evidence and returns 2.

```bash
PYTHONPATH=src .venv/bin/python scripts/run_dock_charging.py --seed 0
PYTHONPATH=src .venv/bin/python scripts/run_dock_charging.py --seed 0 --scenario current_interrupt
PYTHONPATH=src .venv/bin/python scripts/run_dock_charging.py --initial-soc .20 .80
PYTHONPATH=src .venv/bin/python -m pytest tests/test_dock_charging.py tests/test_mobile.py -q
```

Each run stores its outcome, fleet metrics, per-vehicle energy, source hashes, runtime versions and compressed telemetry hash in `result.json`. Decompress `telemetry.jsonl.gz` to inspect each navigation step, electrical reading, state transition, contention request and zone handoff. Both vehicles use the original mobile simulator's A* planner, EKF, collision evaluator and lease scheduler. This charging mission has a dedicated runner. Historical mobile picking runs are documented separately. [Mobile model](mobile-extension.md) · [Charging code](../src/pickloop/dock_charging.py) · [Tests](../tests/test_dock_charging.py)

## Dock admission and metering

1. The controller queues eligible vehicles by lowest initial charge, using the robot ID to break ties. It reserves the shared zone before starting the active route. The waiting vehicle attempts to acquire the lease at reservation, at docking and after current confirmation. Its measured pose and wheel speeds accompany each denial.
2. Geometric docking requires estimated and evaluator position and heading errors within 0.06 m and 0.06 rad, position standard deviation at most 0.025 m and wheel speeds below 0.015 m/s. Electrical operation additionally requires both actual wheel speeds to be zero within 1e-9 m/s, an active lease and sole occupancy at every sample. The mobile sensors and estimator continue updating while parked.
3. A pad-switch model samples longitudinal, lateral and yaw misalignment from plant pose in the dock frame. Its capture limits are 45 mm, 35 mm and 0.05 rad. After five consecutive closed-switch readings, the controller requires five pilot readings in the 24–27 V interval. It then closes the relay and requires five current readings between 0.25 and 2.00 A. Each phase has a one-second timeout. A current interruption after confirmation holds the vehicle on its first failed sample.
4. The ideal circuit uses a 25.2 V source, a battery open-circuit voltage of `23 + 3 × SOC` V, 0.9 Ω total resistance, 0.12 Ω battery resistance and a 2 A current limit. Every 0.04 s, the controller integrates `terminal_v × current_a × dt_s / 3600` in Wh, including energy delivered during current confirmation. Terminal energy divided by the nominal 48 Wh capacity increases the modeled charge fraction. Confirmed top-up has a 40 s time limit.
5. The controller opens the relay and reads zero current before returning to park. It releases the lease after the estimated footprint, expanded for uncertainty, clears the zone and the evaluator confirms clearance. On an electrical fault the vehicle remains stopped, the relay opens, and the current owner retains the occupied zone.

## Recorded outcomes

All six runs use seed 0. Default initial charges were 19.8% and 19.9%. The ready-fleet control used 20% and 80%.

| Experiment | Observed outcome | Terminal energy, AMR-1 / AMR-2 | Simulated finish |
| --- | --- | --- | ---: |
| [Healthy dock](../runs/dock-charging/normal-seed-0/result.json) | Both vehicles charged and returned to park | 0.336370 / 0.288264 Wh | 150.68 s |
| [Switch stays open](../runs/dock-charging/no_contact-seed-0/result.json) | Dock pose accepted, contact timed out | 0 / 0 Wh | 22.76 s |
| [19 V pilot](../runs/dock-charging/low_voltage-seed-0/result.json) | Contact confirmed, pilot timed out | 0 / 0 Wh | 22.96 s |
| [Open current path](../runs/dock-charging/no_current-seed-0/result.json) | Pilot confirmed, current timed out | 0 / 0 Wh | 23.16 s |
| [Current interrupted](../runs/dock-charging/current_interrupt-seed-0/result.json) | Current confirmed, transfer stopped after 2 s of relay closure | 0.023592 / 0 Wh | 24.20 s |
| [Both above or at trigger](../runs/dock-charging/ready-seed-0/result.json) | Both remained parked, zero charging requests | 0 / 0 Wh | 0.00 s |

The healthy run contains 3,767 mobile samples and 1,352 electrical samples. The vehicles traveled 23.934 m in total, logged zero geometric collision samples, and recorded at most one zone occupant. For all four electrical faults AMR-1 retained the dock and AMR-2 stayed parked. The tests recompute the energy integral from raw readings, match powered intervals to wheel and zone samples, and exercise rolling wheels, an expired lease and a rejected pose estimate.

## Scope of evidence

This is a single-process, serialized two-vehicle simulation. The trigger uses supplied initial battery levels. The battery model covers charging only, with ideal instrumentation and unit energy-storage efficiency. It omits traction consumption, aging, thermal behavior and cell-level battery management. Pad capture and relay closure use deterministic geometry and circuit equations. Real connector engagement, currents, thermal limits, stopping distances, charger/BMS protocols and fleet transport have no physical measurements in this experiment.
