"""Make compact parcel label artwork from two pinned fit-set product photos."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageFont

from pickloop.grocery_evaluation import PREFIX, REVISION
from pickloop.simulation import ROOT

LABELS = [('orange', 'God-Morgon-Orange-Juice', 'ORANGE', (114, 3, 347, 346)),
          ('mixed', 'God-Morgon-Orange-Red-Grapefruit-Juice', 'ORANGE & RED GRAPEFRUIT', (0, 0, 329, 348))]


def build(archive, out):
    out.mkdir(parents=True, exist_ok=True)
    fonts = Path('/usr/share/fonts/truetype/dejavu')
    entries = []
    with ZipFile(archive) as source:
        for filename, product, flavor, crop in LABELS:
            path = f'train/Packages/Juice/{product}/{product}_001.jpg'
            raw = source.read(PREFIX + path)
            photo = Image.open(io.BytesIO(raw)).convert('RGB')
            # Simulated shipping label with product photograph and plain-language flavor.
            label = Image.new('RGB', (512, 416), '#241d17')
            label.paste(photo.crop(crop).resize((512, 332), Image.Resampling.LANCZOS))
            draw = ImageDraw.Draw(label)
            draw.text((256, 350), 'GOD MORGON', anchor='mm', fill='#fff3cf',
                      font=ImageFont.truetype(str(fonts/'DejaVuSans-Bold.ttf'), 20))
            draw.text((256, 390), flavor, anchor='mm', fill='#fff3cf',
                      font=ImageFont.truetype(str(fonts/'DejaVuSans-Bold.ttf'), 29))
            label.save(out/f'{filename}.png')
            entries.append(dict(texture=f'{filename}.png', sku=product, source_path=path,
                                source_sha256=hashlib.sha256(raw).hexdigest(), crop_ltrb=crop,
                                source_url=f'https://raw.githubusercontent.com/marcusklasson/GroceryStoreDataset/{REVISION}/dataset/{path}'))
    # Size is a printed experimental shipping-label field read by the zoom camera.
    for volume_ml in (1000, 500):
        sized = Image.open(out/'orange.png').copy()
        draw = ImageDraw.Draw(sized)
        draw.rectangle((0, 332, 511, 415), fill='#241d17')
        draw.text((256, 351), 'GOD MORGON', anchor='mm', fill='#fff3cf',
                  font=ImageFont.truetype(str(fonts/'DejaVuSans-Bold.ttf'), 23))
        draw.text((256, 390), f'ORANGE  {volume_ml} ML', anchor='mm', fill='#fff3cf',
                  font=ImageFont.truetype(str(fonts/'DejaVuSans-Bold.ttf'), 31))
        sized.save(out/f'orange-{volume_ml}ml.png')
        entries.append(dict(texture=f'orange-{volume_ml}ml.png', sku=LABELS[0][1], volume_ml=volume_ml,
                            source=f'orange.png with a simulated {volume_ml} ML shipping label'))
    obscured = Image.open(out/'orange.png').copy()
    tape = ImageDraw.Draw(obscured)
    tape.rectangle((195, 127, 454, 182), fill='#beb2a1')
    tape.rectangle((0, 365, 511, 415), fill='#beb2a1')
    obscured.save(out/'orange-obscured.png')
    entries.append(dict(texture='orange-obscured.png', sku=LABELS[0][1],
                        source='orange.png with opaque tape over both flavour legends'))
    label = Image.new('RGB', (512, 416), '#264e43')
    draw = ImageDraw.Draw(label)
    for cx, cy in [(170, 140), (224, 110), (292, 150), (328, 112)]:
        draw.ellipse((cx-28, cy-56, cx+28, cy+56), fill='#a9bd83', outline='#e2dfa9', width=3)
        draw.line((cx, cy-45, cx, cy+56), fill='#537d58', width=3)
    draw.text((256, 280), 'HERBAL TEA', anchor='mm', fill='#efe8c0',
              font=ImageFont.truetype(str(fonts/'DejaVuSerif-Bold.ttf'), 48))
    draw.text((256, 340), 'MINT LEAF', anchor='mm', fill='#e1dfbf',
              font=ImageFont.truetype(str(fonts/'DejaVuSans.ttf'), 31))
    label.save(out/'mint.png')
    entries.append(dict(texture='mint.png', sku='Unregistered-Mint-Tea', source='original illustrated fixture'))
    for entry in entries:
        entry['texture_sha256'] = hashlib.sha256((out/entry['texture']).read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps(dict(dataset_revision=REVISION, labels=entries), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT/'assets/order-pick')
    args = parser.parse_args()
    build(args.archive, args.out)
