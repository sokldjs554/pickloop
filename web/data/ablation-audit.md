# Independent audit: frozen four-policy ablation

Read-only audit of `runs/ablation-heldout/manifest.json`, `metrics.json`, all 576 raw `result.json` files and event sequences, plus selected failure/recovery traces. No engine runs, outcome replacements, source changes, or regenerated primary metrics were performed. This audit is descriptive verification of the completed experiment, not an additional preregistered experiment.

## Integrity and numerical checks

- Frozen commit: `a1e412b7abd3fad6f3347af6472d9fff4fdd8a71`.
- Source SHA-256: `73c58c5bc497f621e0a40535940295473c34b637a23450dd05d5b5422080c530`.
- Model SHA-256: `9a111d8a584cd48a681d80a4a6f0fc7681aedba611f1afbd43fc81d7cf459bec`.
- Exactly **576 runs = 12 seeds × 12 conditions × 4 policies**. Seeds are 3000–3011. All 144 case identities have exactly one baseline, naive, reobserve, and recovery result.
- Every matched case has identical initial physical truth and condition data across policies. Every result has the manifest's source and model fingerprints. All recorded source-file hashes and the model hash also matched files present during this audit.
- The manifest's canonical cases digest, embedded metrics protocol, and all 576 recorded raw-result hashes matched.
- All event IDs are contiguous, each run has exactly one terminal event, and terminal status/success/reason/metrics equal its result file. Every successful result has both visual and independent truth verification and zero wrong placements.
- Completion counts, drop/collision/retry totals, simulated and wall-time totals/throughput, seed standard deviations, and all reported seed-cluster bootstrap intervals were independently recomputed and matched. Bootstrap recomputation used 10,000 resamples and RNG seed 81419, as specified in the implementation.

No numerical or pairing discrepancy was found.

## Primary results remain unchanged

| Policy | Completed / 144 | Completion | Seed-cluster 95% interval | Mean simulated seconds | Simulated completions/hour |
|---|---:|---:|---:|---:|---:|
| baseline | 24 | 16.67% | 16.67–16.67% | 5.44 | 110.21 |
| naive | 86 | 59.72% | 56.94–62.50% | 17.94 | 119.87 |
| reobserve | 103 | 71.53% | 69.44–73.61% | 18.06 | 142.57 |
| recovery | 113 | 78.47% | 75.00–81.25% | 20.31 | 139.11 |

Baseline has one attempt; the other three policies have the same maximum three attempts and 60 simulated/90 wall-second budgets. Safety stopping is included in elapsed time. Baseline is therefore a retry-budget reference, not the primary equal-budget causal comparison.

| Equal-budget contrast | Later policy only | Earlier policy only | Completion difference | Seed-cluster 95% interval |
|---|---:|---:|---:|---:|
| naive → recovery | 27 | 0 | +18.75 percentage points | +15.97 to +21.53 |
| naive → reobserve | 17 | 0 | +11.81 percentage points | +9.72 to +13.89 |
| reobserve → recovery | 10 | 0 | +6.94 percentage points | +4.86 to +8.33 |

The 27 naive-to-recovery wins comprise **12 calibration-error cases, 10 blocked-path cases, 3 drop cases, and 2 cases with unconfirmed device RPC results**. The last two must not be credited solely to reobservation or path logic.

Selected traces support the intended mechanisms: calibration seed 3000 reuses an erroneous x≈0.4172 m grasp under naive, while reobserve updates it to x≈0.3801 m after the transient error expires; drop seed 3005 updates the displaced target from approximately (0.3865, −0.1572) m to (0.4315, 0.0204) m. Blocked-path seed 3001 retains its payload and completes with the higher retry clearance, while fixed-clearance reobserve exhausts attempts. Recovery still holds on blocked-path seeds 3000 and 3002, whose blocker tops are approximately 0.3586 and 0.3601 m. Thus the higher-clearance strategy is bounded and does not succeed on every obstruction.

## Two transport-uncertainty cases limit mechanism attribution

