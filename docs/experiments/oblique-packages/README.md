# Recognition from the side of a carton

**Python** correctly named 6/15 side-visible cartons, compared with 2/15 in the shipped version. The same comparison on front views was 33/45 → 33/45. The 14 plain-red-grapefruit controls received a registered 1 L name on 0 → 0 frames.

**Chromium upload** correctly named 3/15 side-visible cartons, compared with 1/15 in the shipped version. The same comparison on front views was 29/45 → 29/45. The 14 plain-red-grapefruit controls received a registered 1 L name on 1 → 0 frames.

All 15 side-visible positives come from a previously scored store archive. The Python developer examined archived side failures and used them to choose the query stretch. Both runtime comparisons on that archive are development or regression measurements. The primary group includes several angles of the same apparent carton or shelf setting. **There were zero verified new registered-positive acquisitions.** [Protocol](protocol.md) · [Acquisition and source review](sourcing.md)

## What changed in the reader

The Python fallback stretches a foreshortened upright face horizontally, matches SIFT descriptors in a foreground region, and checks the flavour lettering and fruit artwork on known fronts. For the enrolled orange ingredient side it also verifies the projected orange illustration below the panel. The browser estimates the visible panel boundary, rectifies its pixels, and detects ORB features again. The second geometric estimate must agree with the original panel location. Registered barcode confirmation remains a separate decision.

On the public example a shopper holds an orange carton with its ingredients facing the camera. The original browser held it and the original Python catalogue named milk. The shipped example reads the original unmodified file through the normal upload pipeline. [Photograph and licence](https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/test/Packages/Juice/God-Morgon-Orange-Juice/God-Morgon-Orange-Juice_016.jpg)

## Paired outcomes

A single number means both versions gave that count. An arrow runs from the shipped decision to the frozen candidate. Holds require a completed decision. The table counts frames. The 12-frame exclusion is a sensitivity check and overlaps the primary rows. The broader catalogue correctly named three archived plain-red-grapefruit controls in Python. The browser offers the three registered names. [All individual decisions](paired.csv) · [Machine-readable counts, including order decisions](scores.json)

### Python

| Cohort | Frames | Correct registered | Held | Wrong registered | Wrong broader name | Correct broader name | Timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| Archive registered, side visible | 15 | 2 → 6 | 12 → 9 | 0 | 1 → 0 | 0 | 0 |
| Archive registered sides, excluding three flagged settings | 12 | 2 → 6 | 9 → 6 | 0 | 1 → 0 | 0 | 0 |
| Archive registered, front | 45 | 33 | 11 | 0 | 1 | 0 | 0 |
| Archive registered, all views | 60 | 35 → 39 | 23 → 20 | 0 | 2 → 1 | 0 | 0 |
| Archive plain-red-grapefruit controls | 14 | 0 | 11 | 0 | 0 | 3 | 0 |
| Public apple retests | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Public same-brand controls | 6 | 0 | 6 | 0 | 0 | 0 | 0 |
| Legacy validation registered | 16 | 6 | 10 | 0 | 0 | 0 | 0 |
| Legacy validation controls | 4 | 0 | 3 | 0 | 0 | 1 | 0 |
| New side/reverse controls | 3 | 0 | 3 | 0 | 0 | 0 | 0 |

Across the 15 registered side views, 4 shifted into a correct name and 0 lost a previously correct name.

| Changed side-visible frame | Target | Shipped name | Candidate name |
|---|---|---|---|
| RR-1c1342cb3f7d7971 | orange red grapefruit | hold | orange red grapefruit |
| RR-787b9393075dd1b4 | orange | arla medium fat milk | orange |
| RR-9cac7218a35680ac | orange | hold | orange |
| RR-d706eb3775e71293 | orange red grapefruit | hold | orange red grapefruit |

### Chromium upload

| Cohort | Frames | Correct registered | Held | Wrong registered | Wrong broader name | Correct broader name | Timeout |
|---|---:|---:|---:|---:|---:|---:|---:|
| Archive registered, side visible | 15 | 1 → 3 | 14 → 12 | 0 | 0 | 0 | 0 |
| Archive registered sides, excluding three flagged settings | 12 | 1 → 3 | 11 → 9 | 0 | 0 | 0 | 0 |
| Archive registered, front | 45 | 29 | 16 | 0 | 0 | 0 | 0 |
| Archive registered, all views | 60 | 30 → 32 | 30 → 28 | 0 | 0 | 0 | 0 |
| Archive plain-red-grapefruit controls | 14 | 0 | 13 → 14 | 1 → 0 | 0 | 0 | 0 |
| Public apple retests | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Public same-brand controls | 6 | 0 | 6 | 0 | 0 | 0 | 0 |
| Legacy validation registered | 16 | 6 → 7 | 10 → 9 | 0 | 0 | 0 | 0 |
| Legacy validation controls | 4 | 0 | 4 | 0 | 0 | 0 | 0 |
| New side/reverse controls | 3 | 0 | 3 → 2 | 0 | 0 | 0 | 0 → 1 |

Across the 15 registered side views, 2 shifted into a correct name and 0 lost a previously correct name.

| Changed side-visible frame | Target | Shipped name | Candidate name |
|---|---|---|---|
| RR-787b9393075dd1b4 | orange | hold | orange |
| RR-9cac7218a35680ac | orange | hold | orange |

The Python side counts by flavour were apple 1/2 → 1/2, orange 1/8 → 3/8 and orange/red grapefruit 0/5 → 2/5. Chromium scored 0/2 → 0/2, 1/8 → 3/8 and 0/5 → 0/5 respectively. The earlier rejected nine-reference Python expansion had achieved 3/15 sides and 37/45 fronts, while naming one of the 14 plain-red controls as registered. [Earlier candidate and rejection](../registered-recall/production.md)

## New photographs and operating time

Three newly sourced whole-panel photographs show two separate same-brand controls. Two angles show the same organic orange carton, and one shows a Fruit Crush carton. Both shipped readers and the new Python reader held all three. On its first run with concurrent jobs, the Chromium candidate held two and reached its 120-second application deadline on the Fruit Crush image (2.4 MB). The replay did not capture a completed identity or order for this attempt. [Input sources, product records and groups](supplemental-labels.csv) · [Chromium first attempts](supplemental-browser.jsonl)

Replaying the identical Fruit Crush bytes in a quiet Chromium process produced a completed hold and no barcode-confirmed order. The first-attempt timeout remains in the paired table. [Unchanged-input retry](supplemental-browser-retry.jsonl)

Four deterministic archive inputs were measured sequentially after the full recognition jobs ended. The host used an AMD EPYC 9V74 with a four-core cgroup CPU quota, CPU inference and Chromium 156.0.8078.79. Python measured ordinary recognition after warm-up from decoded RGB. The Chromium measurement includes launching a fresh local server and browser, loading assets, choosing a file, and shutting down. Each case ran once per version. The median summarizes these four inputs only.

| Runtime | Shipped median | Candidate median |
|---|---:|---:|
| Python | 2.89 s | 3.40 s |
| Browser | 5.28 s | 8.42 s |

[Python baseline](latency-python-baseline.json) · [Python candidate](latency-python-candidate.json) · [Browser baseline](latency-browser-baseline.json) · [Browser candidate](latency-browser-candidate.json)

The two public positives represent an enrolled composition and a retest that had motivated a printed-volume rule. The 20 older validation photos had also appeared in earlier catalogue work. No completed strict order was recorded in the main archive, public or legacy cohorts.

[Reproduction commands and package requirements](reproduce.md) · [Model freezes](candidate-models.json) · [Source inventories](../registered-recall/README.md)
