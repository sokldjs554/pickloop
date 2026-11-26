# Unregistered God Morgon packages

This study asks whether a shopper's photo of a similar God Morgon drink can be assigned to a registered product or approved as an exact order. The registry contains four GTINs. Each package in this challenge has a verified GTIN outside those four.

## v28 baseline and final retest

The final reader was evaluated on the same 16 source files. Developers examined the Finnish Apple 1 L control after the first candidate returned the registered Swedish product name. The Norwegian Smooth Orange 1.75 L photograph was also examined while implementing the browser capacity check. Both are targeted retests. All 16 final results are repeat measurements on this frozen set.

| Reader and cohort | Photos | Wrong registered product | Wrong exact order | Read outside barcode | Outside gallery | Outside capacity on same pack | Insufficient evidence | Ambiguous |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v28 baseline, strict | 11 | 0 | 0 | 3 | 0 | 0 | 7 | 1 |
| Final retest, strict | 11 | 0 | 0 | 3 | 0 | 1 | 7 | 0 |
| v28 baseline, look-alike controls | 5 | 1 | 0 | 0 | 3 | 0 | 1 | 0 |
| Final retest, look-alike controls | 5 | 0 | 0 | 0 | 3 | 0 | 2 | 0 |

The baseline assigned the Finnish Apple carton to the Swedish Apple SKU. The final reader held it because the photo lacked distinguishing evidence. The baseline and final both held its order. The final browser read the three outside EANs correctly and displayed the unregistered status in the product result. It also localized the complete Smooth Orange title and 1.75 L capacity on the same foreground face as its ambiguous carton comparison. That observation ruled out the registered capacities while leaving the exact product and order held. In total, seven of the 16 packages had positive outside evidence and nine remained unresolved.

[Final per-photo decisions](final-decisions.csv) · [Final counts and ledger digests](final-summary.json) · [v28 browser output](baseline.jsonl) · [Final browser output](final.jsonl) · [Final component digests](final-reader.json)

## First frozen candidate

The v28 baseline and first candidate held the exact order on all 16 photographs and made the same product decisions. The candidate added an explicit unregistered-product message to the product result for all three correctly decoded outside GTINs. The baseline displayed those GTINs in the barcode result.

| Cohort | Photos / GTINs | Wrong registered product | Wrong exact order | Read outside barcode | Matched outside gallery | Insufficient evidence | Ambiguous |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Strict | 11 / 8 | 0 | 0 | 3 | 0 | 7 | 1 |
| Look-alike controls | 5 / 5 | 1 | 0 | 0 | 3 | 1 | 0 |

All three decoded GTINs were EAN-13 codes and agreed with the independently frozen labels. This cohort contains no EAN-8 or UPC-E ground truth. The wrong product was Finnish Classic Apple 1 L, GTIN `6415130050506`. Both readers returned the registered Swedish Apple 1 L name, associated with GTIN `7310865074225`, from its package appearance. The photo provided no readable barcode to authorize the order. The Finnish orange–red grapefruit, orange–mandarin and blood orange–apple control packages matched the outside gallery. The single red-grapefruit control remained unresolved.

Both runs used Chromium 156.0.8078.79, verified every photo's hash and completed all 16 reads. The HTTP logs show successful delivery of the baseline's two galleries and the candidate's four galleries. No failed gallery loads appear in the scored ledgers.

[Per-photo comparison](decisions.csv) · [Totals and ledger digests](summary.json) · [Baseline browser output](baseline.jsonl) · [Candidate browser output](candidate.jsonl) · [Candidate component digests](candidate-reader.json)

## Photographs and labels

The strict cohort contains **11 source images of 8 unregistered GTINs**. Seven are contributor photos and four are supplier-style packshots. Six show the front, two show both the front and side, and three show the barcode side. One contributor photographed the organic orange bottle sideways on a shelf and framed only part of it. Every replay uses the complete source file. Two pairs of bottle views come from the same contributor and product, so the number of independent packages is smaller than the number of photos.

Five additional Finnish 1 L retailer packshots test especially close visual matches. They show Classic Apple, Classic Orange Red Grapefruit, Selected Citrus Red Grapefruit, Orange-Mandarin, and Blood Orange-Apple. Two have the same flavour and volume as a Swedish registered item, with a different GTIN. These five contain distinct label art, but their composition triggered the pre-set near-duplicate screen against the prior Finnish orange image or the newly selected orange-mango image. Their results are reported separately. A resized copy of the previous Finnish orange photo and a previously examined apple 250 mL photo were excluded entirely.