| Case | Naive failure | Evidence |
|---|---|---|
| seed 3000, suction_once | Attempt 2, SEAL, simulated 12.49 s; command 3 has no confirmed result | `suction_once-3000-naive-b58a9f/events.jsonl`, event 26 |
| seed 3008, communication_delay | Attempt 2, RELEASE, simulated 18.34 s; command 2 has no confirmed result | `communication_delay-3008-naive-4c8a1d/events.jsonl`, event 35 |

Both terminate `HELD / DEVICE_UNCERTAIN`; reobserve and recovery complete their matched cases. The first failure occurs after its suction outage ends at 5.4164 s. The second occurs after the programmed communication window ends at 6.8873 s and during RELEASE, outside the valve-on fault-injection branch. Scanning all 576 event files found no other case identity with an uncertainty reason.

The logs establish `UncertainCommandError: no confirmed result`; **they do not preserve the underlying exception sufficiently to prove that a TCP deadline, rather than another transport failure, was the cause**. These are unplanned transport-uncertainty outcomes in the observed implementation. Terminal handling correctly retains current output without a new release: the first later snapshot shows ON/attached, and the second shows an already-applied OFF/detached state. RETAIN is not misreported as proof of suction remaining ON.

Keep both failures in the primary results. Real TCP/scheduling behavior is not determined solely by the frozen synthetic condition, so identical-seed reruns are not guaranteed to reproduce these two exact outcomes. Do not selectively rerun or replace them, or describe all 27 wins as isolated algorithmic effects. Future experiments could preserve the underlying RPC exception chain and measure transport variability separately; that is not a change to this frozen evaluation.

## Exploratory sensitivity, not a replacement result

Post hoc, excluding **both complete case identities across all four policies** leaves 142 matched cases. This is an exploratory descriptive sensitivity check; it changes the sampled condition mix and does not repair or supersede the preregistered result.

Remaining completions are baseline **24/142**, naive **86/142**, reobserve **101/142**, recovery **111/142**.

| Contrast | Later policy only | Earlier policy only | Trial-weighted difference among 142 retained pairs |
|---|---:|---:|---:|
| naive → recovery | 25 | 0 | +17.61 percentage points |
| naive → reobserve | 15 | 0 | +10.56 percentage points |
| reobserve → recovery | 10 | 0 | +7.04 percentage points |

These sensitivity percentages weight each retained case equally. Removing one case from each of seeds 3000 and 3008 makes cluster sizes unequal; the table intentionally does not claim to be the original equal-seed estimator or provide a new inferential confidence interval. The primary 144-pair estimates and intervals above remain authoritative.

## Seed variation and interpretation

Each entry below is completed cases out of 12; columns follow baseline / naive / reobserve / recovery.

| Seed | baseline | naive | reobserve | recovery |
|---|---:|---:|---:|---:|
| 3000 | 2 | 6 | 8 | 8 |
| 3001 | 2 | 8 | 9 | 10 |
| 3002 | 2 | 8 | 9 | 9 |
| 3003 | 2 | 7 | 8 | 9 |
| 3004 | 2 | 7 | 8 | 9 |
| 3005 | 2 | 7 | 9 | 10 |
| 3006 | 2 | 7 | 8 | 9 |
| 3007 | 2 | 8 | 9 | 10 |
| 3008 | 2 | 7 | 9 | 10 |
| 3009 | 2 | 7 | 9 | 10 |
| 3010 | 2 | 7 | 9 | 10 |
| 3011 | 2 | 7 | 8 | 9 |

The baseline's degenerate interval reflects identical aggregate completion counts across these 12 seed clusters; it does not establish zero uncertainty outside this fixed synthetic benchmark. Confidence intervals resample seed families, hold the selected condition mixture fixed, and do not quantify hardware/general-domain performance or repeated network-run variability.

**Completion and speed trade off:** recovery completes ten more cases than reobserve, but mean simulated duration rises from 18.06 to 20.31 s and aggregate simulated throughput falls from 142.57 to 139.11 completions/hour. Wall throughput likewise falls from 1410.21 to 1383.05 completions/hour. Do not claim recovery is faster or dominates every metric. These are simulator/program rates, not warehouse throughput.

All four policies record 12 drops and zero wrong placements/prohibited collisions. Recovery improves post-failure completion; these measurements do not show fewer initial drop events, comprehensive collision safety, or physical deployment validation. Unknown and permanent suction-outage cases remain held under every policy.
