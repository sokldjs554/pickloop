# Orange carton side evidence

The helper identifies a carton whose printed front and adjacent side can be verified together. The old Swedish 1 L, Finnish 1 L and Swedish 1.75 L orange cartons share the God Morgon logo, orange title, glass and fruit illustration. Those front features alone leave the SKU unresolved.

Five original Grocery Store Dataset training photographs supply the ingredients and front references (005, 007, 009, 010 and 015). The ingredients helper locates the front and the neighboring multilingual ingredients panel. At least two different original source images must agree on that panel. The builder excludes keypoint windows that overlap the carton seam and omits the bottom barcode area.

A sixth training photograph (019) provides a separate nutrition reference for the printing on that carton. The browser aligns the printed single flavor and the white script below it. It then checks the adjacent face for the two long yellow nutrition-heading lines, the shorter third yellow line and the first white nutrient rows. The reference stores luminance and yellow contrast on a small sampling grid. The bounded pose search runs in the disposable browser worker.

The five previously held archive inputs are development checks. The ingredients helper recovered RR-74b070980c9ca99f. The nutrition helper recovered RR-1f2778ff76b56ea8 and RR-6332c70f6388db64. The ingredients and three-line heading helpers produced no orange identification on 53 further photos, including 14 red-grapefruit archive photos, eight public photos, 20 legacy validation photos, seven field photos and four near-sibling reference controls. Each of the 58 input files has a distinct SHA-256. These numbers describe these specific inputs.

When a thumb hides the short heading line, the third check compares four visible printed endings. It requires both yellow lines, both aligned white values, agreement between at least two distinct registered training photographs and a margin over real Finnish 1 L and Swedish 1.75 L labels. The three positive photographs (019, 009 and 014) belong to the same Grocery Store Dataset training collection. This check recovered RR-0ba494a20993f2da. Run on all 118 frozen original browser inputs by itself, it returned the correct registered orange product on that photograph, the two tilted orange photos and RV-6732a659bb1611da. It held the other 114 inputs.

The right-column challenge systematically masked or moved the observed portion of each of three Open Food Facts foil photographs. The tested source was omitted from the comparison gallery each time. All 5,250 pose and masking trials on each of the three source photographs held. These are sensitivity checks on three inputs. The descriptor gallery contains sampled contrast and no source JPEG. The Open Food Facts uploader, original image URL and license for each reference appear in [values-enrollment.json](values-enrollment.json).

The separate three-line heading check used the same photos of one Finnish 1 L and two Swedish 1.75 L cartons. It rejected 945 geometric perturbations of the Finnish photo and 882 of each Swedish photo. Those are three photographs. Each source URL, checksum and printed-region annotation appears in [nutrition-controls.json](nutrition-controls.json).

The 2014 Swedish packaging study shows another 1 L orange carton with a two-line heading and a printed energy value of 180 kJ/45 kcal. Its GTIN is unavailable in the figure. Its right-column component held across 1,050 pose perturbations. A match to the three-line layout applies to the enrolled printing. The earlier carton documents a limit on using that layout across packaging vintages. [Inga-Lena Bohm Fiederling, *English in Swedish product packages*, Appendix A, PDF p. 30](https://www.diva-portal.org/smash/get/diva2%3A784978/FULLTEXT01.pdf)

The browser also replayed six derivatives of three archived orange photos through the public file chooser. All three visual identifications survived JPEG quality 85, and all three survived 0.9 brightness followed by JPEG quality 85. None produced a barcode-confirmed order. The right-column resolver can resolve a conflicting front candidate only when its lower artwork has zero geometric inliers and the same registered front is localized on the same carton. It still requires the complete four-ending proof. All 19 formerly incompatible original scenes stayed held in the separate check.

## Reproduction

The enrollment manifests identify original source bytes at the pinned Grocery Store Dataset revision. Place the original JPEGs in one directory and run the following from the repository root, with the project's Python environment available.

```sh
python scripts/build_orange_side.py /path/to/original-jpegs
python scripts/build_orange_nutrition.py /path/to/original-jpegs
python scripts/build_orange_values.py /path/to/original-jpegs /path/to/nutrition-controls
node tests/orange-values.mjs
node tests/orange-side.mjs
node tests/orange-nutrition.mjs
```

To replay the isolated near-sibling challenge, fetch the three checksum-pinned image URLs from the control manifest into a directory as `<key>.preview.jpg`. Node invokes Pillow to decode each local image.

```sh
node tests/orange-nutrition.mjs /path/to/nutrition-controls
python scripts/validate_orange_value_controls.py /path/to/nutrition-controls
python scripts/validate_orange_value_controls.py /path/to/nutrition-controls --brightness .9 --jpeg-quality 85
```
