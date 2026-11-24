# Frozen external-photo evaluation

This is a Codex-executed comparison, not evidence that the user ran it. Both methods receive the same original EXIF-oriented RGB pixels. The old method is the existing default 81-class DINOv2 catalogue head plus Bravo resolution, not the old optional hold-first juice gate. The new method applies `product_text.recognize_exact` to that unchanged decision. Printed barcodes, when detected, come from pixels; labels, filenames, URLs and GTIN metadata never enter either classifier.

`protocol.json` freezes the candidate population, truth-manifest byte hashes, duplicate rule, class registry and scoring code before inference. `model-freeze.json` records source/data/model hashes, environment versions and the barcode binary before the first image. `predictions-blind.jsonl` is written before labels are parsed; `predictions-seal.json` seals the complete batch. Only then does `score` join frozen labels. The model is not tuned on this cohort. An interrupted batch has no seal and cannot be scored as complete.

The duplicate reference is all 5,502 checksum-verified official GroceryStore train/test/validation/catalogue images, all seven prior external development photographs, and earlier ID-sorted candidates. New candidates are excluded for exact bytes/pixels or conservative whole-image/background-trimmed pHash and dHash proximity (both Hamming distances at most 8). Trimming is used only for screening. The complete `screening.csv` retains exclusions and their matched references; surviving photos are not thereby proven to show independent physical packages. Source groups conservatively pool repeated GTIN/session/packshot origins.

Roles remain separate: new registered original 1-L juice packages and out-of-catalogue variants; alternate-GTIN same-flavour challenges; all seven prior development photos; any produce controls; and identity-unverified photos. A same-flavour alternative package counts as exact UNKNOWN, so naming that flavour is an exact-SKU false accept even when `family_matches` increases. Produce controls measure catalogue fine-class naming, not packaged GTIN verification. Exact-name recall compares predictions with independently assigned SKU truth; it does not establish that every named front view visibly proves its GTIN.

`summary.json` contains explicit known/unknown denominators, before/after exact-name recall, named-wrong counts, holds, unknown false accepts, every paired transition and formerly-correct-known-name-to-bad cases. `rows.csv` joins every inferred ID to its source group, view, URLs, licence/retrieval metadata and raw recognition route/text/barcodes. `source-groups.csv`, `by_stratum`, and `by_route` expose dependence and heterogeneous capture conditions. Routes are model-selected diagnostic subsets, not randomized causal strata. No pooled accuracy or independent-photo confidence interval is asserted for this small selected source sample. A held known photo remains a naming failure; a held unknown photo is a correct rejection.

## Reproduction

Install the repository's catalogue/test extras and system Tesseract English data. Reconstruct original source bytes from the retained source metadata, checking each SHA-256. Raw copyrighted source images are not redistributed here. Original blind/label manifest bytes are preserved as `original-*.csv`; a local reconstruction may rewrite only blind `path` cells to its own paths, retaining ID and image SHA. Relative paths resolve from each blind manifest's directory. Keep label manifest bytes unchanged. PDF-extracted images have their original PDF hash and extraction instruction in source metadata.

Use a fresh output folder for each run; never replace a frozen record. From the repository root:

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1
PYTHONPATH=src python scripts/evaluate_new_photos.py prepare \
  --blind /path/to/new/blind.csv --labels /path/to/new/labels.csv \
  --prior-blind /path/to/prior/blind-inputs.csv --prior-labels /path/to/prior/external-manifest.csv \
  --archive /path/to/pickloop-groceries-fc80ba9.zip \
  --source-protocol docs/experiments/new-photos/source-protocol.txt \
  --out work/my-new-photo-run
PYTHONPATH=src python scripts/evaluate_new_photos.py infer \
  --out work/my-new-photo-run --weights /path/to/dinov2-small.safetensors
PYTHONPATH=src python scripts/evaluate_new_photos.py score \
  --out work/my-new-photo-run --labels /path/to/new/labels.csv \
  --prior-labels /path/to/prior/external-manifest.csv
PYTHONPATH=src python scripts/evaluate_new_photos.py audit --out work/my-new-photo-run
```

To reproduce included produce controls, add `--control-blind /path/to/control/blind.csv --control-labels /path/to/control/labels.csv` to `prepare`, and `--control-labels /path/to/control/labels.csv` to `score`. The official archive and DINO model hashes are in the frozen records. Different local paths/timestamps produce a new protocol hash; compare matched `(id, sha256)` populations and before/after predictions, not absolute paths or elapsed wall time. Retain your own output folder as personal evidence; this published Codex run is not relabeled as yours.

The `formerly_correct_to_bad` field concerns known names only. Unknown-rejection regressions are recorded separately in `paired_transitions.correct_rejection->false_accept`; both must be shown when discussing regressions.
