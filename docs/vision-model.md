# Learned crop recognition

`AppearanceModel.predict()` receives only RGB `uint8` crops. It uses a trained small CNN, a 32-dimensional normalized embedding, and nearest known SKU prototypes. It never receives simulator object IDs, segmentation IDs, material names, SKU truth, or object poses. Depth proposals and position estimation are separate components. Simulation truth is used only to score the development transfer check, never to choose an inference label.

The two known packages share exactly the same red base color. `SKU-RED-A` has one broad white band; `SKU-RED-B` has two thinner white bands with almost the same total white area. Stripe count remains identifiable under rotations. The green package with a white X is unregistered and must return `UNKNOWN`. Original 128×128 textures are in `assets/textures/`; they are agent-authored, dedicated under CC0, and contain no real product images or logos.

## Reproduce

Install project ML/test dependencies in the project environment, then run from the repository root:

```sh
PYTHONPATH=src .venv/bin/python scripts/train_vision.py --epochs 35 > models/training.log 2>&1
# Inspect development data/scene integration, then freeze the artifacts.
PYTHONPATH=src .venv/bin/python scripts/train_vision.py --evaluate-only --final-seed 30000 > models/final_evaluation.log 2>&1
PYTHONPATH=src .venv/bin/python -m pytest
```

The committed weights were actually trained on CPU using Torch 2.7.1+cpu with two threads and training seed 1729. Thirty-five epochs took 18.68 seconds, excluding synthetic image generation and evaluation. No pretrained weights, remote API, or downloaded data are used.

## Data and evaluation integrity

Each sample is a PIL rendering of a square package, randomized by full-angle rotation, quadrilateral distortion, scale, crop padding, background color, brightness, contrast, small occluders, blur, and sensor noise. See `models/validation_contact_sheet.png` for examples.

| Split | Seed identities, per class | Purpose |
|---|---|---|
| Train | 0–599 | 600 A + 600 B, plus 600 auxiliary synthetic outliers |
| Validation | 10000–10119 | 120 each of A, B, and green-X; rejection threshold selection |
| Development | 20000–20119 | Inspected initial and revised model results |
| Frozen final | 30000–30119 | 120 each of A, B, green-X, evaluated after weights/thresholds were frozen |
| Rendered scene development | 0–4 | Actual RGBD depth proposals in MuJoCo; 15 crops |

The initial two-class 30-epoch model was inspected on seeds 20000–20119. Its results motivated auxiliary outlier exposure, so that split was explicitly relabeled **development**. Initial metrics and training logs are retained in `vision_metrics_initial.json` and `training_initial.log`. The final model's development results are retained separately in `vision_metrics_development.json`. A fresh final split was generated only after the final weights and thresholds were fixed. Final checkpoint and TorchScript SHA-256 hashes are recorded in `vision_metrics.json`.

Auxiliary encoder training uses random-color solid packages, 3–6 stripe patterns, and dot patterns. It does not use the green-X motif. Green-X examples **are available for validation threshold calibration**. Thus this is family-specific unknown calibration, not a demonstration of arbitrary open-set rejection. The frozen final benchmark and rendered scene transfer scores below use synthetic inputs. A separate evaluation used 781 real grocery photos, with individual predictions and a protocol for photographing the original A/B targets. [Real-photo evaluation](real-photo-evaluation.md)

## Results

Final raw predictions, distances, embeddings, confusion matrices, all 100 timing samples per runtime, and training history are in `models/vision_metrics.json`. Counts below come from the frozen final split.

| Method | Known accuracy before rejection | Known correct after rejection | Known rejected | Unknown false accepts |
|---|---:|---:|---:|---:|
| CNN + prototypes, eager | 240/240 (100%) | 240/240 (100%) | 0/240 | 0/120 |
| CNN + prototypes, TorchScript | 240/240 (100%) | 240/240 (100%) | 0/240 | 0/120 |
| RGB mean + nearest prototypes | 118/240 (49.17%) | 57/240 (23.75%) | 116/240 | 13/120 (10.83%) |

The color baseline removes spatial information and cannot reliably count stripes. Its distance threshold is independently selected using the same validation unknown family. A correct prediction after rejection counts only an accepted correct known label; wrong known labels and rejection both count against that accuracy.

Actual MuJoCo RGBD scene development seeds 0–4 produced 15/15 correct crop labels across A, B, and unknown. `models/scene_transfer_metrics.json` records each prediction, bbox, distance, and scoring association. This small check verifies the integrated rendering/proposal interface, not broad scene coverage.

## Model, rejection, and deployment

The network has three stride-2 convolutions, adaptive pooling, two fully connected layers, and a 32-D normalized embedding. A three-output auxiliary classifier trains A/B/synthetic-outlier discrimination. Cross entropy uses logit scale 8. At inference the label comes from the closest of the **two known prototypes**, not from the auxiliary class index. A crop is rejected when its Euclidean embedding distance exceeds 1.0832704403. Validation selected a zero minimum prototype margin. `confidence` is the known prototype label's classifier softmax at the training scale; it is an uncalibrated diagnostic, not a safety probability.

```python
import numpy as np
from pickloop.vision_model import AppearanceModel

model = AppearanceModel()  # defaults to repository models/appearance.pt
predictions = model.predict(crops)  # list of HWC uint8 images, or NHWC uint8 array
# Each result: sku, confidence, distance, embedding (32 floats)
```

Preprocessing bilinearly resizes each crop to 64×64, converts RGB to float32 NCHW, and divides by 255. Missing or malformed RGB/uint8 inputs raise errors rather than silently producing a label.

`models/appearance.ts` is a real TorchScript export. It returns `(unscaled_3_class_logits, normalized_embedding)`; prototype distance/rejection logic is in `AppearanceModel`. `appearance_metadata.json` supplies prototypes, thresholds, input contract, and confidence logit scale for other runtimes. No TensorRT artifact or TensorRT speedup is claimed.

| CPU runtime | Batch-1 forward median | p95 | Artifact bytes |
|---|---:|---:|---:|
| Eager | 0.255 ms | 0.317 ms | 192245 |
| TorchScript | 0.206 ms | 0.266 ms | 208346 |

Timings use two CPU threads, ten warmups, and 100 samples; they exclude crop preprocessing, camera rendering, proposals, device I/O, and robot control. Export comparison over all 360 final images found maximum absolute logit and embedding errors of 0 and zero decision disagreements. Results depend on this host and this small model.
