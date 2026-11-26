# Classic orange carton, rear view

The browser identified the reviewed rear-facing Swedish God Morgon Orange 1 L carton from its printed roof, broad rear face and adjoining narrow nutrition panel. The barcode reader held. Development included inspecting this photograph and its failure cases, so the result measures regression recovery. The nutrition descriptor comes from an independent training photo, and the reader finds the roof, rear and nutrition regions from image pixels.

| Actual file chooser input | Visible decision | Elapsed time |
| --- | --- | ---: |
| Original store photo | God Morgon Orange 1 L from package print | 66.23 s |
| Genuine Swedish 1.75 L orange consumer photo | Held as an unregistered similar package | 12.54 s |
| Original resaved at JPEG quality 85 | God Morgon Orange 1 L from package print | 52.31 s |
| Original at 90% brightness and JPEG quality 85 | Held | 68.65 s |

Chromium 156.0.8078.79 processed the four inputs in sequence on a four-core shared instance while three other browser replays were running. The darker JPEG retained enough detail to locate the flap, printed title and rear paragraphs. The general OCR engine could not recover the whole flavour word. The two JPEGs derive from one store photo. [Chooser output](chooser.jsonl)

## What identifies the carton

The printed flavour on the folded roof must read exactly “orange” using both red and green image channels in the same rectification. The pinned general English OCR engine runs in single-line mode. It uses its full alphabet. The title on the nutrition face matches a separately registered Swedish training image, including a short third yellow line and the start of the white value rows. The roof word sets the expected direction and position of that title. A yellow carton fold sits immediately above the title. Two separated regions on the broad dark rear must each contain at least six aligned pale text lines. A visible light gap between the faces vetoes the candidate. The supplemental OCR worker starts only after these visual checks pass. The result reports the matched packaging and leaves barcode confirmation empty.

The original scored 0.615 on the nutrition title and showed six and eight aligned print lines. An early version which searched freely around the roof text incorrectly accepted two genuine Swedish 1.75 L fronts. On both, it treated vertical front graphics as horizontal nutrition print. Enforcing the adjoining-face geometry removed those matches. The final rule also requires visible broad rear print and rejects a pale divider between the sampled faces.

The independent nutrition source is official GroceryStoreDataset training photo 019. The 2014 Stockholm University study *English in Swedish product packages* by Inga-Lena Bohm Fiederling separately shows the Swedish classic orange, mixed, standalone red grapefruit and apple cartons across physical PDF pages 30 and 31. The orange front displays one litre. The broad rear shows multilingual white paragraphs under a yellow headline, and the narrow side shows nutrition. Flavour lettering and line breaks differ between the 2014 carton and the reviewed store photo. The study corroborates physical layout and flavour wording. The archive class record supplies the SKU association. The source ledger provides original links and hashes. [Nutrition enrollment](../orange-side/) · [University source](https://www.diva-portal.org/smash/get/diva2%3A784978/FULLTEXT01.pdf) · [PDF and embedded-photo hashes](audit.json)

## Controls and reproduction

The supplemental verifier was exercised on 35 distinct original controls, including the Finnish orange 1 L front and nutrition panel, Swedish orange 1.75 L fronts, ingredients and nutrition, standalone red grapefruit, mixed cartons and other products. All 35 produced an empty rear-print result. The controls include public product photos and archived images. The manifests provide URLs and hashes. [Original inputs](inputs.csv) · [Frozen verifier outputs](verifier.jsonl)

Eight edits of the reviewed store photo test specific evidence. Four covered the roof word, the fold, the broad rear copy or the nutrition panel. Three replaced the nutrition face with photographed Finnish 1 L, Swedish 1.75 L or standalone red grapefruit print. The eighth inserted a pale gap between the two faces. All eight held in the frozen verifier. The coordinates in the generator specify test edits only. [Control hashes](controls.csv) · [Generator](make_controls.py)

To replay, place the source photos in one directory using the IDs in the original-input manifest as filenames. For the red-grapefruit replacement, also supply official GroceryStoreDataset training photo 021 for that flavour. The scripts check file hashes, launch the installed Chromium, and load the same OpenCV, nutrition reference, English OCR and verifier as the site.

```sh
python docs/experiments/orange-rear-print/replay.py /tmp/rear-photos /tmp/rear-outputs.jsonl
python docs/experiments/orange-rear-print/make_controls.py /tmp/rear-photos /tmp/rear-controls
python docs/experiments/orange-rear-print/replay.py /tmp/rear-controls /tmp/rear-control-outputs.jsonl \
  --manifest docs/experiments/orange-rear-print/controls.csv
python docs/experiments/orange-rear-print/check_cancel.py /tmp/rear-photos/RR-398059de4d64a316
node --test tests/orange-rear.mjs
```

For a full file-chooser replay use `scripts/evaluate_registered_browser.py` with the same original or control manifest and photo directory. Cancelling the uploader while its supplemental English OCR worker was active hid the result. Chromium reported zero surviving workers out of four observed. The 35-photo test measures unwanted orange-rear matches. The full reader may correctly identify another registered product by its barcode or front. The additional evidence path has one reviewed positive camera photo. The wider release evaluation and genuinely new photographs address different questions.
