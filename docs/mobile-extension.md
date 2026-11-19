# Bounded mobile extension

This extension executes a computed mobile mission: allocate a picking task, reserve
an exclusive shared zone, navigate to a dock, verify docking, call the existing
fixed-cell `engine.run_job` under the same job identity, leave the zone, and execute
the next queued reposition task with the second robot. A failed route, lease,
deadline, cancellation, docking check or pick verification prevents later work.

The mobile plant is a differential-drive **kinematic simulator**, implemented in
NumPy. It is not MuJoCo wheel/contact dynamics and is not a physical AMR validation.
The picking job still uses the existing MuJoCo RGB-D/perception/SCARA/suction/placement
pipeline. Integration between those simulators is a docking authorization and job
identity handoff: the arm cell starts separately. There is no mobile-manipulator
contact, payload, load transfer, moving arm base or shared rigid-body scene.

## Run and inspect

From the repository root, using the prepared virtual environment:

```bash
MUJOCO_GL=egl .venv/bin/python scripts/run_mobile.py --seed 0 --scenario normal
.venv/bin/python scripts/run_mobile.py --seed 1 --scenario blocked
.venv/bin/python scripts/run_mobile.py --seed 2 --scenario zone_contention
.venv/bin/python -m pytest tests/test_mobile.py -q
```

The normal CLI path always invokes the actual existing picking engine. There is no
CLI option that replaces picking with a success flag. Unit tests explicitly inject
a tiny runner to test orchestration cheaply; those tests are not physics evidence.
Held scenarios exit with code 2. Every invocation writes a new mission directory;
explicit `--mission-id` names must be unique. Runs do not overwrite previous evidence.

Each directory contains:

- `trajectory.jsonl`: append-only samples and state events, including raw noisy
  encoders, all 36 LiDAR rays, landmark observations, EKF estimates/covariances,
  plant truth for evaluation, wheel rim speeds/accelerations, zone ownership and
  docking acceptance measurements.
- `trajectory.svg`: a static plot computed from those logged truth/estimate samples,
  obstacles, zone and dock. It is not an animation or a pre-drawn navigation path.
- `result.json`: terminal outcome, metrics reduced from the raw log, source and raw
  log SHA-256 hashes, mission/job identity and the unmodified nested picking result.
- `pick/`: the engine's own events, result, calibration and persistent job/device
  records, if picking ran. Picking frame recording is disabled for this experiment.

## Measurement and control model

The world frame is a virtual right-handed map: x east, y north in metres; yaw is
counterclockwise in radians. Wheel values are linear rim speeds in m/s and rim
accelerations in m/s²; wheel track is 0.38 m. The navigation timestep is 0.04 s.
Maximum commanded/realized simulated wheel rim speed is 0.55 m/s; acceleration is
limited to 0.8 m/s², including normal and cancellation braking. Small fixed
left/right wheel-to-body gain errors (1.004/0.996) model rolling mismatch.

The controller reads an actual three-state EKF estimate, not plant pose. It starts
from the surveyed robot start plus a sampled error. The EKF predicts from wheel
encoder samples with independent 0.004 m/s Gaussian noise. Every five steps it
updates from known-map landmark range/bearing measurements (standard deviations
0.025 m and 0.012 rad), using the nonlinear measurement Jacobian and a Joseph
covariance update. Those landmark observations are simulated independently of the
estimator. All four landmarks are available globally; occlusion, missed detections,
data association and outliers are not modeled. This mission supplies the map and
landmark identities in advance. A separate offline experiment reconstructs a map
from wheel odometry and LiDAR scans. [LiDAR SLAM evaluation](lidar-slam.md)

A separate 36-ray 360° LiDAR simulation intersects the map rectangles and room
boundary, adds 0.008 m range noise, and inhibits new motion at a 0.295 m minimum
range. It does not currently detect robot bodies or infer a new occupancy map.
The known-map planner uses 8-neighbor A*, a 0.1 m grid, a circular 0.24 m footprint
plus 0.13 m margin, forbids diagonal corner cutting, and verifies smoothed segments
at 0.04 m intervals. A waypoint controller turns before driving through sharp
corners. It is not dynamic obstacle avoidance or trajectory optimization.

Docking requires a stopped base (both wheel speeds below 0.015 m/s), estimated
position/yaw errors within 0.06 m/0.06 rad, and position standard deviation below
0.025 m. An independent truth evaluator applies the same pose tolerances as a
veto. Truth is used to generate sensors and evaluate collisions/docking/clearance;
it is not supplied to navigation, path following or EKF updates as a pose reading.

## Fleet and failure semantics

