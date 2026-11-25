# Registered 1 L carton photograph study

For the shipped browser and Python results, including the two targeted apple retests and the rejected gallery expansion, see the [release report](production.md).

The first frozen revision recovered **35 of 60 registered cartons in archived store photographs**, up from 0 of 60. On **two genuinely new Swedish apple packshots**, the earlier Python recognizer named one and the revision held both. The improvement observed on legacy packaging did not transfer to these two independent publisher views. At no point did either Python version confirm an order from these 82 photographs.

| Frozen Python comparison | Photos | Registered targets | Correct names before | Correct names revised | Wrong name on a registered target before → revised | Outside target named as a registered 1 L before → revised |
|---|---:|---:|---:|---:|---:|---:|
| Archived store exposures | 74 | 60 | 0/60 | 35/60 | 4 → 2 | 0/14 → 0/14 |
| New publisher exposures | 8 | 2 | 1/2 | 0/2 | 0 → 0 | 0/6 → 0/6 |

The archive contains 19 apple, 22 orange and 19 orange/red grapefruit registered targets. The revision named **12/19 apple, 14/22 orange, and 9/19 mixed**. It named 33/45 front views and 2/15 views with a substantial side panel, and 34/55 with the target barcode outside view. Of the 25 missed registered targets, 23 were held. The broad catalogue named one apple carton plain red grapefruit and one orange carton medium-fat milk. Both errors also occurred before the revision. Both versions correctly named plain red grapefruit from their broader catalogue on three of the 14 unregistered controls and held the other 11.

On the 35 archived positives unseen by the browser developer, the first revised Python model recovered 18, compared with zero before. Preliminary worker runs covered nine positives and three controls. The corresponding Python result was 7/9 correct registered names. The contact-sheet-only subset yielded 10/16. All nine archive images with visible bar patterns, including five registered targets, yielded zero Python order confirmations. The public set has no such barcode exposures.

On the public oblique white-flap apple, the earlier system read apple and printed 1 L. The first revision retained apple as the flavour candidate, then held the name because of competing carton artwork. Both versions held the new black-flap apple, and all six unregistered same-brand foils were held. These are the paired outcomes of the first frozen revision. Any later change informed by these failures requires its own retest label. [Paired rows](python-rows.csv) · [Counts by GTIN, view, barcode visibility and prior developer exposure](python-summary.json)

## Retrospective reference-coverage test

The 14 eligible externally sourced exact positives from earlier experiments were assigned to three folds by GTIN. For each fold, we removed every external registered-pack reference of that GTIN, including the test image and different photos of the same product. The store-training references and references for other GTINs stayed available. This conservative grouping avoids treating separate retailer copies or adjacent uploads as independent physical acquisitions. Each query went through the ordinary Python recognizer; only the fold gallery changed. Previous model development included these images. This is a test of dependence on reference coverage, separate from both main cohorts.

The earlier system correctly named 2/14 photos. The revised system correctly named 1/14, a hand-held legacy orange/red grapefruit carton. It lost the earlier correct names on two studio fronts, held all six reverse or nutrition views and gave no wrong names. Each hidden group represents one positive GTIN. The results describe these 14 historical exposures. [Folds and withheld template IDs](folds-withheld.json) · [Photograph-level comparison](folds-rows.csv) · [Frozen rows and assignments](folds-freeze.json)

## Photographs and ground truth

