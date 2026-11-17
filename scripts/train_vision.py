#!/usr/bin/env python3
"""Reproducible, entirely synthetic CPU training and isolated final evaluation."""
import argparse
import json
import hashlib
from pathlib import Path
import time
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
import torch
from torch import nn
import torch.nn.functional as F
from pickloop.vision_model import CropEncoder, KNOWN_SKUS, crops_to_tensor

ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / 'assets' / 'textures'


def make_texture(kind, rng=None):
    image = Image.new('RGB', (128, 128), (190, 27, 35) if kind < 2 else (28, 160, 54))
    draw = ImageDraw.Draw(image)
    if kind == 0:
        draw.rectangle((0, 49, 127, 78), fill=(242, 242, 234))
    elif kind == 1:
        draw.rectangle((0, 31, 127, 46), fill=(242, 242, 234))
        draw.rectangle((0, 81, 127, 96), fill=(242, 242, 234))
    elif kind == 2:
        draw.line((16, 16, 111, 111), fill=(242, 242, 234), width=22)
        draw.line((111, 16, 16, 111), fill=(242, 242, 234), width=22)
    else:
        # Auxiliary outlier exposure: random solid/3..6 stripe/dot patterns,
        # never the held-out green-X motif.
        if rng is None:
            rng = np.random.default_rng(0)
        image = Image.new('RGB', (128, 128), tuple(int(x) for x in rng.integers(20, 210, 3)))
        draw = ImageDraw.Draw(image)
        motif = int(rng.integers(0, 3))
        if motif == 1:
            count = int(rng.integers(3, 7))
            for y in np.linspace(10, 112, count):
                draw.rectangle((0, int(y), 127, int(y) + 6), fill=(242, 242, 234))
        elif motif == 2:
            for x, y in rng.integers(10, 105, (9, 2)):
                draw.ellipse((int(x), int(y), int(x) + 14, int(y) + 14), fill=(242, 242, 234))
    return image


def synthetic_crop(seed, kind):
    """Randomized texture pose, perspective, crop padding, light, and occlusion.

    Seed identities are disjoint across splits; each kind uses its own RNG stream.
    """
    rng = np.random.default_rng(seed * 13 + kind * 1000003)
    size = 96
    background = tuple(int(x) for x in rng.integers(30, 115, 3))
    canvas = Image.new('RGB', (size, size), background)
    texture = make_texture(kind, rng).convert('RGBA')
    # Perspective perturbation followed by arbitrary rotation. Counting stripes
    # identifies the known classes even after a 90-degree image rotation.
    jitter = rng.uniform(-10, 10, (4, 2))
    corners = np.array([[0, 0], [0, 127], [127, 127], [127, 0]]) + jitter
    texture = texture.transform((128, 128), Image.Transform.QUAD, tuple(corners.ravel()), Image.Resampling.BILINEAR)
    texture = texture.rotate(float(rng.uniform(-180, 180)), resample=Image.Resampling.BILINEAR, expand=True)
    width = int(rng.integers(62, 88))
    height = int(width * rng.uniform(.8, 1.14))
    texture.thumbnail((width, height), Image.Resampling.BILINEAR)
    x = int((size - texture.width) / 2 + rng.integers(-4, 5))
    y = int((size - texture.height) / 2 + rng.integers(-4, 5))
    canvas.paste(texture, (x, y), texture)
    if rng.random() < .2:
        draw = ImageDraw.Draw(canvas)
        x0, y0 = rng.integers(15, 65, 2)
        draw.rectangle((int(x0), int(y0), int(x0 + rng.integers(5, 15)), int(y0 + rng.integers(5, 15))), fill=background)
    canvas = ImageEnhance.Brightness(canvas).enhance(float(rng.uniform(.65, 1.3)))
    canvas = ImageEnhance.Contrast(canvas).enhance(float(rng.uniform(.8, 1.2)))
    if rng.random() < .25:
        canvas = canvas.filter(ImageFilter.GaussianBlur(float(rng.uniform(.2, .65))))
    pixels = np.asarray(canvas).astype(np.float32)
    pixels += rng.normal(0, 2, pixels.shape)
    return np.clip(pixels, 0, 255).astype(np.uint8)


