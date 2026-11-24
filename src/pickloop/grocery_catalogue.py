"""Identify a catalogue product in a photograph, or hold it as UNKNOWN."""
import argparse
from functools import cache
from hashlib import sha256
import json
from pathlib import Path


DEFAULT_HEAD = Path(__file__).with_name('data') / 'grocery_catalogue.npz'
BRAVO_GALLERY = DEFAULT_HEAD.with_name('bravo_carton_panels.npz')
BRAVO_GALLERY_SHA256 = '7537c7c13ee7a44635e2fc49c3a21235be712b6b4bcbd2a4bc558bd44a81312c'
BRAVO = {'Bravo-Apple-Juice', 'Bravo-Orange-Juice'}


@cache
def bravo_matcher():
    from .carton_matcher import CartonMatcher

    if sha256(BRAVO_GALLERY.read_bytes()).hexdigest() != BRAVO_GALLERY_SHA256:
        raise ValueError('packaged Bravo gallery checksum mismatch')
    return CartonMatcher.load(BRAVO_GALLERY)


def resolve_decision(generic, read_rgb):
    """Verify either Bravo candidate against the frozen panel gallery using original pixels."""
    top1 = generic['top1']
    result = dict(generic, generic_top1=top1, generic_prediction=generic['prediction'], decision_source='generic',
                  panel_prediction=None, panel_reason=None, panel_inliers=None, panel_color_similarity=None,
                  panel_color_gap=None)
    if top1 in BRAVO:
        panel = bravo_matcher().predict(read_rgb())
        prediction = panel['prediction']
        if prediction not in BRAVO and prediction != 'UNKNOWN':
            raise ValueError('unexpected class returned by the frozen Bravo panel matcher')
        result.update({f'panel_{field}': value for field, value in panel.items()})
        result.update(decision_source='bravo_panel', prediction=prediction,
                      top1=top1 if prediction == 'UNKNOWN' else prediction)
    return result


def add_arguments(parser):
    parser.add_argument('image', type=Path)
    parser.add_argument('--weights', type=Path, help='verified DINOv2 safetensors (default: download once to cache)')
    parser.add_argument('--head', type=Path, default=DEFAULT_HEAD)
    parser.add_argument('--baseline', action='store_true', help='replay the historical 81-way head and Bravo verifier')
    parser.add_argument('--juice-gate', action='store_true', help='replay the historical hold-first juice gate')
    parser.add_argument('--general-only', action='store_true', help='run the 81-way head without Bravo verification')


def run(args):
    import numpy as np
    from PIL import Image, ImageOps
    from .catalogue_features import CatalogueEncoder
    from .catalogue_model import CatalogueHead

    head = CatalogueHead.load(args.head)
    with Image.open(args.image) as image:
        rgb = np.asarray(ImageOps.exif_transpose(image).convert('RGB'))
    encoder = CatalogueEncoder(args.weights)
    result, = head.predict(encoder.encode([rgb]))
    if not args.general_only:
        result = resolve_decision(result, lambda: rgb)
    if args.juice_gate:
        from .juice_gate import apply_juice_gate
        result = apply_juice_gate(result, lambda: rgb)
    elif not args.baseline and not args.general_only:
        from .product_text import recognize_exact
        result = recognize_exact(result, lambda: rgb)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
