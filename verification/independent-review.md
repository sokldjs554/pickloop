# PickLoop core engineering review

Reviewed baseline commit `5f3b57f9c18db657ffab0e51fdfd889a5c8065f4`, with the already-added blocked-path regression, against the supplied user request and design spec. Review scope: physics/control/perception, device protocol, journal/server, geometry, model inference, mobile extension, C++ client, and tests. This was an independent review; no production files were changed. Reporting/CLI work explicitly in progress was not treated as missing functionality.

No critical finding. Three important reproducible findings follow. The root implementer has acknowledged and is fixing findings 1 and 2; fixes were not yet present when this report was written. Line numbers refer to the baseline.

## Important findings

### 1. A collision during braking can discard the terminal run and its metrics

Locations: `src/pickloop/simulation.py:206–209,249–266`; `src/pickloop/engine.py:159,204–206,233–236`.

`stop_motion()` continues through `step()`, which always raises on prohibited contacts, even while `_stopping`. A collision during recovery braking is caught by the recovery decorator, but the subsequent unconditional terminal `stop_motion()` can raise again. `run_job()` then writes only `UNHANDLED_FAILURE` and rethrows. It does not produce `result.json`, `run.json`, final collision/drop metrics, or a normal terminal event. Thus the very runs that should establish collision/hold behavior are absent from ordinary result aggregation and replay.

Reproduction, seed 4: use `Controller.on_step` as an external scenario-injection hook. Once `state == 'TRANSPORT'`, `carrying` is true, and `norm(cell.data.qvel[:2]) > .15`, raise the existing blocker by setting `cell.model.geom_pos[blocker_id, 2] = .20` and call `mujoco.mj_forward`. This changes the world after the path was checked, so it exercises runtime detection rather than static preflight.

Observed: `VACUUM_LOSS` at simulated 7.12 s, `RECOVERY_BEGIN`, then `UNHANDLED_FAILURE: OperationError COLLISION` at 7.14 s; `run_job` raises. Evidence: `/workspace/work/pickloop-collision-review-hze0nuts/normal-4-recovery-c049e2/events.jsonl`. Only that event file and device SQLite exist in the run directory.

Fix: provide a bounded best-effort stop that latches and counts contact faults without recursively aborting on each retained contact. Record stopping failure explicitly, retain suction if feasible, and still persist a truthful terminal result and metrics. Add this dynamic-obstacle regression; asserting only static PATH_BLOCKED misses it.

### 2. Server restart neither reconciles nor exposes interrupted jobs until resubmission

Locations: `src/pickloop/server.py:26–34,67–75`; `src/pickloop/journal.py:12–17`.

The journal fences unfinished jobs when `JobStore` opens, but `create_app()` never opens it at startup. `GET /api/jobs/{job_id}` searches only in-memory jobs and completed `run.json` files. A process killed during TRANSPORT leaves no run manifest, so after restart the operator sees 404 and the persistent record still says TRANSPORT. Submitting that same ID eventually fences it through `run_job`, so duplicate physical execution was not observed; the gap is startup recovery and operational visibility.

Reproduction: create a `JobStore`, begin `interrupted` with run ID `partial-run`, transition to TRANSPORT, close it; start `TestClient(create_app(directory))`. GET returns `404 {'detail': 'Unknown job ID'}` and a read-only SQLite query still returns `TRANSPORT`.

Fix: reconcile at server startup while respecting the same process lease used by the runner, and use the journal as the authoritative fallback for historical/interrupted status. Do not open a mutating JobStore without ownership while another process is actively running. Preserve partial event/run identifiers for diagnosis. Add restart/read-only GET regression.

### 3. An executed but unconfirmed valve command has no physical effect in the simulator

Locations: `src/pickloop/engine.py:108–119`; `src/pickloop/device.py:225–227,329–350`.

The emulator durably applies the valve intent before replying, but the suction plant receives it only after `client.command()` returns successfully. If both the write ACK and its reconciliation status are unavailable, the device has executed once while the physical suction model never sees the valve change. This removes the central executed-but-unconfirmed outcome from the integrated simulation. The coordinator correctly enters HOLD and does not retry, but the physical state and retention evidence are unrealistically favorable, especially for an uncertain release.

Reproduction: wrap `DeviceEmulator._process`; after processing the first FC16 valve-on request, arm `delay_response` for the following FC03 and return `drop_ack` for the write. Run normal seed 3. Instrument device shutdown and cell close to capture final states.

