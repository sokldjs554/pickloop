#!/usr/bin/env python3
"""Fetch checked originals, run a frozen Python revision, or run the shipped browser worker."""
import argparse
import csv
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "docs/experiments/fresh-size-eval"


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def verify_manifest():
    seal = json.loads((STUDY / "freeze.json").read_text())
    for name, expected in seal["sha256"].items():
        if digest(STUDY / name) != expected:
            raise ValueError(f"Frozen manifest changed: {name}")


def fetch(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for row in rows(STUDY / "labels.csv"):
        path = folder / row["id"]
        if path.exists() and digest(path) == row["sha256"]:
            continue
        request = Request(row["image_url"], headers={"User-Agent": "PickLoop-Research/1.0"})
        with urlopen(request, timeout=30) as response:
            payload = response.read(12 * 1024 * 1024 + 1)
        if sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError(f"Source bytes changed: {row['id']}")
        path.write_bytes(payload)


def inputs(folder):
    for row in rows(STUDY / "blind.csv"):
        path = folder / row["id"]
        if digest(path) != row["sha256"]:
            raise ValueError(f"Photo checksum failed: {row['id']}")
        yield row["id"], path


def infer_python(folder, out):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    from pickloop.grocery_catalogue import recognize_rgb

    cv2.setNumThreads(1)
    with out.open("x") as stream:
        for identity, path in inputs(folder):
            with Image.open(path) as photo:
                pixels = np.asarray(ImageOps.exif_transpose(photo).convert("RGB"))
            ordinary = recognize_rgb(pixels)
            strict = recognize_rgb(pixels, require_gtin=True)
            row = {"id": identity, "ordinary": ordinary, "strict": strict}
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()


def infer_browser(folder, out, chromium):
    from playwright.sync_api import sync_playwright

    # Observe the real worker's return value while the normal file input, canvas preparation,
    # optical worker and registry decision execute. The observer never changes messages.
    observer = """window.Worker = class extends Worker {
      constructor(...args) {
        super(...args);
        if (new URL(args[0], location.href).pathname.endsWith('/package-reader.js'))
          this.addEventListener('message', event => window.barcodeWorkerReply = event.data);
      }
    };"""
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / "web"))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as pw:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            browser = pw.chromium.launch(executable_path=chromium)
            page = browser.new_page()
            page.add_init_script(observer)
            base = f"http://127.0.0.1:{server.server_port}"
            with out.open("x") as stream:
                for identity, path in inputs(folder):
                    from PIL import Image
                    with Image.open(path) as im:
                        mime = Image.MIME[im.format]
                    page.goto(base + "/recognition.html")
                    page.locator("#package-photo").set_input_files({
                        "name": "photo." + mime.split("/")[1], "mimeType": mime, "buffer": path.read_bytes()})
                    page.locator('#package-reader [type="submit"]').click()
                    page.wait_for_function("window.barcodeWorkerReply !== undefined", timeout=120_000)
                    reply = page.evaluate("window.barcodeWorkerReply")
                    if reply["status"] != "resolve":
                        raise RuntimeError(f"Optical worker failed on {identity}")
                    readout = page.evaluate("""async symbols => {
                      const {describeBarcodes} = await import('/package-reader.js');
                      const response = await fetch('/vendor/package-reader/registry.json');
                      if (!response.ok) throw Error('Registry unavailable');
                      return describeBarcodes(symbols, await response.json());
                    }""", reply["data"])
                    page.wait_for_function("document.querySelector('#package-barcode').textContent.includes('상품 확정')", timeout=10_000)
                    row = {"id": identity, "engine": browser.version, "symbols": reply["data"],
                           "decision": readout, "display": page.locator("#package-barcode").inner_text()}
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                    stream.flush()
            browser.close()
        finally:
            server.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["fetch", "python", "browser"])
    parser.add_argument("photos", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--chromium", help="System Chromium executable (default is Playwright Chromium)")
    args = parser.parse_args()
    verify_manifest()
    if args.stage == "fetch":
        fetch(args.photos)
    elif not args.out:
        parser.error("inference requires --out")
    elif args.stage == "python":
        infer_python(args.photos, args.out)
    else:
        infer_browser(args.photos, args.out, args.chromium)


if __name__ == "__main__":
    main()
