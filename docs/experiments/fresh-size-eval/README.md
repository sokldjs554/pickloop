# Fresh package-size photographs

The former Python recognizer named two different orange cartons as the Swedish God Morgon Orange 1 L order product. The revised recognizer held both and retained orange as a flavour candidate. The cartons were the 250 mL demo product and a Finnish 1 L product with another GTIN. A reader can see the volume on both fronts. The revised OCR reported `unread` for both, so these holds show a reduction in false names. They give no evidence that the model can reliably read the printed volumes.

The final set contained 10 fresh photos from seven GTINs. Both versions missed the one photo of a registered Python order product, a slightly blurred Swedish 1 L orange nutrition panel. The revised recognizer mistook nutrition-table amounts for contrary pack-size evidence, recording `100 ml` and `180 ml`. The three development photos from three other GTINs yielded three holds with both revisions. These small, purposively selected sets do not establish general recognition accuracy.

| Final photos | Registry members | Correct names | Wrong names | Holds | Held registry members | Held outside registry |
|---|---:|---:|---:|---:|---:|---:|
| Python ordinary, before | 1/10 | 0 | 2 | 8/10 | 1/1 | 7/9 |
| Python ordinary, revised | 1/10 | 0 | 0 | 10/10 | 1/1 | 9/9 |
| Python strict order, before | 1/10 | 0 | 0 | 10/10 | 1/1 | 9/9 |
| Python strict order, revised | 1/10 | 0 | 0 | 10/10 | 1/1 | 9/9 |
| Browser barcode worker | 2/10 | 0 | 0 | 10/10 | 2/2 | 8/8 |

The browser registered the 250 mL GTIN in addition to the three 1 L order products. Two final photos exposed a printed barcode on different unregistered Carrefour juices. The browser read the correct GTIN on **2/2** and held both as unregistered. The other eight photos yielded empty barcode reads. No fresh barcode-facing photo of a registered product survived sourcing. Fresh registered barcode sensitivity therefore has denominator zero. Earlier demo examples retain their earlier role.

| Final photo condition | Photos | Python holds before | Python holds after | Browser holds |
|---|---:|---:|---:|---:|
| Barcode visible | 2 | 2/2 | 2/2 | 2/2 |
| Barcode outside view | 8 | 6/8 | 8/8 | 8/8 |
| Pack volume visible to curator | 7 | 5/7 | 7/7 | 7/7 |
| Pack volume obscured | 3 | 3/3 | 3/3 | 3/3 |
| Visible glare on package | 2 | 2/2 | 2/2 | 2/2 |
| Visibly soft/blurred image | 1 | 1/1 | 1/1 | 1/1 |
| 250 mL | 1 | 0/1 | 1/1 | 1/1 |
| 1 L | 8 | 7/8 | 8/8 | 8/8 |
| 1.75 L | 1 | 1/1 | 1/1 | 1/1 |

Conditions overlap. Both glare views belong to one carton GTIN. The two visible-barcode views provide unregistered controls only. The set lacks a fresh visible-front Swedish registered 1 L orange photo, a registered 1 L blend, and controlled same-carton sequences at multiple blur or glare levels. The two Kesko supplier fronts provide a same-flavour size comparison with different market GTINs. Source records establish exact identities even if glare, crop, or the nutrition panel hides all discriminating evidence.

## Selection and provenance

A curator selected photographs and labelled exact SKU, volume, view, visible bars, glare and blur before running either recognizer. All exposures of a GTIN stayed in the same split. Both related Kesko listings stayed in final. Other pairs show two views of one GTIN and do not establish independent physical packages. Development includes fresh views of products photographed in earlier studies. The two fresh development reverse panels have adjacent OFF uploads or related historical source candidates. The registered final reverse was uploaded six months after the earlier front. The raw ledgers have complete outputs on every frozen ID. No model input includes a source URL, filename, GTIN field or label. Printed codes remain part of the actual photo.

