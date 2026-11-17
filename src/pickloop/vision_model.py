"""Small CPU crop encoder and validation-calibrated prototype recognizer.

Only RGB pixels cross this module's inference boundary. No simulator IDs, poses,
texture names, segmentation masks, or catalog labels are supplied to predict().
"""
from pathlib import Path
from typing import Sequence
import numpy as np
from PIL import Image
import torch
from torch import nn
import torch.nn.functional as F

KNOWN_SKUS = ('SKU-RED-A', 'SKU-RED-B')
MODEL_ROOT = Path(__file__).resolve().parents[2] / 'models'
INPUT_SIZE = 64

def crops_to_tensor(crops: Sequence[np.ndarray] | np.ndarray) -> torch.Tensor:
    values = []
    for crop in crops:
        array = np.asarray(crop)
        if array.dtype != np.uint8:
            raise ValueError('crops must contain uint8 pixels')
        if array.ndim != 3 or array.shape[2] != 3 or min(array.shape[:2]) < 2:
            raise ValueError('each crop must be a nonempty HWC RGB image')
        image = Image.fromarray(array).resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR)
        values.append(np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0)
    return torch.from_numpy(np.stack(values)) if values else torch.empty((0, 3, INPUT_SIZE, INPUT_SIZE))

class CropEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv2d(16, 24, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(24, 32, 3, stride=2, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)), nn.Flatten(),
            nn.Linear(32 * 4 * 4, 64), nn.ReLU(), nn.Linear(64, 32),
        )
        self.classifier = nn.Linear(32, 3)

    def forward(self, images: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        embedding = F.normalize(self.features(images), dim=1)
        return self.classifier(embedding), embedding

class AppearanceModel:
    def __init__(self, checkpoint_path=None):
        torch.set_num_threads(2)
        path = Path(checkpoint_path) if checkpoint_path else MODEL_ROOT / 'appearance.pt'
        checkpoint = torch.load(path, map_location='cpu', weights_only=True)
        self.network = CropEncoder().eval()
        self.network.load_state_dict(checkpoint['state_dict'])
        self.prototypes = checkpoint['prototypes']
        self.distance_threshold = float(checkpoint['distance_threshold'])
        self.margin_threshold = float(checkpoint['margin_threshold'])
        self.skus = tuple(checkpoint['skus'])

    def predict(self, crops: Sequence[np.ndarray] | np.ndarray) -> list[dict]:
        images = crops_to_tensor(crops)
        if len(images) == 0:
            return []
        with torch.inference_mode():
            logits, embeddings = self.network(images)
            distances = torch.cdist(embeddings, self.prototypes)
            closest_distances, labels = distances.min(dim=1)
            sorted_distances = distances.sort(dim=1).values
            margins = sorted_distances[:, 1] - sorted_distances[:, 0]
            probabilities = torch.softmax(logits * 8.0, dim=1)
        result = []
        for i, label in enumerate(labels.tolist()):
            distance = float(closest_distances[i])
            known = distance <= self.distance_threshold and float(margins[i]) >= self.margin_threshold
            confidence = float(probabilities[i, label])
            result.append({'sku': self.skus[label] if known else 'UNKNOWN',
                           'confidence': confidence, 'distance': distance,
                           'embedding': embeddings[i].tolist()})
        return result
