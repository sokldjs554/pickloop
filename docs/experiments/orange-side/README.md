# Orange carton side evidence

The helper identifies a carton whose printed front and adjacent side can be verified together. The old Swedish 1 L, Finnish 1 L and Swedish 1.75 L orange cartons share the God Morgon logo, orange title, glass and fruit illustration. Those front features alone leave the SKU unresolved.

Five original Grocery Store Dataset training photographs supply the ingredients and front references (005, 007, 009, 010 and 015). The ingredients helper locates the front and the neighboring multilingual ingredients panel. At least two different original source images must agree on that panel. The builder excludes keypoint windows that overlap the carton seam and omits the bottom barcode area.

A sixth training photograph (019) provides a separate nutrition reference for the printing on that carton. The browser aligns the printed single flavor and the white script below it. It then checks the adjacent face for the two long yellow nutrition-heading lines, the shorter third yellow line and the first white nutrient rows. The reference stores luminance and yellow contrast on a small sampling grid. The bounded pose search runs in the disposable browser worker.

The five previously held archive inputs are development checks. The ingredients helper recovered RR-74b070980c9ca99f. The nutrition helper recovered RR-1f2778ff76b56ea8 and RR-6332c70f6388db64. The two helpers produced no orange identification on 53 further photos, including 14 red-grapefruit archive photos, eight public photos, 20 legacy validation photos, seven field photos and four near-sibling reference controls. Each of the 58 input files has a distinct SHA-256. These numbers describe these specific inputs.

Three additional Open Food Facts photos show actual nutrition panels on one Finnish 1 L and two Swedish 1.75 L cartons. The isolated heading check rejected 945 geometric perturbations of the Finnish photo and 882 of each Swedish photo. Those are three photographs. Each source URL, checksum and printed-region annotation appears in [nutrition-controls.json](nutrition-controls.json).

The 2014 Swedish packaging study shows another 1 L orange carton with a two-line heading and a printed energy value of 180 kJ/45 kcal. Its GTIN is unavailable in the figure. A match to the three-line layout applies to the enrolled printing. The earlier carton documents a limit on using that layout across packaging vintages. [Inga-Lena Bohm Fiederling, *English in Swedish product packages*, Appendix A, PDF p. 30](https://www.diva-portal.org/smash/get/diva2%3A784978/FULLTEXT01.pdf)

## Reproduction

The two enrollment manifests identify original source bytes at the pinned Grocery Store Dataset revision. Place the original JPEGs in one directory and run the following from the repository root, with the project's Python environment available.

```sh
python scripts/build_orange_side.py /path/to/original-jpegs
python scripts/build_orange_nutrition.py /path/to/original-jpegs
node tests/orange-side.mjs
node tests/orange-nutrition.mjs
```

To replay the isolated near-sibling challenge, fetch the three checksum-pinned image URLs from the control manifest into a directory as `<key>.preview.jpg`. Node invokes Pillow to decode each local image.

```sh
node tests/orange-nutrition.mjs /path/to/nutrition-controls
```
