# Orange market and capacity lookalikes

The older Swedish and Finnish orange 1 L packages show the same orange title, squeezed-fruit line, glass and fruit artwork. An upload of the original Finnish photo held the Swedish product name. At a 900-pixel long edge and JPEG quality 85, the earlier browser instead named Swedish orange 1 L using 274 matching features. Strong matches also aligned the Finnish 1 L and Swedish 1.75 L references to the same physical face. [Original source labels](sources.csv)

The reader now seeks independent evidence when another catalogued orange variant matches the same face and its aligned artwork nearly ties the proposed match. The allowed appearance difference is 0.01. Across 54 resize, JPEG and small-warp perturbations on the two enrolled Swedish orange fronts, the largest drop in their own artwork agreement was 0.0036. Shared artwork alone leaves the photo name on hold. A matching clean optical identity still resolves, and a conflicting optical identity still holds. [Appearance calibration](appearance-calibration.json) · [Artwork decision](../../../../web/vendor/package-reader/panel-worker.js) · [Browser decision tests](../../../../tests/package-reader.mjs)

A separate Swedish 1.75 L publisher view also produced the Swedish 1 L name after a side mask, reduced brightness and JPEG conversion. The reader picked a generic front after geometry recovery. OCR read its printed capacity as `1751` directly above `JUICE FROM CONCENTRATE`. The updated reader checks for the documented 1.75 L alternative even when that capacity line loses the decimal separator or the final L is read as a one. The check applies to a proposed Swedish orange 1 L visual front with the complete quantity line and the adjacent concentrate statement. [Photo decision](../../../../web/package-reader.js)

Chromium's ordinary file chooser reproduced both wrong names before the changes. Both uploads held the name on the frozen release. Across all 30 derivatives the frozen release returned zero wrong registered names and zero order confirmations. The prior worker named two of the 30; both were wrong Swedish orange 1 L names and both were confirmed through the prior file chooser. [Paired upload records](targeted-uploads.json) · [All derivative outcomes](paired-derivatives.csv) · [Counts and version hashes](summary.json)

| Input | Prior upload | Release upload |
|---|---|---|
| Finnish 1 L, resized and saved as JPEG | Swedish orange 1 L | Held on ambiguous artwork |
| Swedish 1.75 L, side masked and dimmed | Swedish orange 1 L | Held on capacity |

The ordinary file chooser kept the registered Swedish orange name on a known front and on a known adjoining-side view. On 45 source-hash-checked fronts from the registered store archive, the near-tie condition did not divert any prior worker decision. At that checkpoint the full reader named 32 registered fronts correctly. The diagnostic checks the market guard against the same geometric results for each image. The separate release replay measures the whole reader. [Swedish control uploads](targeted-uploads.json) · [Archive front diagnostic](archive-front-market-probe.csv)

## Reproduce

The five source photographs cover three GTINs. Each yielded six bounded variations combining brightness at 1.0 or 0.9, no mask or one of two masks, and resize and JPEG conversion. Multiple images come from the same product and all derivatives retain the acquisition of their original. Four of the five source photos already contributed outside references to the artwork gallery. This challenge measures sensitivity on these known pack images.

Restore the five original files under the names in the source manifest. In a Python environment with Pillow 13.0.0 and Playwright, run from the repository root. [Source manifest](sources.csv)

```sh
script=docs/experiments/market-rival-retry/orange-variants
trial=$(mktemp -d)
python "$script/prepare.py" /path/to/source-files "$trial/derivatives"
python scripts/evaluate_registered_browser.py "$trial/derivatives/manifest.csv" \
  "$trial/derivatives" --web web --chromium /usr/bin/chromium --out "$trial/release.jsonl"
```

The preparation script independently reproduced all 30 frozen derivative hashes with Pillow 13.0.0. The asset hashes, paired observations and upload outcomes document the before and release runs.
