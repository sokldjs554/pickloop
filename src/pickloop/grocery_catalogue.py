"""Identify a catalogue product in a photograph, or hold it as UNKNOWN."""
import argparse
import json
from pathlib import Path


DEFAULT_HEAD = Path(__file__).with_name('data') / 'grocery_catalogue.npz'


def add_arguments(parser):
    parser.add_argument('image', type=Path)
    parser.add_argument('--weights', type=Path, help='verified DINOv2 safetensors (default: download once to cache)')
    parser.add_argument('--head', type=Path, default=DEFAULT_HEAD)


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
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