def dataset(start, count, kinds=(0, 1)):
    crops, labels = [], []
    for kind in kinds:
        for seed in range(start, start + count):
            crops.append(synthetic_crop(seed, kind))
            labels.append(min(kind, 2))
    return crops_to_tensor(crops), torch.tensor(labels)


def color_features(images):
    # Spatial information removed: cannot count the identical-color motifs.
    return images.mean(dim=(2, 3))


def get_distances(network, images, prototypes):
    with torch.inference_mode():
        logits, embeddings = network(images)
        distances = torch.cdist(embeddings, prototypes)
    return logits, embeddings, distances


def decide(distances, threshold, margin):
    values, labels = distances.sort(dim=1)
    return torch.where((values[:, 0] <= threshold) & ((values[:, 1] - values[:, 0]) >= margin), labels[:, 0], -1)


def summarize(prediction, labels):
    known = labels < 2
    unknown = ~known
    return {'known_accuracy': float((prediction[known] == labels[known]).float().mean()),
            'known_reject_rate': float((prediction[known] == -1).float().mean()),
            'unknown_false_accept_rate': float((prediction[unknown] != -1).float().mean()),
            'known_count': int(known.sum()), 'unknown_count': int(unknown.sum()),
            'confusion_rows_true_A_B_UNKNOWN_cols_pred_A_B_UNKNOWN':
                [[int(((labels == true) & (prediction == pred)).sum()) for pred in (0, 1, -1)] for true in (0, 1, 2)]}


def latency(function, images, repeats=100):
    for _ in range(10):
        function(images)
    samples = []
    for _ in range(repeats):
        before = time.perf_counter_ns()
        function(images)
        samples.append((time.perf_counter_ns() - before) / 1e6)
    return {'median_ms': float(np.median(samples)), 'p95_ms': float(np.percentile(samples, 95)), 'samples': samples}



