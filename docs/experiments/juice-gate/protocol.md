# Frozen juice verification protocol

The 81-class recognizer and the original Bravo arbiter supply the baseline. The optional juice gate runs only for a named God Morgon Apple, Orange, or Orange–Red Grapefruit candidate. It preserves existing holds and all other candidate decisions. On these three candidates, two corroborating OCR readings may confirm or correct the flavour. Missing, conflicting, unrecognized or ambiguous evidence yields UNKNOWN.

The four registered package-front quadrilaterals come exclusively from fit-role images. The four reference names play no part in the final flavour vote. The fourth (pure red grapefruit) helps locate the shared packaging. A SIFT homography with at least 12 inliers locates the printed face, which is rectified before three English Tesseract readings of the flavour strip. An upright, single carton isolated on a light backdrop is eligible for a fallback with three whole-carton readings and an additional brand-text requirement. All readings use original image pixels. The gate receives no source path, barcode, reference label or order.

Frozen before independent image inference:

* Gate source SHA-256 `9b9c2dca045935d794c1bf291426dd4887b57896d31ad2d09f084a79e525aab5`.
* Four-panel feature gallery SHA-256 `496c81c7de627748b79c7661fa7377d6d5e3a62d2cf0dd09f3e2e3a0050b7aea`.
* Baseline head SHA-256 `55b1af5108cb748b05702f14976a9bee471872730ce5221ad2c9be16a906fcd1`.
* Tesseract 5.5.0 with the English language model. Geometry, thresholds, vocabulary and OCR modes were selected on old official training/development photos only. The 19 previously reported mixed-juice test photos do not participate in selection or independent evaluation.

## Populations and counting

The independent source manifest fixes barcode-confirmed consumer uploads and retail packshots separately from their labels. The evaluation checks original file bytes, decoded RGB identity, and near-duplicates against all 5,502 original Grocery Store Dataset files. It excludes a candidate if it matches a previous or retained evaluation image exactly, or both its 64-bit pHash and dHash are within four bits of the same source. A barcode verified by a source page establishes ground truth; the recognizer never receives it. Different product flavours with their own EAN outside the 81 registered names have truth UNKNOWN.

A separate simulated camera trial uses two deterministically chosen fit-role photographs for each target flavour, one pure red-grapefruit carton (registered class 33), and one invented unregistered carton. The first and middle image in path-sorted order per flavour are used, excluding the four panel-registration shots. Each of the eight textures is captured once front-on, once at 15° tilt, and once with an opaque strip occluding part of the front. This is a check on 24 new camera views with reused reference artwork. Counts for those views must be reported separately from external photos.

For each cohort publish all rows, denominator, correct named, incorrect named, held, and accepted coverage. Also report previously wrong names now held or corrected, previously correct names now held, newly introduced wrong names, and remaining wrong names. The full end-to-end camera/head output controls counting. Outcomes on cases outside the three-candidate route remain in the denominator.