The archive contains every official test photo for the four Swedish God Morgon juice classes in GroceryStoreDataset. The authors’ Swedish descriptions link directly to ICA listings for the three registered 1 L GTINs and a fourth 1 L red-grapefruit-only GTIN. The per-class package-information files also give volume. A curator checked all 74 photos against the class artwork before inference. Each shows a hand-held target near shelves that can contain other products. The exact GTIN association comes from the authors’ class record. Individual codes were not transcribed. A visible barcode label means that the curator could distinguish a bar pattern on the target package, including tilted or clipped patterns. [Archive image links, class evidence and conditions](archive-labels.csv) · [Pinned dataset](https://github.com/marcusklasson/GroceryStoreDataset/tree/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc)

For each class, the original researchers assigned a store’s captures wholly to training or testing. Several frames show one carton held from different angles in front of the same shelf. The archive has four class-level identities and an unknown number of physical cartons. The project had already used these test images in earlier reports. During browser development, a preliminary worker ran on frame numbers 001, 010 and 012 of each class. The browser developer also saw contact sheets of every apple and plain-red-grapefruit frame while selecting demo photographs. Of the remaining photos, 27 were inspected on those two contact sheets only, and 35 were neither inspected nor run by the browser developer. All 35 are registered orange or mixed juice. They give no independent plain-red-grapefruit specificity measurement. Curator inspection to establish truth and check duplicates was separate. [Original paper](https://arxiv.org/abs/1901.00711) · [Per-row exposure and results](python-rows.csv)

The public set contains eight previously unscored original publisher files covering seven GTINs. Arla supplied a black-flap Swedish apple front. Torebrings supplied an oblique white-flap apple packshot with the left panel in view. Both publisher records list GTIN 7310865074225. The six outside products are Swedish orange juice 1.75 L, orange nectar in two sizes, organic orange in an 850 mL bottle, Fruit Crush orange/mango 1 L, and plain red grapefruit 1 L. All are the same brand. All target barcodes are outside view. These are studio/catalogue images and may be renders. Two apple designs represent two views of one trade identity. The cohort has zero fresh phone photographs and zero fresh registered orange or mixed-juice positives. No 250 mL SKU appears in either cohort. [Original URLs, exact product records, rights and hashes](public-labels.csv)

The curator compared the public images with 6,076 prior image records using byte hashes, EXIF-oriented pixel hashes, and paired pHash/dHash checks on both whole and background-trimmed images. The threshold was eight bits on both hashes of either image region. A secondary SIFT screen on 182 related prior photos ranked homography inliers with a 0.74 match ratio and 3 px reprojection tolerance at up to 620 px long edge. High local matches prompted a visual comparison of pose, artwork, and background. The standard logo and printed fruit can match across different cartons. The retained oblique white-flap apple shares artwork with an older straight front, but shows a full side panel absent from that acquisition. The new black-flap apple visibly differs from the old white-flap file previously served at the same URI. Publisher identity or a changed byte hash alone did not qualify a photograph as new. [Retrieval screening](public-screening.csv)

The Norwegian SeSum and NorgesGruppen orange pictures reproduced an older Swedish supplier photograph. Several Torebrings and Arla packshots were derivatives or exact copies. Both prior and current Arla mixed-juice files were byte-identical. The 2024 and 2026 manufacturer brochures reused the previously scored orange scene. All 12 numeric Open Food Facts uploads for the three exact GTINs had previously been inspected. The separate enrollment screen found zero byte, pixel, or paired-perceptual duplicate flags for the 82 main rows against all 31 enrolled references and 3,017 official train/validation/iconic images. The authors’ test frames remain correlated within their own split. [Enrollment comparisons](enrollment-screen.csv)

Both main photo rosters were sealed before revised-model evaluation. Python received EXIF-oriented RGB only, via the ordinary and strict entry points on each full photo. Before was release revision `e522495`. After used the implementation at `099f3c4`, including the revised handling of nutrition serving sizes. The CPU DINO weights and model files were hashed. Both versions used the same photos, head, and DINO weights. The Python matcher developer used official training and earlier external images for template and threshold selection. The preliminary browser exposures limit claims of blinding. A separate shipping browser file-upload study on these same bytes records a different runtime. [Archive freeze](archive-freeze.json) · [Public freeze](public-freeze.json) · [Python code and weights](python-model-freeze.json) · [Paired prediction seal](python-prediction-seal.json)

## Reproduce

The raw ledgers retain every prediction. The scorer verifies hashes, row order, and population before calculating counts and exposure strata.

```sh
python scripts/score_registered_recall.py --out /tmp/registered-recall-rescore
diff docs/experiments/registered-recall/python-rows.csv /tmp/registered-recall-rescore/python-rows.csv
diff docs/experiments/registered-recall/python-summary.json /tmp/registered-recall-rescore/python-summary.json
diff docs/experiments/registered-recall/folds-rows.csv /tmp/registered-recall-rescore/folds-rows.csv
```

The inference commands require the project catalogue extra, Tesseract English data and the verified DINO weights. Run them from the repository root. The public set was successfully refetched with all eight hashes. Arla’s main apple URL can also return the old white-flap asset. Its alternate URL returned the original black-flap bytes. The raw retail and phone photos remain at their source. [Alternate version URL](public-alternate-urls.json)

```sh
run=$(mktemp -d)
mkdir "$run/before" "$run/after"
git archive e522495 src | tar -x -C "$run/before"
git archive 099f3c4 src | tar -x -C "$run/after"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1
for cohort in archive public; do
    python scripts/evaluate_registered_recall.py fetch "$cohort" "$run/photos"
    for phase in before after; do
        PYTHONPATH="$run/$phase/src" python scripts/evaluate_registered_recall.py infer "$cohort" "$run/photos" --out "$run/$cohort-$phase.jsonl"
    done
done
python scripts/evaluate_registered_folds.py "$run/photos" --fetch
PYTHONPATH="$run/before/src" python scripts/evaluate_registered_folds.py "$run/photos" --out "$run/folds-before.jsonl"
PYTHONPATH="$run/after/src" python scripts/evaluate_registered_folds.py "$run/photos" --out "$run/folds-after.jsonl" --revised
python scripts/score_registered_recall.py --ledgers "$run" --seal
python scripts/score_registered_recall.py --ledgers "$run" --out "$run/scores"
```
