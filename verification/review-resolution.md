# Independent review resolution

Review snapshot: 5f3b57f. Frozen execution snapshot after fixes: 6b4d93e.

| Finding | Resolution | Regression |
|---|---|---|
| Important: collision during stopping lost terminal artifact | Contact episodes latched; bounded stopping reports instead of recursively aborting; HELD result and metrics saved | test_dynamic_collision_has_durable_terminal_evidence RED→GREEN |
| Important: interrupted jobs invisible after restart | Lease-protected startup fences jobs; GET falls back to durable ledger | test_restart_reports_interrupted_job_without_resubmission RED→GREEN |
| Important: applied valve depended on successful RPC reconciliation | Plant reads actual durable controller output independently at physics steps | test_executed_but_unconfirmed_valve_still_affects_physics RED→GREEN |
| Drop semantics | Count force/overload loss and commanded unsupported release with >40mm clearance; distinguish from near-support placement | test_dynamic_lift_and_release |
| Collision semantics | Explicitly defined as prohibited penetration episodes >1mm; no claim to count every object contact | docs/architecture.md |
| Planning stale frame ValueError | Convert to recoverable OperationError | test_stale_observation_at_planning_becomes_recoverable_error RED→GREEN |

Full suite after these fixes: 73 passed, one external deprecation warning. No model/control tuning followed inspection of the final frozen evaluation. Live/source deployment layers have separate commit provenance from physics experiments. Browser visual QA remains unverified because runtime and managed preview are unavailable.
