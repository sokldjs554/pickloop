# Exact carton names when market variants share graphics

The 33-photo study originally gave six unregistered photos a registered name. A replay of the same file bytes through the later Python reader reproduced one of those six names. The updated artwork decision held that Finnish orange 1 L carton and kept all four correct names from the later reader. Each version used the original photograph pixels. The recognizer received no filenames, GTIN labels, or publisher metadata. [Original study](../new-photos/report.md) · [Paired photographs and decisions](historical-paired.csv)

| Same historical cohort | Original flavour reader | Python before this change | Updated Python |
|---|---:|---:|---:|
| Exact registered names | 1/6 | 4/6 | 4/6 |
| False registered names on unregistered products | 6/27 | 1/27 | 0/27 |
| Order SKUs confirmed by the Python readout | 0/33 | 0/33 | 0/33 |

The remaining error combined a Swedish orange template and an enrolled Finnish orange template. The Swedish score was 8.222 with 257 inliers. The Finnish score was 5.932 with 102 inliers, but its aligned artwork similarity was 0.9866 versus 0.9634 and its coverage was 0.156 versus 0.146. The Swedish aggregate score cleared the existing ratio of 1.38. A comparable outside front of equal or unknown volume can now keep the match ambiguous when it has higher artwork similarity and at least as much geometric coverage. The 0.65 threshold for a comparable outside front already applied to ambiguous matches. The corrected readout still reports orange as the flavour candidate. [Artwork decision](../../../src/pickloop/registered_pack.py) · [Regression test](../../../tests/test_registered_pack.py)

Three of the four correct names matched the photographed image itself in the gallery. The fourth matched another registered gallery reference. The Finnish photograph also had an enrolled template. This is a historical retest with those references in place. [Enrolled reference records](../registered-photo-recall/enrollment.json)

## Separate regression checks

The official validation and test photos are separate from the Finnish correction example and from the exact gallery training images. They were used in earlier recognizer studies and include correlated views from stores. The artwork pass below measures the unwarped geometric matcher without the OCR, barcode or foreshortened-side routes. The frozen original file hash was checked for every frame. [Official labels](../registered-recall/) · [Artwork comparison](official-artwork.json)

| Artwork-only cohort | Registered names before → after | False registered names before → after |
|---|---:|---:|
| Official training frames excluded from enrollment | 34/56 → 34/56 | 0/184 → 0/184 |
| Official store test frames | 37/60 → 37/60 | 0/14 → 0/14 |
| Official validation frames | 6/16 → 6/16 | 0/4 → 0/4 |

The end-to-end Python reader also preserved four correct archive oblique names and one prior validation hold. The eight publisher probes preserved two correct apple retests and six correctly held outside products. The two publisher apple views are an enrolled composition and a prior volume-rule retest. [Runtime probes](runtime-probes.jsonl) · [Earlier Python side study](../oblique-packages/README.md)

## Reproduce

Run from the repository root with the catalogue extra, Tesseract English data, and the pinned DINOv2 weights in the usual PickLoop cache. Restore the original NX photos with the retrieval script from the historical study. The archive ZIP digest and model, code, and output digests are in the source lock. [Original photo retrieval](../new-photos/README.md) · [Source lock](source-lock.json)

```sh
run=$(mktemp -d)
mkdir "$run/before"
git archive 719b31ab978f0beb2997a4cd868771ce92071e3e src | tar -x -C "$run/before"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1
for phase in before after; do
    if [ "$phase" = before ]; then source_dir="$run/before/src"; else source_dir=src; fi
    PYTHONPATH="$source_dir" python docs/experiments/market-rival-retry/replay.py \
        --historical-photos /path/to/new/blind --out "$run/$phase-historical.jsonl"
    PYTHONPATH="$source_dir" python docs/experiments/market-rival-retry/replay.py \
        --dataset-zip /path/to/GroceryStoreDataset.zip --out "$run/$phase-artwork.jsonl"
done
```

## Browser follow-up

A separate Chromium check held a newly sourced Finnish apple carton that the previous browser linked to the Swedish black-flap design. The targeted replay also preserved both known Swedish publisher views. [Browser evidence and limits](browser-identity-band.md)

[Browser orange market and capacity challenge](orange-variants/README.md)
