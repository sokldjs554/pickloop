# Current-model transport-height comparison

Executor label: Codex. Snapshot: `5643fd6bd35897370cfb31ccc96057f093ab91cf`.

Before: 0.40 m after any failure. After: 0.40 m only after PATH_BLOCKED. Both use the same archived physical model, recovery policy and three-attempt budget.

| Rule | Completed | Mean simulated s | Mean wall s | Drops | Collisions | Wrong placements |
|---|---:|---:|---:|---:|---:|---:|
| before | 16/20 | 22.424 | 1.976 | 0 | 0 | 0 |
| after | 16/20 | 22.039 | 1.960 | 0 | 0 | 0 |

All failures remain in time denominators. Wall time is environment-specific; no wall-speedup claim.

| Case | Before | After | Before sim s | After sim s | After − before s |
|---|---|---|---:|---:|---:|
| mixed-64000 | COMPLETED | COMPLETED | 27.460 | 28.065 | +0.605 |
| mixed-64001 | COMPLETED | COMPLETED | 27.420 | 28.025 | +0.605 |
| mixed-64002 | COMPLETED | COMPLETED | 27.395 | 28.000 | +0.605 |
| mixed-64003 | COMPLETED | COMPLETED | 27.505 | 28.110 | +0.605 |
| normal-64000 | COMPLETED | COMPLETED | 16.380 | 16.380 | +0.000 |
| normal-64001 | COMPLETED | COMPLETED | 16.410 | 16.410 | +0.000 |
| normal-64002 | COMPLETED | COMPLETED | 16.415 | 16.415 | +0.000 |
| normal-64003 | COMPLETED | COMPLETED | 16.355 | 16.355 | +0.000 |
| path_blocked-64000 | COMPLETED | COMPLETED | 19.515 | 19.515 | +0.000 |
| path_blocked-64001 | COMPLETED | COMPLETED | 19.545 | 19.545 | +0.000 |
| path_blocked-64002 | COMPLETED | COMPLETED | 19.550 | 19.550 | +0.000 |
| path_blocked-64003 | COMPLETED | COMPLETED | 19.490 | 19.490 | +0.000 |
| suction_once-64000 | COMPLETED | COMPLETED | 27.460 | 24.930 | -2.530 |
| suction_once-64001 | COMPLETED | COMPLETED | 27.420 | 24.890 | -2.530 |
| suction_once-64002 | COMPLETED | COMPLETED | 27.395 | 24.865 | -2.530 |
| suction_once-64003 | COMPLETED | COMPLETED | 27.505 | 24.975 | -2.530 |
| suction_permanent-64000 | HELD | HELD | 21.380 | 21.380 | +0.000 |
| suction_permanent-64001 | HELD | HELD | 21.205 | 21.205 | +0.000 |
| suction_permanent-64002 | HELD | HELD | 21.130 | 21.130 | +0.000 |
| suction_permanent-64003 | HELD | HELD | 21.555 | 21.555 | +0.000 |

See `manifest.json`, `summary.json`, `pairs.csv` and `raw/` for frozen inputs, identities, decision traces and native evidence.
This small fixed scenario mixture supports descriptive comparison only; it does not establish a generally optimal rule or hardware safety.
