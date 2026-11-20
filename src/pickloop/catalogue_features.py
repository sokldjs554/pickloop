"""Frozen DINOv2 and color descriptors for catalogue photographs."""
from pathlib import Path
import hashlib
import os
import shutil
import tempfile
from urllib.request import urlopen

import cv2
import numpy as np
from PIL import Image

REVISION = '4610ca143709d58a633b6397a74412c2c3842454'
WEIGHTS_URL = f'https://huggingface.co/timm/vit_small_patch14_dinov2.lvd142m/resolve/{REVISION}/model.safetensors'
WEIGHTS_SHA = '04d27f3400d059fc0cfd7d17dd1909a75bf3ea8fb3eeb48b97cb99e57ee20081'
FEATURE_VERSION = 'dinov2s14-224-cls-center-hsv-v1'


def verified_weights(path=None):
    if path is None:
        root = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'pickloop'
        path = root / f'dinov2-{WEIGHTS_SHA[:12]}.safetensors'
        if not path.exists():
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=root, delete=False) as tmp:
                name = Path(tmp.name)
            try:
                with urlopen(WEIGHTS_URL, timeout=90) as source, name.open('wb') as out:
                    shutil.copyfileobj(source, out)
                verified_weights(name)
                name.replace(path)
                return path
            finally:
                name.unlink(missing_ok=True)
    path = Path(path)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != WEIGHTS_SHA:
            raise ValueError('DINOv2 weights SHA-256 mismatch')
    return path


def center_color(rgb):
    h, w = rgb.shape[:2]
    region = rgb[h // 5:max(h // 5 + 1, h * 4 // 5), w // 5:max(w // 5 + 1, w * 4 // 5)]
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    histogram = cv2.calcHist([hsv], [0, 1, 2], None, [18, 4, 3], [0, 180, 0, 256, 0, 256]).ravel()
    return np.sqrt(histogram / histogram.sum())


class CatalogueEncoder:
    def __init__(self, weights=None):
        import torch
        try:
            import timm
            from safetensors.torch import load_file
        except ImportError as error:
            raise RuntimeError("Install the project catalogue extra: python -m pip install -e '.[catalogue]'") from error
        path = verified_weights(weights)
        torch.set_num_threads(min(4, torch.get_num_threads()))
        self.torch = torch
        self.net = timm.create_model('vit_small_patch14_dinov2', pretrained=False, num_classes=0,
                                     dynamic_img_size=True)
        self.net.load_state_dict(load_file(str(path)))
        self.net.eval()
        self.mean = torch.tensor([.485, .456, .406]).view(1, 3, 1, 1)
        self.std = torch.tensor([.229, .224, .225]).view(1, 3, 1, 1)

    def encode(self, rgbs):
        torch = self.torch
        frames = np.stack([np.asarray(Image.fromarray(rgb).resize((224, 224), Image.Resampling.BICUBIC))
                           for rgb in rgbs])
        x = torch.from_numpy(frames).permute(0, 3, 1, 2).float() / 255
        with torch.inference_mode():
            tokens = self.net.forward_features((x - self.mean) / self.std)
            central = tokens[:, 1:].reshape(len(frames), 16, 16, -1)[:, 3:13, 3:13].mean((1, 2))
            normalize = torch.nn.functional.normalize
            color = torch.from_numpy(np.stack([center_color(rgb) for rgb in rgbs]))
            features = torch.cat([normalize(tokens[:, 0]), .8 * normalize(central), .30 * color], dim=1)
            return normalize(features).numpy()
