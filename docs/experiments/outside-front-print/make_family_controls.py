"""Rebuild synthetic neighbouring-carton and conflicting-code test scenes."""
import argparse
import csv
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

SOURCES = (
    '65e455524bd717f773a91668b07db1598b6f655aeda3b33fa1aa63f57bc09959',
    '08be70619c12080fdc66bc000e314cadbd05173509c7d6ae0d343f13d1e8fda8',
)


def paste_original(canvas, path, box):
    image = ImageOps.exif_transpose(Image.open(path)).convert('RGBA')
    background = Image.new('RGBA', image.size, 'white')
    background.alpha_composite(image)
    x, y, right, bottom = box
    fit = ImageOps.contain(background.convert('RGB'), (right-x, bottom-y))
    canvas.paste(fit, ((x+right-fit.width)//2, (y+bottom-fit.height)//2))


def barcode(code):
    left_patterns = ['0001101','0011001','0010011','0111101','0100011',
                     '0110001','0101111','0111011','0110111','0001011']
    parity = ['LLLLLL','LLGLGG','LLGGLG','LLGGGL','LGLLGG',
              'LGGLLG','LGGGLL','LGLGLG','LGLGGL','LGGLGL']
    inverse = str.maketrans('01', '10')
    left = []
    for group, digit in zip(parity[int(code[0])], code[1:7], strict=True):
        pattern = left_patterns[int(digit)]
        left.append(pattern if group == 'L' else pattern.translate(inverse)[::-1])
    right = ''.join(left_patterns[int(d)].translate(inverse) for d in code[7:])
    bars = '101' + ''.join(left) + '01010' + right + '101'
    image = Image.new('RGB', (5*(len(bars)+24), 190), 'white')
    draw = ImageDraw.Draw(image)
    for i, bit in enumerate(bars):
        if bit == '1':
            x = 5*(i+12)
            draw.rectangle((x, 10, x+4, 170), fill='black')
    return image


def generate(smooth, apple, output):
    output.mkdir(exist_ok=True, parents=True)
    for path, expected in zip((smooth, apple), SOURCES, strict=True):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Original image changed: {path}')
    rows = []

    def record(sample_id, image, expected):
        target = output / (sample_id + '.png')
        image.save(target)
        rows.append(dict(id=sample_id, path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                         expected=expected))

    for sample_id, foreground, background in [
        ('neighbor_equal', (65,50,535,1250), (520,55,935,1220)),
        ('neighbor_behind', (0,0,950,1280), (695,270,990,1000)),
    ]:
        scene = Image.new('RGB', (1000,1300), 'white')
        paste_original(scene, smooth, background)
        paste_original(scene, apple, foreground)
        record(sample_id, scene, 'no positive outside, no exact order')

    for code, sample_id in [('7310865074225','contradictory_registered_code'),
                            ('7310865074829','outside_code')]:
        scene = Image.new('RGB', (850,1400), 'white')
        paste_original(scene, smooth, (45,0,805,1140))
        symbol = barcode(code)
        scene.paste(symbol, ((850-symbol.width)//2,1180))
        record(sample_id, scene, 'original optical precedence')

    with (output/'inputs.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('smooth_orange_original', type=Path)
    parser.add_argument('registered_apple_original', type=Path)
    parser.add_argument('output', type=Path)
    options = parser.parse_args()
    generate(options.smooth_orange_original, options.registered_apple_original, options.output)