def evaluate_frozen(final_seed):
    """Evaluate a saved model without selecting weights or rejection thresholds."""
    from pickloop.vision_model import AppearanceModel
    torch.set_num_threads(2)
    output = ROOT / 'models'
    model = AppearanceModel()
    exported = torch.jit.load(str(output / 'appearance.ts'), map_location='cpu').eval()
    previous = json.loads((output / 'vision_metrics_development.json').read_text())
    test, labels = dataset(final_seed, 120, (0, 1, 2))
    logits, embeddings, distances = get_distances(model.network, test, model.prototypes)
    exported_logits, exported_embeddings, exported_distances = get_distances(exported, test, model.prototypes)
    prediction = decide(distances, model.distance_threshold, model.margin_threshold)
    script_prediction = decide(exported_distances, model.distance_threshold, model.margin_threshold)
    train, train_labels = dataset(0, 600)
    features = color_features(train)
    prototypes = torch.stack([features[train_labels == kind].mean(0) for kind in range(2)])
    baseline_distances = torch.cdist(color_features(test), prototypes)
    baseline_prediction = decide(baseline_distances, previous['baseline_distance_threshold'], 0.)
    previous['status'] = 'frozen_final_evaluation'
    previous['data']['development_seed_range'] = [20000, 20119]
    previous['data']['final_test_seed_range'] = [final_seed, final_seed + 119]
    previous['data']['selection_history'] = [
        'Initial 30-epoch two-class model inspected on seeds 20000..20119; these are development, not untouched final.',
        'Added auxiliary random-pattern outlier exposure, 35 epochs; thresholds selected on validation seeds 10000..10119.',
        'Frozen model and thresholds then evaluated once on final seeds recorded above; scene development uses seeds 0..99.'
    ]
    previous['eager'] = summarize(prediction, labels)
    previous['torchscript'] = summarize(script_prediction, labels)
    previous['baseline_color_mean'] = summarize(baseline_prediction, labels)
    previous['eager']['closed_known_accuracy_before_rejection'] = float((distances[:240].argmin(1) == labels[:240]).float().mean())
    previous['baseline_color_mean']['closed_known_accuracy_before_rejection'] = float((baseline_distances[:240].argmin(1) == labels[:240]).float().mean())
    previous['export'].update({
        'max_abs_logit_error': float((logits - exported_logits).abs().max()),
        'max_abs_embedding_error': float((embeddings - exported_embeddings).abs().max()),
        'prediction_disagreements': int((prediction != script_prediction).sum()),
        'checkpoint_sha256': hashlib.sha256((output / 'appearance.pt').read_bytes()).hexdigest(),
        'torchscript_sha256': hashlib.sha256((output / 'appearance.ts').read_bytes()).hexdigest(),
    })
    with torch.inference_mode():
        previous['latency']['eager'] = latency(model.network, test[:1])
        previous['latency']['torchscript'] = latency(exported, test[:1])
    previous['raw_final_predictions'] = [
        {'seed': final_seed + i % 120, 'truth': int(labels[i]), 'prediction': int(prediction[i]),
         'baseline_prediction': int(baseline_prediction[i]), 'distances': distances[i].tolist(),
         'embedding': embeddings[i].tolist()} for i in range(len(test))
    ]
    (output / 'vision_metrics.json').write_text(json.dumps(previous, indent=2) + '\n')
    print(json.dumps({key: previous[key] for key in ('eager', 'baseline_color_mean', 'export')}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=35)
    parser.add_argument('--evaluate-only', action='store_true')
    parser.add_argument('--final-seed', type=int, default=30000)
    args = parser.parse_args()
    if args.evaluate_only:
        evaluate_frozen(args.final_seed)
        return
    torch.set_num_threads(2)
    torch.manual_seed(1729)
    np.random.seed(1729)
    TEXTURES.mkdir(parents=True, exist_ok=True)
    for kind, name in enumerate(('red_a', 'red_b', 'unknown')):
        make_texture(kind).save(TEXTURES / (name + '.png'))
    (TEXTURES / 'LICENSE.txt').write_text('Synthetic package textures authored for PickLoop. CC0 1.0 Universal public domain dedication. No third-party product images or marks.\n')
    train, train_labels = dataset(0, 600, (0, 1, 3))
    validation, validation_labels = dataset(10000, 120, (0, 1, 2))
    network = CropEncoder()
    optimizer = torch.optim.Adam(network.parameters(), lr=.002)
    history = []
    start = time.perf_counter()
    for epoch in range(args.epochs):
        network.train()
        order = torch.randperm(len(train))
        total = 0.
        for indices in order.split(64):
            logits, embeddings = network(train[indices])
            loss = F.cross_entropy(logits * 8, train_labels[indices])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += float(loss.detach()) * len(indices)
        network.eval()
        with torch.inference_mode():
            _, embeddings = network(train)
            prototypes = F.normalize(torch.stack([embeddings[train_labels == kind].mean(0) for kind in range(2)]), dim=1)
            _, _, validation_distances = get_distances(network, validation, prototypes)
        prediction = validation_distances.argmin(dim=1)
        accuracy = float((prediction[:240] == validation_labels[:240]).float().mean())
        history.append({'epoch': epoch + 1, 'loss': total / len(train), 'validation_closed_known_accuracy': accuracy})
        print(json.dumps(history[-1]), flush=True)
    training_seconds = time.perf_counter() - start
    # Select rejection using validation only; final test is generated afterwards.
    best = None
    for threshold in np.linspace(.02, 1.6, 160):
        for margin in np.linspace(0, 1.0, 31):
            prediction = decide(validation_distances, float(threshold), float(margin))
            known_acc = float((prediction[:240] == validation_labels[:240]).float().mean())
            unknown_reject = float((prediction[240:] == -1).float().mean())
            score = .5 * (known_acc + unknown_reject)
            if best is None or score > best[0]:
                best = (score, float(threshold), float(margin))
    _, threshold, margin = best
    output = ROOT / 'models'
    output.mkdir(exist_ok=True)
    checkpoint = {'state_dict': network.state_dict(), 'prototypes': prototypes,
                  'distance_threshold': threshold, 'margin_threshold': margin,
                  'skus': list(KNOWN_SKUS), 'training_seed': 1729,
                  'input_size': 64, 'synthetic_only': True}
    torch.save(checkpoint, output / 'appearance.pt')
    metadata = {key: checkpoint[key] for key in ('distance_threshold', 'margin_threshold', 'skus', 'input_size', 'training_seed', 'synthetic_only')}
    metadata.update({'embedding_dimension': 32, 'confidence_logit_scale': 8.0, 'classifier_outputs': list(KNOWN_SKUS) + ['AUXILIARY_SYNTHETIC_OUTLIER'],
                     'prototypes': prototypes.tolist(),
                     'input_contract': 'RGB uint8 crop -> bilinear resize64 -> float32 NCHW /255',
                     'output_contract': 'TorchScript returns (3-class unscaled logits, L2-normalized32-dimensional embeddings). Labels use nearest known prototype; reject distance above threshold or second-minus-first distance below margin.'})
    (output / 'appearance_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    exported = torch.jit.script(network)
    exported.save(str(output / 'appearance.ts'))
    test, test_labels = dataset(20000, 120, (0, 1, 2))
    logits, embeddings, distances = get_distances(network, test, prototypes)
    exported_logits, exported_embeddings, exported_distances = get_distances(exported, test, prototypes)
    predictions = decide(distances, threshold, margin)
    exported_predictions = decide(exported_distances, threshold, margin)
    baseline_train = color_features(train)
    baseline_prototypes = torch.stack([baseline_train[train_labels == kind].mean(0) for kind in range(2)])
    baseline_val_distances = torch.cdist(color_features(validation), baseline_prototypes)
    # Same validation unknown family available to baseline threshold selection.
    baseline_best = None
    for value in np.linspace(.005, 1.0, 200):
        guess = decide(baseline_val_distances, float(value), 0.)
        score = .5 * (float((guess[:240] == validation_labels[:240]).float().mean()) + float((guess[240:] == -1).float().mean()))
        if baseline_best is None or score > baseline_best[0]:
            baseline_best = (score, float(value))
    baseline_distances = torch.cdist(color_features(test), baseline_prototypes)
    baseline_predictions = decide(baseline_distances, baseline_best[1], 0.)
    with torch.inference_mode():
        eager_latency = latency(network, test[:1])
        script_latency = latency(exported, test[:1])
    metrics = {'data': {'origin': 'agent-authored synthetic PIL package textures and randomized crops',
                        'train_seed_range': [0, 599], 'validation_seed_range': [10000, 10119],
                        'development_seed_range': [20000, 20119],
                        'train_known': 1200, 'train_auxiliary_outliers': 600, 'validation_each_class': 120, 'test_each_class': 120,
                        'unknown_calibration': 'green X only in validation, not encoder training; 600 auxiliary random solid/multi-stripe/dot outliers used in encoder training',
                        'limitations': 'synthetic only; single unknown family; no real product or general open-set claim'},
               'training': {'epochs': args.epochs, 'seconds': training_seconds, 'seed': 1729, 'cpu_threads': 2, 'history': history},
               'rejection': {'distance_threshold': threshold, 'margin_threshold': margin, 'selection': 'balanced validation known accuracy and unknown rejection'},
               'eager': summarize(predictions, test_labels), 'torchscript': summarize(exported_predictions, test_labels),
               'baseline_color_mean': summarize(baseline_predictions, test_labels),
               'baseline_distance_threshold': baseline_best[1],
               'export': {'max_abs_logit_error': float((logits - exported_logits).abs().max()),
                          'max_abs_embedding_error': float((embeddings - exported_embeddings).abs().max()),
                          'prediction_disagreements': int((predictions != exported_predictions).sum()),
                          'eager_bytes': (output / 'appearance.pt').stat().st_size,
                          'torchscript_bytes': (output / 'appearance.ts').stat().st_size},
               'latency': {'batch_size': 1, 'input': '1x3x64x64 float32, preprocessing excluded', 'unit': 'ms',
                           'eager': eager_latency, 'torchscript': script_latency},
               'raw_final_predictions': [{'seed': 20000 + i % 120, 'truth': int(test_labels[i]),
                                          'prediction': int(predictions[i]), 'baseline_prediction': int(baseline_predictions[i]),
                                          'distances': distances[i].tolist(), 'embedding': embeddings[i].tolist()} for i in range(len(test))]}
    (output / 'vision_metrics_development.json').write_text(json.dumps(metrics, indent=2) + '\n')
    print(json.dumps({key: metrics[key] for key in ('eager', 'baseline_color_mean', 'export')}, indent=2), flush=True)

if __name__ == '__main__':
    main()
