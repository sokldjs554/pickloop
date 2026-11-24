# What the frozen new-photo comparison establishes

The candidate does **not** establish reliable recognition of new exact SKUs. On the retained new juice photographs it names one of six registered-SKU photos correctly and incorrectly names six alternate-GTIN photos. Its success on all six known prior photographs is development evidence, not a new-photo result. No model or threshold was changed after inspecting these results.

| Frozen role | Known / unknown photos | Before → after correct known names | Before → after wrong names | Before → after holds |
|---|---:|---:|---:|---:|
| New primary: original registered GTINs and outside-catalogue variants | 6 / 9 | 0 → 1 | 0 → 0 | 15 → 14 |
| New alternate-GTIN same-flavour challenge | 0 / 18 | 0 → 0 | 0 → 6 | 18 → 12 |
| Prior development photos | 6 / 1 | 0 → 6 | 0 → 0 | 7 → 1 |
| Separate produce controls | 12 / 4 | 6 → 6 | 0 → 0 | 10 → 10 |

The 33 retained new juice photos together contain six known and 27 exact-UNKNOWN examples. Their descriptive exact-name recall is 0/6 → 1/6; unknown false accepts are 0/27 → 6/27. This pooled count is supplementary: the primary and deliberately difficult alternate-package challenge remain separately reported, and the sample is not a population prevalence estimate. Seven new juice photographs receive a name after the change; one name matches exact-SKU truth, and six only match the flavour family.

The primary's sole gain is `NX-d03141e8696f584c`, an unchanged manufacturer scene extracted from a PDF, recognized through package text. Original registered front views are 0/1 correct after conservative screening; registered back views are 0/4; the manufacturer context view is 1/1. The known photos represent five source groups. The new primary's nine unknown photos remain held. These observations support neither broad front-view generalization nor proven barcode identification of the original three SKUs.

All six exact-identity regressions are `correct_rejection → false_accept`, in front photographs from the alternate-GTIN challenge:

| ID | Source GTIN | Named flavour after change |
|---|---|---|
| NX-128b044de60a6242 | 6415130050490 | Orange |
| NX-2874d2801bee038e | 6415130050506 | Apple |
| NX-2eca27540a00d80d | 7310865074768 | Orange |
| NX-63455b37f6fb074a | 7310865074768 | Orange |
| NX-696557e5fb415bd8 | 7310865081650 | Apple |
| NX-d152da1019eb25f9 | 6415130089834 | Orange |

All six use the package-text route without a decoded barcode. They are **not exact-SKU hits**, even though their family labels agree. The alternate challenge has 18 photos from seven groups: 14 fronts (six false accepts) and four backs (all held). Two backs contain optically decoded unregistered EANs and are held by the barcode route; this demonstrates rejection of those two visible unknown codes, not successful reading of a registered code in this cohort.

The summary field `formerly_correct_to_bad` counts previously correct **known names** becoming held/wrong, which is zero here. It does not include the six unknown-rejection regressions above; those remain explicit in `paired_transitions`. Zero previously correct-name regressions must not be described as zero regressions overall.

Produce controls are full physical scenes from 16 independently attributed source photographs, evaluated separately as fine classes. Banana is 3/4 correct, Pineapple 3/4, Cucumber 0/4, and all four unregistered Strawberry photos are held, identically before and after. Thus the control shows no changes on these photos, with substantial existing missed naming; it does not show complete ordinary-produce recognition.

## Independence and screening limits

There were 58 frozen candidates: 35 new juice, seven prior development, and 16 control photos. Two new candidates were excluded by the predeclared conservative perceptual rule, leaving 56 predictions. Neither exclusion was an exact byte match. `NX-64cb3e6d4264d35a` (registered Apple front) was close to the old official iconic image (whole-image pHash distance 2, dHash 0). `NX-e712776ea6272f14` (unknown tropical blend front) was close to prior packshots (nearest pHash 6, dHash 1). Such shape-based matches can exclude genuinely different packaging/products; these are **near-duplicate candidates, not confirmed reused photographs**. Exclusions were fixed before inference and are not restored based on outcomes. They leave very limited registered-front evidence.

The dedup reference included all 5,502 official images, not only training data, plus the previous seven photographs. Grouping is conservative source/GTIN/session provenance, not proof of a different physical carton per group. The primary has ten source groups, the alternate challenge seven, prior development four, and produce controls 16. Multiple views and selected source availability preclude an independent-photo accuracy confidence interval or a general deployment claim. No new-photo outcome was used to select a different candidate method or tune this one.

## Verification and reproducibility

The one joint batch completed on this machine; labels were joined only after a complete 56-row prediction seal. Source/data hashes were checked before every image and after the final image. The frozen scorer audit and an independent raw-ledger/CSV reducer agree on all row counts, paired identities, correct names, wrong names, holds and unknown false accepts. Ten focused evaluator tests pass.

- Evaluator SHA-256: `6cf920b298a5910cf1e5a934fbabe9a16fa3319f0959b54e9a2c39385b7b44b2`
- Protocol SHA-256: `0ecf17b009c5e1a745643c2115e641a4379e005fa48d9bf2935bd25e69e9b1aa`
- Model-freeze SHA-256: `4b3c9cf7fde746fad750866a126a7c6ed1c2d82dbc97f0f4989eb231b2548467`
- Combined source/data index SHA-256: `01ea168aadef707ce18579064a5c6a0ad5cb9bc93353e6014e6254624ec820cf`
- Prediction ledger SHA-256: `d5746510470698d44572774b41f6eaffd164adabebd366828df44b84e3c0a775`

The frozen methods are `product_text.py` SHA `3bbbfa242b489920a52d59ee29cc8f478b7c6b2c63511e2815687d034106d3b7` and `pack_barcode.py` SHA `f38cd2aab03acf1fedb0a6427ea863c4560153f6e84119e78c5e3a0e48602f31`, alongside the unchanged baseline head/Bravo resolver. Full per-file hashes, OCR/DINO data hashes and decoder/environment versions are in `model-freeze.json`. The measured 63.16-second batch time is specific to this machine and concurrent workload, not a speedup claim.

Use `README.md` for the four-stage CLI, `rows.csv` for per-photo source links/attribution/routes, `summary.json` for denominators/strata/groups/transitions, and `screening.csv` plus `labels-joined-after.csv` for exclusions. Original manifest bytes are retained. Source photographs are linked and hashed rather than redistributed. This run was performed by Codex; it is not the user's personal run or their earlier PR1 evidence.
