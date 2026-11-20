"""Classify photographs of the two registered Bravo cartons with a frozen ResNet-18."""
from pathlib import Path
import hashlib

import numpy as np
from PIL import Image
from scipy.optimize import minimize
from scipy.special import logsumexp

from .grocery_evaluation import REGISTERED
from .photo_evaluation import UNKNOWN

NAMES = tuple(REGISTERED.values())
WEIGHTS_SHA256 = 'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec'
SCHEMA = 'pickloop-grocery-resnet18-v1'


def development_product(class_id):
    """Reserve every third unregistered packaging ID for evaluation only."""
    return class_id in REGISTERED or class_id % 3 != 0


def product_margins(logits):
    winner = np.argmax(logits[:, :2], axis=1)
    rows = np.arange(len(logits))
    rival = np.maximum(logits[rows, 1 - winner], logits[:, 2])
    return winner, logits[rows, winner] - rival


def decide(winner, margin, boundary):
    return [NAMES[i] if score > boundary else UNKNOWN for i, score in zip(winner, margin, strict=True)]


def validation_boundary(unknown_margins):
    scores = np.asarray(unknown_margins, dtype=float)
    if scores.ndim != 1 or not len(scores) or not np.all(np.isfinite(scores)):
        raise ValueError('need finite validation unknown scores')
    # Strict > excludes all ties at the first disallowed negative.
    return max(0., float(np.sort(scores)[::-1][len(scores) // 20]))


def fit_head(vectors, labels):
    """Optimize balanced multinomial cross-entropy with an L2 penalty on slopes."""
    x = np.asarray(vectors, dtype=np.float64)
    y = np.asarray(labels, dtype=int)
    if x.ndim != 2 or y.shape != (len(x),) or set(y) != {0, 1, 2} or not np.isfinite(x).all():
        raise ValueError('need finite vectors and samples of all three classes')
    counts = np.bincount(y)
    sample_weights = 1 / (3 * counts[y])
    targets = np.eye(3)[y]
    features = x.shape[1]
    penalty = .0003

    def objective(parameters):
        weights = parameters[:features * 3].reshape(features, 3)
        logits = x @ weights + parameters[-3:]
        log_prob = logits - logsumexp(logits, axis=1, keepdims=True)
        loss = -(sample_weights * log_prob[np.arange(len(x)), y]).sum() + .5 * penalty * (weights ** 2).sum()
        residual = sample_weights[:, None] * (np.exp(log_prob) - targets)
        gradient = x.T @ residual + penalty * weights
        return loss, np.r_[gradient.ravel(), residual.sum(axis=0)]

    result = minimize(objective, np.zeros((features + 1) * 3), jac=True, method='L-BFGS-B',
                      options={'maxiter': 700, 'ftol': 1e-12, 'gtol': 1e-8})
    if not result.success:
        raise RuntimeError(f'linear head fit did not converge: {result.message}')
    return result.x[:-3].reshape(features, 3), result.x[-3:]


class PhotoEncoder:
    def __init__(self, checkpoint):
        import torch
        from torchvision.models import resnet18

        with Path(checkpoint).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != WEIGHTS_SHA256:
                raise ValueError('unexpected ResNet-18 weights')
            stream.seek(0)
            state = torch.load(stream, map_location='cpu', weights_only=True)
        net = resnet18(weights=None)
        net.load_state_dict(state)
        net.fc = torch.nn.Identity()
        self.net = net.eval()
        self.torch = torch
        self.mean = torch.tensor([.485, .456, .406]).view(1, 3, 1, 1)
        self.std = torch.tensor([.229, .224, .225]).view(1, 3, 1, 1)

    def encode(self, images):
        torch = self.torch
        resized = [np.asarray(Image.fromarray(image).resize((224, 224), Image.Resampling.BILINEAR))
                   for image in images]
        x = torch.from_numpy(np.stack(resized)).permute(0, 3, 1, 2).float() / 255
        with torch.inference_mode():
            vectors = self.net((x - self.mean) / self.std)
            return torch.nn.functional.normalize(vectors, dim=1).numpy().astype(np.float64)


class ProductRecognizer:
    def __init__(self, head):
        if (head.get('schema') != SCHEMA or head.get('classes') != [*NAMES, UNKNOWN]
                or head.get('weights_sha256') != WEIGHTS_SHA256):
            raise ValueError('unexpected product head or encoder')
        self.weights = np.asarray(head['slopes'])
        self.bias = np.asarray(head['intercept'])
        self.boundary = float(head['boundary'])
        if (self.weights.shape != (512, 3) or self.bias.shape != (3,) or self.boundary < 0
                or not np.isfinite(self.weights).all() or not np.isfinite(self.bias).all()
                or not np.isfinite(self.boundary)):
            raise ValueError('invalid head parameters')

    def predict(self, vectors):
        logits = vectors @ self.weights + self.bias
        winner, scores = product_margins(logits)
        return decide(winner, scores, self.boundary), scores
