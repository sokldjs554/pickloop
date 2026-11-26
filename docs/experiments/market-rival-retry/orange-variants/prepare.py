"""Regenerate the frozen five-photo resize, masking, and JPEG challenge."""

import argparse
import csv
from hashlib import file_digest
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance


def digest(filename):
    with filename.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def prepare(originals, output):
    output.mkdir(parents=True, exist_ok=True)
    source_table = Path(__file__).with_name('sources.csv')
    with source_table.open(encoding='utf-8', newline='') as source_stream:
        sources = list(csv.DictReader(source_stream))

    with (output / 'manifest.csv').open('x', encoding='utf-8', newline='') as manifest:
        writer = csv.DictWriter(manifest, fieldnames=('id', 'path', 'sha256'), lineterminator='\n')
        writer.writeheader()
        for source in sources:
            original = originals / source['filename']
            if digest(original) != source['sha256']:
                raise ValueError(f'Unexpected bytes for {source["id"]}')
            with Image.open(original) as pixels:
                image = pixels.convert('RGB')
                image.thumbnail((900, 900))
            width, height = image.size
            for region in ('whole', 'footer-masked', 'side-masked'):
                sample = image.copy()
                if region == 'footer-masked':
                    ImageDraw.Draw(sample).rectangle((0, .74*height, width, height), fill=(155, 116, 93))
                elif region == 'side-masked':
                    bounds = (.05*width, .30*height, .30*width, .80*height)
                    ImageDraw.Draw(sample).rectangle(bounds, fill=(142, 93, 77))
                for suffix, factor in (('', 1.0), ('-dim', .9)):
                    identifier = f'{source["id"]}-{region}{suffix}'
                    path = output / f'{identifier}.jpg'
                    ImageEnhance.Brightness(sample).enhance(factor).save(path, quality=85)
                    writer.writerow(dict(id=identifier, path=path.name, sha256=digest(path)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('originals', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prepare(args.originals, args.output)


if __name__ == '__main__':
    main()
