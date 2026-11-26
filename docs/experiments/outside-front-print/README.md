# Can a printed front panel establish an outside product?

The four registered items are plain orange in 250 ml and 1 L, apple in 1 L, and orange/red grapefruit in 1 L. A visible unregistered barcode can settle identity. We tested whether a family name, a clearly incompatible printed volume, or matching supplier artwork could support an outside decision when the original reader held the package. The test outputs never authorize an order. [Registry](../../../web/vendor/package-reader/registry.json) · [Original 16-photo study](../side-unknown-challenge/README.md)

## Front-panel OCR

The frozen rule required a single silhouetted foreground package on a light background, the God Morgon logo and an incompatible complete printed title or supported volume on that same package. It used the browser's existing Tesseract word boxes, rejected ingredients, nutrition and multipack contexts, and distinguished decimal volumes from OCR artifacts. Images and thresholds were locked before this run. The older 16 photographs had been inspected when assessing feasibility. [Rule](outside-print.mjs) · [Synthetic tests](test.mjs) · [Freeze](freeze.json)

| Group | Images | Single foreground package found | Outside calls |
|---|---:|---:|---:|
| Fresh producer and retail photographs with no duplicate flag | 6 | 4 | 0 |
| Additional photographically similar controls | 2 | 0 | 0 |
| Previous near-miss test | 16 | 7 | 0 |
| Archived registered and outside store photographs | 74 | 0 | 0 |

Even the clean studio photographs often lost a logo line, a flavour word, or both. On the archive, the background test rejected every frame before text classification. This result gives little information about false outside calls on a legible store front. [Full results](results.csv) · [Fresh image URLs, identity sources and hashes](fresh-labels.csv) · [Duplicate screening](screening.csv)

## Complete supplier artwork

A second frozen probe registered six packshots extracted from the producer's Swedish 2025 brochure and one Finnish retailer packshot. It estimated a projective map from independently matched keypoints, required a central mostly visible face, and verified two product-title bands plus a separate area of distinctive artwork. The minimum high-pass normalized cross-correlation was 0.60 in each band. Neither the gallery nor its marked regions used a challenge photograph. Individual original URLs, byte digests, PDF object numbers, normalized coordinates and thresholds are recorded. [Registered sources](artwork-enrollment.csv) · [Method freeze](artwork-freeze.json)

Across six new independently sourced Open Food Facts photographs, the 16 historical near misses and 74 archived store photographs, all 96 decisions were holds. The closest new examples were Original Lemonade and Ginger Shot. The first matched both bands of text at 0.967 and 0.955 with 364 geometric inliers, but its fruit-art region scored 0.567. The second reached 0.867 and 0.920 on the text, with 168 inliers, but reached 0.391 in the third region. The published threshold and results include those holds. [Per-image evidence](artwork-results.jsonl) · [Inputs](artwork-inputs.csv) · [Photographic overlap checks](artwork-screen.csv)

## Outside-family experiment

A third probe tested a different claim. A verified complete printed brand and an incompatible named product family can exclude the registered items even when the fruit photograph, marketing copy or exact product code varies. It checked the full logo and each of two printed title regions independently on one foreground plane. The single-citrus series also required its separate Selected line. The Smooth Orange template required the visible 1.75 L declaration. Both geometric support and image correlation were required within every region. It refused strongly landscape scenes, detected repeat copies of the brand beyond the chosen face, and declined an output if two different enrolled families passed. No query coordinate, filename, GTIN or truth was used in inference. [Pixel reader](family_reader.py) · [Supplier sources and regions](family-registrations.json) · [Frozen inputs and source hashes](family-freeze.json)

The six previous Open Food Facts observations were available when the family experiment was designed. Fresh acquisitions were screened against the prior photo inventory and the enrolling references. The independently authored review images included breakfast scenes with multiple visible products and an unrelated brand. Source copies and perceptual matches were kept separate. The same photo appears under two IDs across the historical and flagged groups. [Uncropped source originals](all-family.csv) · [Screening decisions](family-screen.csv) · [Full evaluated population](family-inputs.csv)

The frozen reader made three outside-family calls in 115 rows. It recognized Original Lemonade and Ginger Shot in two of the six previously examined contributor photographs. It also verified Smooth Orange 1.75 L in one of the 16 historical near-misses. On the latter photograph, normalized correlation was 0.975 on the logo, 0.876 on the full printed name and 0.657 on the printed capacity. Five scene controls with multiple visible products, three unrelated or unidentifiable scenes and all 60 registered store photographs produced zero false outside decisions. None of the newly acquired rows yielded an independent positive. This includes the closely matching commercial artwork, which was flagged in duplicate screening. [Ledger and local measurements](family-results.jsonl)

| Evaluation group | Rows | Supported outside-family decisions |
|---|---:|---:|
| Previously examined contributor photographs | 6 | 2 |
| Historical near-misses, including source-similarity controls | 16 | 1 |
| Archived store views of registered cartons | 60 | 0 |
| Archived store views of plain red grapefruit | 14 | 0 |
| Newly acquired, screened field and studio photos | 17 | 0 |
| Additional source-overlap controls | 2 | 0 |

The native implementation and its separate chooser results are documented in the [browser evaluation](native.md).

The studies use supplier and publisher photographs by reference. They do not redistribute the original files or image patches. The manufacturer catalogue documents the names and formulations in each line. [Swedish supplier catalogue](https://a.storyblok.com/f/243238/x/e14cfc3015/eckes_sortimentsbroschyr_2025-v2_high.pdf) · [Finnish supplier catalogue](https://www.eckes-granini.fi/ammattilaiset/tuotekuvasto/eckes-granini-luettelo-09_2021-03_2022.pdf) · [Manufacturer portfolio](https://www.godmorgon.com/products/)