Observed: `HELD DEVICE_UNCERTAIN`; device valve `True`, execution count `1`; cell valve `False`, pressure `0.0`, attachment `None`, even after terminal braking/settling.

Fix: apply controller output to the plant independently of successful client acknowledgement/status reconciliation. Keep physical state changes in the device/plant adapter, not in a success continuation of the coordinator's RPC. Preserve fail-closed coordinator behavior and at-most-once intent. Regression should lose both reply and status and assert actual valve effect occurs once while controller remains uncertain; cover release as well as seal.

## Metric qualification and smaller issues

* `simulation.py:163–168,174–179`, `engine.py:223`: `drops` is currently the count of injected/overload suction detachment events. It is not an independent physical fall detector. Running the existing lift/release component pattern with a commanded release at TCP z=.30 produces parcel center descent from .2745 m to .0850 m onto the source table (about 19 cm), yet `drop_count=0`. Either evaluate unsupported releases/falls with a predeclared threshold/support rule, or explicitly name and document this as suction-loss events rather than all parcel drops. The current fixed task normally releases near the bin, so this finding does not claim its normal successful runs secretly drop parcels.
* `simulation.py:215–229`: `collisions` counts newly prohibited robot/held-payload contact pairs with penetration greater than 1 mm; it is not all MuJoCo physical contacts. Non-held parcel/table contacts are intentionally omitted. State this definition alongside results. The important missing-result failure above must still be fixed so prohibited contacts cannot vanish from aggregation.
* `engine.py:99`: `plan()` directly calls `Observation.validate()`, whose stale checks raise `ValueError`. `Action` does not convert that exception into `OperationError`, unlike `Perception.proposals`. If a frame becomes stale between perception and planning (e.g. >5 s wall processing delay), it takes the unhandled-recovery route rather than the bounded sensor-error branch. Wrap this validation consistently. The supplied stale-at-capture scenario itself works correctly.

## Positive checks and boundaries

* Device code and tests use actual Modbus TCP frames, durable intent/application transactions, duplicate suppression, same-ID reconciliation, and persistent cancellation tombstones. No automatic new-ID resend was found after an uncertain write. The C++ client independently implements the same frames/deadline behavior. Ordinary lost-ACK reconciliation is already covered by device tests.
* JobStore prevents re-execution of the same unfinished ID. The runner obtains an exclusive file lease before opening the mutating journal. The server-visibility issue above is distinct from physical deduplication.
* Targeted carrying cancellation: seed 3, cancellation in TRANSPORT when joint speed exceeds .15. Result CANCELLED; parcel remained attached at center z=.2753 m, translational speed .000479 m/s; drops/collisions 0. Measured joint accelerations remained bounded (peak shoulder about 1.65 rad/s²). Thus the actual carrying path was tested, beyond the existing cancel-before-motion test.
* Targeted `stale_observation` and `depth_missing` runs both rejected their first observation and completed on attempt 2. Bounded permanent failure is already covered in the suite; code caps recovery at three attempts.
* Completion requires visual verification and independent evaluator truth. A targeted baseline run with `Controller.verify` forced to raise after actual placement returned HELD with truth verification true and vision verification false. Truth could not promote an unverified camera outcome into success.
* `_collision_at()` erases dynamic parcel true positions/identities from its probe before constructing a generic catalog payload envelope using pressure and robot configuration. I found no object-pose oracle supplied to perception or motion goals. The static survey/map and catalog shape are valid declared inputs. Dynamic obstacle avoidance from observed free-space is not implemented; the runtime contact check is therefore important.
* Actual RGB-D perception, CNN inference, PnP extrinsics, actuator-integrated MuJoCo transport, conditional force-limited suction, pressure checks, and final independent object truth are connected. Cup/object contact exclusion and payload compensation are explicit physical simplifications, not evidence of real suction validation.
* Mobile code implements known-map A*, encoder/landmark EKF, kinematics, bounded wheel commands, zone leasing, and a linked physics pick job. Its no-SLAM/no-charging/no-contact-dynamics/no-physical-coupling limitations are explicit. No additional blocker was found within that declared extension scope.

The full test suite was not rerun redundantly; this review used focused reproductions while the root implementer owns final verification and the frozen holdout evaluation.
