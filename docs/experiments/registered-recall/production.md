# Deployed recognition and rejected gallery expansion

**The deployed Python source remains commit `3f4fb51`.** The nine-template trial improved registered recall but introduced a false name on a plain red grapefruit control. The predeclared acceptance condition rejected it.

Adding the updated apple artwork and revising the printed-volume rule recovered the two public apple failures. One photo reproduces the enrolled artwork. The other directly motivated the rule. **The fresh public cohort contains zero independent registered positives after excluding both retests.** The six other public cartons remained held. None of these 82 photographs produced a confirmed strict Python order.

| Photo cohort | Registered / outside | Baseline correct names | First revision correct | Production correct |
|---|---:|---:|---:|---:|
| Archived Swedish store images | 60 / 14 | 0/60 | 35/60 | 35/60 |
| Public apple with enrolled manufacturer composition | 1 / 0 | 0/1 | 0/1 | 1/1 |
| Public oblique apple that motivated the volume rule | 1 / 0 | 1/1 | 0/1 | 1/1 |
| Other public same-brand products | 0 / 6 | — | — | — |
| Separate archived validation probe | 16 / 4 | 0/16 | 6/16 | 6/16 |

Excluding the enrolled Arla composition alone gives 36/61 correct across the first two cohorts, including the targeted Torebrings retest. Excluding both gives **35/60**, all from the archived store cohort. The production and first revisions agreed on every archived name and every order. Both named 33/45 registered front views, 2/15 registered side-visible views and 18/35 registered frames the browser developer had never viewed. Both misnamed an apple carton as plain red grapefruit (RR-ebf05ee2e700d493) and an orange carton as Arla medium-fat milk (RR-787b9393075dd1b4). Both held 23 of the 60 registered targets. Three of the 14 outside archive controls were correctly named plain red grapefruit by the broader catalogue. None of the 20 outside products in the main cohorts received one of the three registered names. [Per-photo rows](production-rows.csv) · [Counts including exclusions, broader-catalogue errors and strict orders](production-summary.json)

The supplementary probe includes every official validation image from the three registered classes (five apple, five orange, six mixed) and four plain-red-grapefruit negatives. All 20 had been evaluated in older general-catalogue experiments; eleven also appeared in earlier carton-panel development. They show shelf scenes with several cartons as well as individual hand-held packages. We froze the full roster after production code was fixed. Both first and production revisions named six registered targets, held the other ten and made zero strict confirmations. The probe is a legacy regression check. [Labels, sources and SHA-256](legacy-validation-labels.csv) · [Probe freeze](legacy-validation-freeze.json) · [Prediction seal](production-prediction-seal.json)

The eight public sources and 74 archived images are the same original, EXIF-oriented inputs as the first paired study. Both Python modes ran independently with the production model files and DINO weights. The 45 recorded files match commit `3f4fb51` byte for byte. The Python gallery and browser gallery have identical decoded contents. [Model freeze](production-model-freeze.json) · [First paired study and original records](README.md)

The manufacturer supplied a higher-resolution version of the black-flap Arla apple photograph. The production gallery contains its descriptors. Both byte and perceptual hashes miss this transformed copy. Visual inspection and SIFT alignment establish the shared composition. The black-flap and white-flap apple packshots yielded 84 and 60 local homography inliers respectively. The latter shows the left side and a different flap, pack design and camera angle. Its earlier failure informed the new volume rule. Both images therefore have separate, explicit retest roles. A second audit compared all 102 inputs against the 32 enrolled images. No other same-composition copy was found. [Manufacturer source disclosure](../registered-photo-recall/apple-source.json) · [Reference screen](production-enrollment-screen.csv) · [Additional local alignment results](production-apple-screen.csv)

## Browser upload results

Using the ordinary photo chooser, Chromium correctly named 30 of the 60 registered store targets (7/19 apple, 12/22 orange, 11/19 orange/red grapefruit). The former reader named zero. The current reader held the remaining 30. One of the 14 plain-red-grapefruit controls received a registered name. The public retest named both registered apple photos and held all six lookalikes. Neither set produced a barcode-confirmed order. The final release repeated all 82 uploads with identical records. [Store photo ledger](archive-browser-production.jsonl) · [Public photo ledger](public-browser-production.jsonl) · [Release check and file hashes](browser-release-check.json)

To repeat the test with Python, Pillow, Playwright, and an installed Chromium binary, run from the repository root:

```sh
for cohort in archive public; do
    python scripts/evaluate_registered_recall.py fetch "$cohort" /tmp/pickloop-registered-photos
    python scripts/evaluate_registered_browser.py "docs/experiments/registered-recall/$cohort-blind.csv" /tmp/pickloop-registered-photos --chromium /usr/bin/chromium --out "/tmp/$cohort-browser.jsonl"
done
```

## Rejected nine-reference trial