[Labels, packaging details, source records, image URLs and attribution](labels.csv) · [Opaque inputs](blind.csv) · [Nearest comparison for every included photo](screening.csv) · [Pre-inference freeze and checksums](freeze.json)

## Sampling and duplicate screening

We selected public God Morgon / God Morgen photos of closely related citrus and apple products from Open Food Facts original numbered uploads and Kesko item-specific product media. Photographer records, manufacturer or retailer listings, and visible packaging establish the item. Buyers can check each source in the label ledger. A contributor-supplied product record supports some GTINs. Images are referenced at source, with source rights recorded per row.

The screen compared each file against 5,502 official GroceryStoreDataset fingerprints, 2,556 additional distinct prior files, and 6,559 unique digests in previously published experiment records. It checked identical bytes, decoded RGB pixels, and paired 64-bit perceptual and difference hashes. A pair was flagged if both distances were at most eight on the full image or on the background-trimmed image. The strict cohort has zero flags against previous files or earlier passing photos in the new batch. The five supplemental rows record exactly which other design triggered a flag. The official fingerprint cache matched all 5,502 paths and SHA-256 digests in the repository training and prediction ledgers. Its source archive SHA-256 is `f2434611ed5dd472dae830d6c7fbdf4b75dfd1697ba25f1280f0a1d0ce9170b0`. The additional references include earlier fit, test, development, source candidates and previews. These comparisons cannot exhaust every photo on the public web.

We froze the blind manifest, labels and screening results before opening any image in the reader. The browser received image bytes under a generic filename, while the scorer joined labels by ID and SHA-256 after inference. No photos were registered as references or used to fit this study. The resulting rates apply to the sampled packages.

## Replay

From the repository root, with Chromium, Python, Pillow and Playwright installed, run the following commands. An independent refetch reproduced all 16 original SHA-256 digests. The supplier may replace a linked photo. The fetch script checks the frozen hash and stops if that happens.

```sh
study=docs/experiments/side-unknown-challenge
run_dir=$(mktemp -d)
python "$study/study.py" fetch "$run_dir/photos"
git archive 719b31ab978f0beb2997a4cd868771ce92071e3e \
  web/recognition.html web/recognition.js web/package-reader.js web/recognition.css \
  web/evidence.css web/styles.css web/vendor/package-reader \
  web/data/registered-pack-gallery.json web/data/registered-detail-gallery.json \
  | tar -x -C "$run_dir"
python scripts/evaluate_registered_browser.py "$study/blind.csv" "$run_dir/photos" \
  --web "$run_dir/web" --chromium /usr/bin/chromium --out "$run_dir/baseline.jsonl"
python "$study/study.py" score "$run_dir/baseline.jsonl"
```

A wrong product is a registered name returned on an outside package. A wrong order is a registered GTIN authorized for that package. A visible, decoded unregistered barcode identifies an outside item, and a visual match to the outside gallery identifies a look-alike. A hold for a missing or ambiguous panel leaves the actual identity unresolved. The browser ledger preserves the product, order and both visible status messages.

For the final retest, use the static web tree from this study's release. The following commands verify all 19 final reader components before starting the browser.

```sh
python "$study/study.py" check-reader web --phase final
python scripts/evaluate_registered_browser.py "$study/blind.csv" "$run_dir/photos" \
  --web web --chromium /usr/bin/chromium --out "$run_dir/final.jsonl"
python "$study/study.py" score "$run_dir/final.jsonl"
```

The 14-component initial retest, the 16-component thumb-occlusion endpoint and the 17-component pre-family release produced the same complete 16-row ledger (SHA-256 `0480c629c30bd5849cdfa1f97ad1bddbfa72d92f725262297cc167b3e64226dd`). They yielded six supported outside facts and ten unresolved holds. The final 19-component release changed only the 1.75 L capacity observation. [Pre-family ledger](pre-family.jsonl) · [Initial components](side-front-reader.json) · [Thumb-occlusion endpoint](endpoint-reader.json) · [Pre-family release](pre-family-reader.json) · [Final release](final-reader.json) · [Outside-family method and controls](../outside-front-print/native.md)