The pre-inference screening used the existing whole-image and background-trimmed pHash/dHash, byte and oriented-pixel checks against 5,502 official GroceryStore images, seven prior external images, all 35 earlier juice candidates, 16 produce controls, two earlier rescans, three Korean package photos and other fresh candidates. The paired perceptual cutoff was at most eight bits on both hashes. Manual inspection also excluded probable old crops or supplier reproductions even when their distance exceeded the cutoff. A supplementary audit against 392 further outside/produce reference files found zero duplicate candidates after the batch. The archive checksum and selected-image nearest-neighbour distances appear in the [screening record](screening.csv).

Two retail listings served the same previous Swedish orange front, and a Joker upload reproduced an older original. The manufacturer 2026 brochure repeated the earlier orange studio scene. Other registered blend uploads appeared to show the same carton and panel from an earlier session. The earlier 250 mL barcode view and its derivatives were excluded. A second Kesko 250 mL apple supplier image was excluded to keep the sibling packshot collection in one split. Open Food Facts is a hosting platform with many contributors. An upload date is recorded only as an upload date. Original pixels remain at their linked sources and the package photos retain their publisher rights. [Originals, GTIN references, licences and hashes](labels.csv)

## Verify or repeat

The source protocol, blind input IDs, labels and model dependencies were sealed before inference. The three result ledgers were sealed before joining against truth. A second retrieval returned all 13 matching photo hashes. A second execution reproduced all three raw ledgers byte-for-byte, including Chromium reads on the refetched originals. The independent reduction reproduced rows.csv, metrics.json and public-summary.json. The summary counts can be reconstructed without model weights or downloading photos.

```sh
python scripts/score_fresh_size.py --out /tmp/size-rescore
diff docs/experiments/fresh-size-eval/public-summary.json /tmp/size-rescore/public-summary.json
diff docs/experiments/fresh-size-eval/rows.csv /tmp/size-rescore/rows.csv
```

For a full rerun, install the project's catalogue extra, Tesseract with English language data, and Playwright with Chromium. Execute from the repository root. Choose an empty working directory. The Python runner uses the normal `recognize_rgb` entry point in ordinary and strict modes on the same EXIF-oriented source pixels. Its DINO download verifies the published weight hash. The browser runner opens the actual file-upload form, observes its disposable worker reply, and records the visible Korean result. The scorer checks ID population and ordering, per-file hashes and split isolation.

```sh
study_run=$(mktemp -d)
mkdir "$study_run/before-src"
git archive 8db3040dc546b9b0e5dd08ad6cd3449de53187e6 src | tar -x -C "$study_run/before-src"
python scripts/evaluate_fresh_size.py fetch "$study_run/photos"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_THREAD_LIMIT=1
PYTHONPATH="$study_run/before-src/src" python scripts/evaluate_fresh_size.py python "$study_run/photos" --out "$study_run/python-before.jsonl"
PYTHONPATH=src python scripts/evaluate_fresh_size.py python "$study_run/photos" --out "$study_run/python-after.jsonl"
python scripts/evaluate_fresh_size.py browser "$study_run/photos" --out "$study_run/browser.jsonl"
python scripts/score_fresh_size.py --ledgers "$study_run" --seal
python scripts/score_fresh_size.py --ledgers "$study_run" --out "$study_run/score"
```

Supply `--chromium /path/to/chromium` when using a system browser. The revised source file hashes allow a later checkout to be checked against the assessed version. The fetcher verifies every original byte and fails on publisher drift. Codex ran this experiment on 2026-11-25. [Frozen labels](freeze.json) · [Model and worker hashes](model-freeze.json) · [Environment](environment.json) · [Raw before](python-before.jsonl) · [Raw after](python-after.jsonl) · [Raw browser](browser.jsonl) · [Per-photo outcomes](rows.csv) · [All metric strata](metrics.json)