The candidate added nine official training photos covering three apple fronts, two orange fronts, two orange/red grapefruit views, and two plain-red-grapefruit views. The goal was to cover more angles and side panels with the existing decision thresholds. Within the train-only comparison, registered names improved from 7/13 to 9/13. The two recovered apple photos shared a shelf and apparent carton with a training reference. The visual matcher falsely named none of 23 plain red grapefruit and 31 other juice training controls. [Reference polygons, source paths and SHA-256](expanded/addition.json) · [Train-only query roster](expanded/train-eval-roster.json) · [Development results and acquisition limitation](expanded/train-development-summary.json)

| Follow-up archive stratum | Deployed v2 correct | Expanded correct |
|---|---:|---:|
| All registered frames | 35/60 | 40/60 |
| Front views | 33/45 | 37/45 |
| Side-visible views | 2/15 | 3/15 |
| Frames unseen by browser developer | 18/35 | 20/35 |
| Excluding nine frames with plausible same-GTIN acquisition setting | 30/51 | 35/51 |
| Outside controls falsely named as a registered 1 L product | 0/14 | **1/14** |

The candidate gained five names and lost zero on the 60 registered targets. All five gains occurred outside the nine flagged exposures. The 82 main images still yielded zero strict order confirmations and the public retests remained 2/2 with 0/6 false names on the other public cartons. The new error changed the decision on official test frame `God-Morgon-Red-Grapefruit-Juice_001` (RR-dd462bf509593057). It shows red grapefruit in the hand and apple cartons behind it. The apple template yielded 97 inliers and projected to the upper-right background apple. The deployed model held this frame. The archive was used to accept or reject the trial, so this comparison is a follow-up selection result. [Per-image decisions](expanded-rows.csv) · [All subgroup counts](expanded-summary.json) · [Prediction seal](expanded-prediction-seal.json)

The 738 comparisons between the nine extra references and all 82 queries yielded no exact or paired-perceptual duplicate flags. We also ran SIFT matching across the full frames and inspected likely overlaps. Some reference photos include several cartons or the same shelf setting. Correspondences outside a panel can come from another carton displaying identical artwork. Five apple and four orange test frames show the same design, glass-front display and similar aisle setting as a training reference of that flavour. We excluded all nine in the additional sensitivity calculation. A physical carton count cannot be established from these images. [Pairwise geometry and hash checks](expanded-enrollment-screen.csv) · [Frame-level acquisition review](expanded-acquisition-review.csv)

## Reproduce

The scorer validates the original paired prediction seals and the production seals before calculating counts.

```sh
python scripts/evaluate_registered_production.py score --out /tmp/registered-production-score
diff docs/experiments/registered-recall/production-rows.csv /tmp/registered-production-score/production-rows.csv
diff docs/experiments/registered-recall/production-summary.json /tmp/registered-production-score/production-summary.json
```

To repeat inference, use the project catalogue dependencies, Tesseract English and the same pinned DINO weights as the first study. Run from the repository root.

```sh
run=$(mktemp -d)
mkdir "$run/before" "$run/v1" "$run/production"
git archive e522495 src | tar -x -C "$run/before"
git archive 099f3c4 src | tar -x -C "$run/v1"
git archive 3f4fb51 src | tar -x -C "$run/production"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1
for cohort in public archive legacy-validation; do
    python scripts/evaluate_registered_production.py fetch --cohort "$cohort" --photos "$run/photos"
    for phase in before v1 production; do
        tag=$phase
        if [ "$cohort" != legacy-validation ] && [ "$phase" = v1 ]; then tag=after; fi
        PYTHONPATH="$run/$phase/src" python scripts/evaluate_registered_production.py infer --cohort "$cohort" --photos "$run/photos" --out "$run/$cohort-$tag.jsonl"
    done
done
python scripts/evaluate_registered_production.py seal --ledgers "$run"
python scripts/evaluate_registered_production.py score --ledgers "$run" --out "$run/scores"
```


The rejected weights are excluded from the shipping package. To reconstruct the exact trial, supply the pinned ZIP (SHA-256 `f2434611ed5dd472dae830d6c7fbdf4b75dfd1697ba25f1280f0a1d0ce9170b0`) and a new output directory. The rebuild extracts the accepted source privately, adds the nine checked reference crops, and validates the candidate JSON, NPZ and runtime pin. A local rebuild reproduced the frozen NPZ and matcher source hashes. The commands below continue the reproduction session above. [Variant construction and expected hashes](expanded/freeze.json) · [Frozen comparison criteria](expanded-model-freeze.json)

```sh
python docs/experiments/registered-recall/expanded/rebuild.py /path/to/GroceryStoreDataset.zip "$run/expanded"
for cohort in public archive; do
    PYTHONPATH="$run/expanded/src" python scripts/evaluate_registered_production.py infer --cohort "$cohort" --photos "$run/photos" --out "$run/$cohort-expanded.jsonl"
done
python scripts/score_expanded_recall.py --ledgers "$run" --seal
python scripts/score_expanded_recall.py --ledgers "$run" --out "$run/scores"
```
