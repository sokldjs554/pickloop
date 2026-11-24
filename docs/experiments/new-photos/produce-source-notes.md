# Independent ordinary-produce exploratory control

Collected 2026-11-24 UTC. This is a **separate exploratory control**, never a supplement to the juice primary sample and not a representative grocery-product benchmark. Existing public photographs were newly assembled for this evaluation; they were not newly captured in 2026.

Sixteen source images: four each Banana, Cucumber, Pineapple and Strawberry. The first three map exactly to broad registered catalogue names. Strawberry is absent from all 81 registered names and receives UNKNOWN. No apple/pear/tomato cultivar or firmness subtype was guessed. Broccoli, considered up front, was dropped wholesale before inference because only two of 19 sorted candidates met raw/unambiguous eligibility; no partial class is reported. Cauliflower was replaced before pixel fetching because the official boxable label table does not contain it.

## Primary provenance

- Official dataset documentation: https://storage.googleapis.com/openimages/web/download_v7.html
- Official class names: https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv
- Official human bbox annotations: https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv
- Official attribution metadata: https://storage.googleapis.com/openimages/2018_04/validation/validation-images-with-rotation.csv
- Pixel delivery mirror documented by Open Images/CVDF: https://github.com/cvdfoundation/open-images-dataset
- Each image's exact delivery URL, original Flickr photo page, original image URL, CC BY 2.0 licence URL, photographer/profile and title are retained in labels.csv. The licence basis is the official per-image metadata; original photographers were not contacted and current Flickr licensing was not independently re-audited.

Source files are retained under source/. The stored Open Images release/split is validation with v5 bbox annotations, not a claimed new dataset release. Foundation encoder web-pretraining overlap is unknown. Independence here means a separately assembled source cohort outside the application's Grocery Store Dataset catalogue/gallery source, not proof that a foundation model has never seen any photograph.

## Selection and labels without model output

selection-plan.json was written before pixel downloads and model evaluation. Candidates were ordered by ImageID, required human boxes with IsDepiction=0, IsInside=0 and at least one target box area >=0.08. Up to the first 30 IDs/class were fetched; human source-label quality review then excluded prepared meals/desserts/preserves, mixed ambiguous targets and obvious annotation errors. Open Images cucumber candidates frequently depicted zucchini; a strawberry candidate depicted raspberries. These were excluded for semantic eligibility, independent of model scores. eligibility-review.json lists decisions for every candidate examined through each class's stopping point and the complete omitted broccoli class.

Selected the first four eligible photographs per retained class. Each is a distinct Flickr source group and each class has four different photographers. No prediction model was instantiated and no scores/recognizer outputs were consulted. NPZ keys, dtypes and names were inspected solely to verify registration; learned vector values were not consulted for selection. The freeze preceded evaluator handoff.

All selected images show physical food, with original full image extents. Three are fruit-on-plant context photographs rather than market/shelf views; one is a physical halved cucumber. Those conditions are stated per row. These context differences limit grocery-shelf generalization. No generated render, montage, synthetic pattern or computational crop enters this cohort.

## Pixels, deduplication and freeze

Downloaded source JPEGs are retained under candidates/. Inference images are full RGB decoding of the delivered JPEG saved as metadata-free lossless PNG, with opaque filenames and deterministically shuffled row order. There is no crop, rotation, resize, color augmentation or JPEG recompression in our preparation. Open Images/CVDF's supplied source copies themselves have at most 1024-pixel long edges; we make no claim they are the photographer's original resolution.

blind.csv contains only id,path,sha256. labels.csv contains truth and provenance, joined after prediction. All 16 source-byte SHA-256 and all 16 decoded-pixel SHA-256 hashes are unique. Pairwise 64-bit dHash distances have minimum 22, above the predeclared <=6 duplicate-review trigger. This catches exact/obvious near duplicates; it cannot prove all images depict distinct physical fruit instances. Source_group is the original Open Images image ID; repeated views of one source would stay one group (none are used here).

freeze.json records the manifest hashes and freeze time. There were no inference outputs available at freeze. The main evaluator may score this cohort afterward, retaining the exploratory-control designation and reporting known/unknown denominators separately from juice primary and stress sets.
