"""Optional visual naming for three loose produce classes on otherwise held photos."""
from functools import cache
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import urlopen

import numpy as np
from PIL import Image, ImageOps


WEIGHTS_URL = 'https://download.pytorch.org/models/resnet18-f37072fd.pth'
WEIGHTS_SHA = 'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec'
TARGETS = {'banana':'Banana', 'pineapple':'Pineapple', 'cucumber':'Cucumber'}
# The generic head must place the object in an actual fruit/vegetable registry
# class. A grocery carton illustrated with fruit can also trigger ImageNet.
PRODUCE = frozenset(('Golden-Delicious','Granny-Smith','Pink-Lady','Red-Delicious','Royal-Gala',
    'Avocado','Banana','Kiwi','Lemon','Lime','Mango','Cantaloupe','Galia-Melon','Honeydew-Melon',
    'Watermelon','Nectarine','Orange','Papaya','Passion-Fruit','Peach','Anjou','Conference','Kaiser',
    'Pineapple','Plum','Pomegranate','Red-Grapefruit','Satsumas','Asparagus','Aubergine','Cabbage',
    'Carrots','Cucumber','Garlic','Ginger','Leek','Brown-Cap-Mushroom','Yellow-Onion',
    'Green-Bell-Pepper','Orange-Bell-Pepper','Red-Bell-Pepper','Yellow-Bell-Pepper',
    'Floury-Potato','Solid-Potato','Sweet-Potato','Red-Beet','Beef-Tomato','Regular-Tomato',
    'Vine-Tomato','Zucchini'))
PACKAGE_TEXT = re.compile(r'\b(?:juice|juices|morgon|godmorgon|milk|yogurt|yoghurt|smoothie|litre|ml)\b', re.I)


def verified_weights(path=None):
    if path is None:
        folder = Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'pickloop'
        path = folder / f'resnet18-{WEIGHTS_SHA[:12]}.pth'
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as out:
                tmp = Path(out.name)
            try:
                with urlopen(WEIGHTS_URL, timeout=90) as stream, tmp.open('wb') as out:
                    shutil.copyfileobj(stream, out)
                verified_weights(tmp)
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)
    path = Path(path)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != WEIGHTS_SHA:
            raise ValueError('ResNet-18 weights SHA-256 mismatch')
    return path


class ProduceClassifier:
    def __init__(self, weights=None):
        import torch
        from torchvision.models import ResNet18_Weights, resnet18
        self.torch = torch
        self.net = resnet18(weights=None)
        self.net.load_state_dict(torch.load(verified_weights(weights), map_location='cpu', weights_only=True))
        self.net.eval()
        self.transform = ResNet18_Weights.IMAGENET1K_V1.transforms()
        self.names = ResNet18_Weights.IMAGENET1K_V1.meta['categories']

    def evidence(self, rgb):
        if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError('expected H x W x 3 uint8 RGB')
        im = Image.fromarray(rgb)
        # Centre crop vs entire original field. After padding to 224, the same
        # normalize/resize pipeline sees all real pixels in the second view.
        from torchvision.transforms.functional import pil_to_tensor, normalize
        full = ImageOps.pad(im, (224,224), method=Image.Resampling.BILINEAR, color=(124,116,104))
        tensor = normalize(pil_to_tensor(full).float()/255., self.transform.mean, self.transform.std)
        with self.torch.inference_mode():
            probs = self.net(self.torch.stack((self.transform(im), tensor))).softmax(dim=1)
        values, ids = probs.topk(2, dim=1)
        return [dict(view=view, label=self.names[idx[0]], probability=float(v[0]), runner=self.names[idx[1]],
                     margin=float(v[0]-v[1])) for view,v,idx in zip(('centre','whole'),values,ids,strict=True)]


@cache
def classifier(weights=None):
    return ProduceClassifier(weights)


def eligibility(current):
    if current.get('prediction') != 'UNKNOWN':
        return 'existing_name'
    if current.get('generic_prediction') != 'UNKNOWN' or current.get('generic_top1') not in PRODUCE:
        return 'generic_not_held_produce'
    if (current.get('recognition_gtins') or current.get('recognition_source') == 'barcode' or
            current.get('recognition_reason') in ('conflicting_product_or_size','conflicting_flavours') or
            any(PACKAGE_TEXT.search(t) for t in current.get('recognition_text', []))):
        return 'package_evidence'
    return None


def decide(current, views):
    names = {v['label'] for v in views}
    if len(views) != 2 or len(names) != 1 or not names.issubset(TARGETS):
        return None, 'unmapped_or_conflicting_views'
    name = TARGETS[views[0]['label']]
    agrees = name == current['generic_top1']
    # A different produce top-1 needs stronger corroboration from both views.
    floor = .75 if agrees else .90
    if min(v['probability'] for v in views) < floor or min(v['margin'] for v in views) < .55:
        return None, 'weak_imagenet_evidence'
    if not agrees and current.get('support', -1.) < .50:
        return None, 'weak_catalogue_produce_support'
    return name, 'two_view_registered_produce'


def apply_produce_rescue(current, read_rgb, weights=None):
    reason = eligibility(current)
    views, name = [], None
    if reason is None:
        views = classifier(weights).evidence(read_rgb())
        name, reason = decide(current, views)
    evidence = dict(prior_prediction=current['prediction'], reason=reason, views=views)
    result = dict(current, produce_rescue=evidence)
    if name is not None:
        result.update(prediction=name, recognition_source='produce_rescue', recognition_reason=reason)
    return result