Two robots receive tasks by nearest available estimated position, with stable
task identities and no double allocation. The picking robot reserves the entire
shared zone before starting its route. The second robot stays parked until the
picking robot has exited, then executes its queued reposition route. This is
intentionally serialized traffic, not a concurrent large-fleet traffic solver.

The scheduler allows one owner and one recorded occupant. Entry uses an estimated
footprint expanded by three-sigma position uncertainty plus 0.10 m. A 90 s lease
is renewed at each mobile step. On expiry the owner is fenced; even an apparently
empty zone cannot be reassigned until positive clearance is provided. The mission
only releases after estimated footprint clearance, with an additional truth veto.
The zone-contention experiment places the second robot stationary inside the zone;
the first waits five simulated seconds and holds without calling the picker.
Lease expiry and refusal to reassign an occupied/uncertain zone are separately
tested. This scheduler is single-process, in-memory, and has no distributed
consensus, durable mobile-task recovery or network-partition handling.

`mission_time_s` advances with mobile simulation steps and then adds the picking
engine's recorded simulated duration at the fixed-cell handoff. Robots remain
stationary during that handoff. The lease is renewed before picking and checked
afterward; its 90 s lifetime exceeds the engine's 60 s simulation limit. Default
mission limits are 240 simulated seconds and 120 wall-clock seconds. Picking is
only started with 60 simulated seconds remaining. The same cancellation probe
and wall deadline are passed into the picking engine. Cancellation or a deadline
ends new work; acceleration-limited stopping can take up to 0.6875 additional
simulated seconds. Every braking sample is logged, and zone ownership is retained.
This bound is a simulator property, not a hardware safety certificate.

There is no charging simulation, battery model, charger control, ROS stack,
hardware driver or real autonomous driving claim. The next task is a second
robot's reposition, not a second physical picking cycle. Extending these boundaries
requires separate sensing, dynamics, safety and integration validation.

## Metrics and reproducibility

`metrics_from_rows` reconstructs distance from consecutive truth samples per robot,
localization RMSE from truth-versus-EKF position samples, maximum absolute logged
wheel speeds and finite-difference accelerations, flagged collision samples,
duration and maximum recorded zone occupancy. Distance omits the first sample's
sub-millimetre displacement from each robot's surveyed starting point. No RMSE is
reported for a run with no motion/sensor samples. Stationary samples contribute to
RMSE; mobile duration includes the fixed-cell simulated duration. Collision checks
are geometric circle-versus-map/circle-versus-circle checks, without collision
response/contact forces. The run manifest hashes runtime source, assets, config,
model, mobile CLI and raw trajectory. The nested physics result also preserves its
own source/model provenance. Inspect those hashes when comparing regenerated runs.

## Recorded verification

The final recorded three-scenario set is under `runs/mobile/`:

| Seed / mission | Outcome | Actual picker calls | Combined simulated duration |
| --- | --- | ---: | ---: |
| 0 / `normal-seed-0-final` | COMPLETED; dock → verified pick → exit → second robot reposition | 1 | 55.85 s |
| 1 / `blocked-seed-1-final` | HELD / NO_PATH | 0 | 0 s |
| 2 / `contention-seed-2-final` | HELD / ZONE_WAIT_TIMEOUT | 0 | 5 s |

The normal run contains 983 mobile samples, 9.611 m of combined robot travel,
7.225 mm sampled position RMSE, maximum wheel speed 0.43157 m/s and maximum wheel
acceleration 0.80000 m/s². Dock errors were 26.44 mm estimated and 17.78 mm truth,
with both heading errors below 0.015 rad. There were zero flagged collision samples
and at most one recorded zone occupant. The physics pick result is
`normal-seed-0-final/pick/normal-0-recovery-97eb51/result.json`, with vision and truth
placement verification, one attempt, no wrong placements, drops or collisions, and
16.53 simulated seconds. The combined mission took 4.612 wall-clock seconds on this
container; this is not a real-robot cycle-time measurement.

`runs/mobile/verification.json` records independent recomputation of all three raw
metric sets, raw-log SHA-256 checks, actual picker invocation counts and gate
ordering/identity checks. The final three runs share source fingerprint
`ad29703e37aa44659e3e7fec096453c8fc6fe063f13800de8d5d8badaaa5c5c3`.
The 13 focused tests additionally cover normal noisy navigation seeds 0/1/7,
EKF correction, footprint clearance, allocator exclusivity, lease expiry fencing,
docking disagreement, cancellation during motion with bounded braking, and deadline
refusal. Early non-`-final` directories are preserved as earlier evidence and are
not the final comparison set.
