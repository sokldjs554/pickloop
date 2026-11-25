"""Record the specified normal, spatial-swap, and refusal order scenarios."""
import argparse
from pathlib import Path
import hashlib
from importlib.metadata import version

from pickloop.order_pick import MIX, ORANGE, ROOT, Reader, run_case, write_json


JOBS = [('duplicate', 'duplicate', ORANGE, 1000),
        ('orange', 'standard', ORANGE, None), ('orange-swapped', 'swapped', ORANGE, None),
        ('mixed', 'swapped', MIX, None), ('mixed-standard', 'standard', MIX, None),
        ('unreadable', 'unreadable', ORANGE, None), ('absent', 'absent', ORANGE, None),
        ('wrong-volume', 'duplicate', ORANGE, 500), ('unspecified-volume', 'different-sizes', ORANGE, None),
        ('unreadable-volume', 'ambiguous', ORANGE, 1000)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    reader = Reader(args.weights)
    index = []
    for name, case, sku, volume_ml in JOBS:
        result = run_case(case, sku, args.out/name, reader, volume_ml=volume_ml)
        frames = [dict(f, image=f"{name}/{f['image']}") for f in result['frames']]
        hero = (next(f['image'] for f in result['frames'] if f['stage'] == 'LIFTED')
                if result['status'] == 'COMPLETED' else 'overview.png')
        index.append(dict(id=name, order_sku=sku, order_volume_ml=volume_ml, status=result['status'], reason=result['reason'],
                          result=f'{name}/result.json', poster=f'{name}/{hero}', clip=f'{name}/motion.mp4' if result['clip'] else None,
                          frames=frames))
        print(name, result['status'], result['reason'], flush=True)
    sources = ['src/pickloop/order_pick.py', 'src/pickloop/simulation.py', 'src/pickloop/perception.py',
               'src/pickloop/bin_perception.py', 'src/pickloop/juice_gate.py', 'src/pickloop/data/juice_gate.npz',
               'src/pickloop/grocery_catalogue.py', 'src/pickloop/catalogue_model.py', 'src/pickloop/catalogue_features.py',
               'scripts/run_order_pick.py', 'scripts/make_order_labels.py', 'assets/order-pick/manifest.json']
    write_json(args.out/'index.json', dict(schema_version=2, runs=index,
               source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
               versions={name:version(name) for name in ('mujoco','numpy','opencv-python-headless','torch','timm')}))


if __name__ == '__main__':
    main()
