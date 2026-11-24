# New external-photo before/after evaluation

Small selected external-photo cohort. Prior seven are development only. Alternate GTIN family matches are not exact-SKU hits. Multiple views share source groups; no independent-photo confidence intervals. Produce controls evaluate fine-class identity separately.

| Role | Photos / source groups | Known / unknown | Before correct / named wrong / held | After correct / named wrong / held | Previously correct known names → held/wrong |
|---|---:|---:|---:|---:|---:|
| new_primary | 15 / 10 | 6 / 9 | 0 / 0 / 15 | 1 / 0 / 14 | 0 |
| alternate_gtin_challenge | 18 / 7 | 0 / 18 | 0 / 0 / 18 | 0 / 6 / 12 | 0 |
| prior_development | 7 / 4 | 6 / 1 | 0 / 0 / 7 | 6 / 0 / 1 | 0 |
| produce_control | 16 / 16 | 12 / 4 | 6 / 0 / 10 | 6 / 0 / 10 | 0 |
| identity_unverified | 0 / 0 | 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |

Known recall = exact correct names / known photos. Unknown false-accept rate = named predictions / unknown photos. Held known photos remain failures of naming; held unknown photos are correct rejections. See summary.json for both denominators, all transitions, views and source groups.

Dedup is conservative exact/pixel and whole/background-trimmed perceptual screening, not proof that two surviving photos show different physical packages. Exclusions remain in screening.csv; GTIN/source/session grouping is separate from photo counts. No raw external image bytes are redistributed here.

Unknown correctness regressions are separately counted as `correct_rejection->false_accept`: six in the alternate-GTIN challenge. The zero previously-correct-known-name count does not mean zero regressions. See report.md.
