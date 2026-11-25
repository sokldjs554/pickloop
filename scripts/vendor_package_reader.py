"""Rebuild the local-only photo reader assets from pinned archives, or verify them offline."""
import argparse
import ast
import base64
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'web/vendor/package-reader'
ARCHIVES = [
    ('tesseract.js', '6.0.1', '/sPvMvrCtgxnNRCjbTYbr7BRu0yfWDsMZQ2a/T5aN/L1t8wUQN6tTWv6p6FwzpoEBA0jrN2UD2SX4QQFRdoDbA==', {
        'dist/worker.min.js': 'ocr-worker.js', 'dist/worker.min.js.LICENSE.txt': 'licenses/ocr-worker-notices.txt',
        'LICENSE.md': 'licenses/tesseract-js.txt'}),
    ('tesseract.js-core', '6.0.0', '1Qncm/9oKM7xgrQXZXNB+NRh19qiXGhxlrR8EwFbK5SaUbPZnS5OMtP/ghtqfd23hsr1ZvZbZjeuAGcMxd/ooA==', {
        'tesseract-core-lstm.wasm.js': 'tesseract-core-lstm.wasm.js', 'LICENSE': 'licenses/tesseract-core.txt'}),
    ('@tesseract.js-data/eng', '1.0.0', 'mbTumm6KQPUHyzTPQaF3ObXYnx0SqqfV2nabqFVQBwD6Kl7PhGSLSzOlfFTWy0P3BjghaSKA2W9GB19Jk+ZcTg==', {
        '4.0.0_best_int/eng.traineddata.gz': 'eng.traineddata.gz'}),
    ('@tesseract.js-data/kor', '1.0.0', 'tepYhsYiRJ8E44R27MHxVteEDDLfYQxuvM6u4JlEHcCYqwpefvI5TGzoMgB67kunOvtyEJYtT5zfJ/6R6FVU9w==', {
        '4.0.0_best_int/kor.traineddata.gz': 'kor.traineddata.gz'}),
    ('@techstark/opencv-js', '4.10.0-release.1', 'S4XELidRiQeA0q1s9VQLo540wCxUo24r1O4C+LqZ6llX+sPCXvZCPv3Ice8dEIr0uavyZ8YZeKXSBdDgMXSXjw==', {
        'dist/opencv.js': 'opencv.js', 'LICENSE': 'licenses/opencv.txt'}),
    ('zxing-wasm', '2.2.1', 'njVYnrDCDLVssruDprHGL/NSHm/lH5qsNqHQLNptLSNEf4Zsw9G2Z8A+dN+HFNYmbP8EAlEk3AxV1RiMHdNAQQ==', {
        'dist/es/reader/index.js': 'zxing/reader/index.js', 'dist/es/share.js': 'zxing/share.js',
        'dist/reader/zxing_reader.wasm': 'zxing_reader.wasm', 'LICENSE': 'licenses/zxing-wasm.txt'}),
]
# Production-only reader code, language models, and their upstream notices.
NOTICES = {
    'leptonica.txt': ('https://raw.githubusercontent.com/DanBloomberg/leptonica/4af068b56a9674da915debea4ed7e1b9885b17e8/leptonica-license.txt',
                    '87829abb5bbb00b55a107365da89e9a33f86c4250169e5a1e5588505be7d5806'),
    'libgif.txt': ('https://raw.githubusercontent.com/mirrorer/giflib/fa37672085ce4b3d62c51627ab3c8cf2dda8009a/COPYING',
                    '0c9b7990ecdca88b676db232c226548ac408b279f550d424d996f0d83591dd8e'),
    'libjpeg.txt': ('https://raw.githubusercontent.com/LuaDist/libjpeg/6c0fcb8ddee365e7abc4d332662b06900612e923/README',
                    'c791da525733040e622ed257c7b096b8f5191b332604ead0c6bc2b54cbd8e0d1'),
    'libpng.txt': ('https://raw.githubusercontent.com/glennrp/libpng/a37d4836519517bdce6cb9d956092321eca3e73b/LICENSE',
                    '33ba4e187d8b0c8d7ab2bc2e522bb095219e03089e9aa0122b4fb9eb2b7de82b'),
    'webp.txt': ('https://raw.githubusercontent.com/webmproject/libwebp/20ef03ee351d4ff03fc5ff3ec4804a879d1b9d5c/COPYING',
                    '5aec868f669e384a22372a4e8a1a6cd7d44c64cd451f960ca69cc170d1e13acf'),
    'openlibm.txt': ('https://raw.githubusercontent.com/JuliaMath/openlibm/ae2d91698508701c83cab83714d42a1146dccf85/LICENSE.md',
                    'b1843fbf5b03f519a5f0a44fce751bdd1022ae7148614923f9d6293e17a18b17'),
    'zlib.txt': ('https://raw.githubusercontent.com/madler/zlib/21767c654d31d2dccdde4330529775c6c5fd5389/README',
                    'fc2c3368901700f0acdeb1d8afeaca5923296768ec6824ecdf627aac396001fd'),
    'zxing-cpp.txt': ('https://raw.githubusercontent.com/zxing-cpp/zxing-cpp/c0a7c6cd2165457c721c58045edd22ffee9624e9/LICENSE',
                    'c6596eb7be8581c18be736c846fb9173b69eccf6ef94c5135893ec56bd92ba08'),
    'tiff.txt': ('https://raw.githubusercontent.com/libsdl-org/libtiff/b51bb157123264e26d34c09cc673d213aea61fc7/COPYRIGHT',
                    'fbd6fed7938541d2c809c0826225fc85e551fdbfa8732b10f0c87e0847acafd7'),
    'zxing-bridge.txt': ('https://raw.githubusercontent.com/Sec-ant/zxing-wasm/v2.2.1/src/cpp/LICENSE',
                    '80caa1dd3fca8e626335ca3b936c97b71463241718f77d51589727a8cfd9b41b'),
    'language-models.txt': ('https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/LICENSE',
                            'a6cba85bc92e0cff7a450b1d873c0eaa2e9fc96bf472df0247a26bec77bf3ff9'),
    'stb.txt': ('https://raw.githubusercontent.com/nothings/stb/f0569113c93ad095470c54bf34a17b36646bbbb5/LICENSE',
                'bebfe904b14301657e4e5d655c811d51fd31b97c455b9cc2d8600d6bac6cff63'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def split_opencv(data):
    # Externalize the embedded module to avoid transferring its base64 representation.
    match = re.search(rb'wasmBinaryFile="data:application/octet-stream;base64,([A-Za-z0-9+/=]+)"', data)
    if not match:
        raise ValueError('Missing embedded OpenCV WebAssembly module')
    yield 'opencv.wasm', base64.b64decode(match[1], validate=True)
    yield 'opencv.js', data[:match.start()] + b'wasmBinaryFile="opencv.wasm"' + data[match.end():]


def assets():
    for name, version, checksum, members in ARCHIVES:
        filename = f'{name.rsplit("/", 1)[-1]}-{version}.tgz'
        with urlopen(f'https://registry.npmjs.org/{name}/-/{filename}', timeout=40) as response:
            archive = response.read()
        if base64.b64encode(hashlib.sha512(archive).digest()).decode() != checksum:
            raise ValueError(f'Archive integrity failed for {name}')
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            for source, output in members.items():
                data = package.extractfile('package/' + source).read()
                if output == 'opencv.js':
                    yield from split_opencv(data)
                else:
                    yield output, data
    for name, (url, checksum) in NOTICES.items():
        with urlopen(url, timeout=30) as response:
            data = response.read()
        if digest(data) != checksum:
            raise ValueError(f'Notice integrity failed for {name}')
        yield 'licenses/' + name, data
    yield 'registry.json', registry_bytes()


def registry_bytes():
    tree = ast.parse((ROOT / 'src/pickloop/pack_barcode.py').read_text())
    registry = next(ast.literal_eval(s.value) for s in tree.body if isinstance(s, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'REGISTERED_GTINS' for t in s.targets))
    # The browser demonstration also registers the 250 mL retail carton.
    registry['6415130089834'] = 'God-Morgon-Orange-Juice-250ml'
    return (json.dumps(registry, indent=2, sort_keys=True) + '\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild', action='store_true', help='Download and verify sources before writing outputs')
    args = parser.parse_args()
    manifest = DEST / 'sha256.json'
    if args.rebuild:
        contents = dict(assets())
        for name, data in contents.items():
            path = DEST / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest.write_text(json.dumps({name: digest(data) for name, data in sorted(contents.items())}, indent=2) + '\n')
    expected = json.loads(manifest.read_text())
    for name, checksum in expected.items():
        if digest((DEST / name).read_bytes()) != checksum:
            raise SystemExit(f'Vendor integrity failed for {name}')
    if expected.get('registry.json') != digest(registry_bytes()):
        raise SystemExit('Rebuild registry.json from the current pack_barcode registry')
    print(f'Verified {len(expected)} photo reader assets and the current barcode registry.')


if __name__ == '__main__':
    main()
