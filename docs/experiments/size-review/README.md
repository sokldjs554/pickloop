# Reading the size of a photographed God Morgon carton

The inspected 33-photo regression set contains six registered cartons and 27 exact unknowns. The old default assigned seven names from package evidence. One was correct. The revised default named one photograph, a Finnish 1 L apple carton whose flavour and quantity matched but whose GTIN differed. It held all four formerly accepted wrong-size products, and it also held the previously correct Swedish orange carton. Neither rule optically confirmed an order SKU among these 33 photos.

| Frozen comparison | Known correct / 6 | Known wrong name / 6 | Known held / 6 | Unknown named / 27 | Unknown held / 27 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Previous package-text name | 1 | 0 | 5 | 6 | 21 |
| With required quantity evidence | 0 | 0 | 6 | 1 | 26 |

The 27 exact unknowns include 18 same-brand alternate-GTIN challenges. Unknown false accepts fell from 22.2% to 3.7% on this set. Known exact-name recall fell from 16.7% to 0%. The photos include repeated views from the same source groups. The six errors were inspected while developing the change, so these figures describe a regression set.

## The six previous false accepts

| Frozen ID | Previous photo name | Package identified by the source | What the revised recognizer found |
| --- | --- | --- | --- |
| NX-128b044de60a6242 | Orange | Finnish 1 L orange, 6415130050490 | Orange remained readable. The angled front yielded no quantity with a unit. Held. |
| NX-2874d2801bee038e | Apple | Finnish 1 L apple, 6415130050506 | Both new lower-front readings say “1 L” beside the printed juice description. The photo name passed. Its market-specific GTIN still makes this an exact false accept. No order identity was confirmed. |
| NX-2eca27540a00d80d | Orange | 1.75 L orange, 7310865074768 | The previous full/front reads missed the quantity. The new neutral-ink reading found “1.75L”. Held for contradictory size. |
| NX-63455b37f6fb074a | Orange | 1.75 L orange, 7310865074768 | An angled carton shows the size low on its front. Neither quantity read recovered a number with a unit. Held for missing evidence. |
| NX-696557e5fb415bd8 | Apple | 1.75 L apple, 7310865081650 | Original OCR read “1.75 JTER” beside “JUICE PARTLY”. The damaged litre spelling can veto a candidate. Held. |
| NX-d152da1019eb25f9 | Orange | 250 ml orange, 6415130089834 | The small front label produced “250 mi” in one reading and broken number/unit fragments in others. The damaged unit vetoed the 1 L candidate. Held. |

On the known orange photo NX-d03141e8696f584c, a cut orange covers part of the numeral at the lower edge of the carton. The original OCR recovered the brand and orange flavour. The new quantity readings yielded “sea —————-” and “a 1 |”. The candidate remains orange and the photo name is held. Five other registered photos were already held.

Seven earlier development photos are separately included in the receipt. Of the six registered photos, the previous reader named six correctly. The revised reader named two correctly and held four. Both readers held the one unknown. The two retained photos contain corroborated 1 L print. An actual CLI run and an in-process HTTP upload returned the same complete JSON readout for GMX-28c6aec5bc49. Uploading NX-d152da1019eb25f9 returned a held photo name and an orange flavour candidate.

## Decision and replay

The normal CLI and upload API expose `flavour_candidate`, `photo_name`, `size_status`, `size_evidence`, `size_readings` and `confirmed_order_sku`. A single registered optical code can name its juice unless visible text conflicts. A text-only name requires corroborated brand/flavour evidence and two OCR passes that each read a quantity equivalent to 1 L. The passes use the same photograph, including two lower-front readings for small print. They verify a printed quantity separately from fruit words. Different package quantities, multipacks and recognized conflicting codes cause a hold. One legible amount without corroboration is reported as `unread`. Other catalogue classes retain their existing naming behaviour. Only the three registered barcodes can confirm an order. Brand, flavour and litre marks alone cannot resolve a same-size market variant.

[results.json](results.json) records all 33 paired rows, the seven development rows, source and model-asset hashes, original image SHA-256, raw OCR, supplemental readings, decoded optical codes, reasons and exact outcomes. Before uses the original sealed package-text ledger's `after.prediction`. After comes from full current inference on the original hash-checked pixels. Truth is joined after current inference. The original archived study and its photographs are described in the [collection record](../new-photos/README.md).

Reconstruct the `new` and `prior` blind manifests and original images using that collection record. With the catalogue dependencies, Tesseract English data and verified model weights available, run from the repository root. Setting `XDG_CACHE_HOME` to the parent of the existing `pickloop/dinov2-04d27f3400d0.safetensors` cache file avoids a download.

```sh
export PYTHONPATH=src OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python scripts/review_photo_sizes.py --photos /path/to/photo-root --out /tmp/size-replay.json
cmp /tmp/size-replay.json docs/experiments/size-review/results.json
python scripts/report_photo_readouts.py --check
```
