"""Replay blinded photographs through the shipped file chooser and record visible decisions."""
import argparse
import csv
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread

from PIL import Image
from playwright.sync_api import sync_playwright


def replay(web, manifest, photos, output, chromium):
    with manifest.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = [row["id"] for row in rows]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("expected distinct blind input IDs")
    registry = json.loads((web / "vendor/package-reader/registry.json").read_text())
    handler = partial(SimpleHTTPRequestHandler, directory=str(web))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as playwright:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with playwright.chromium.launch(executable_path=chromium) as browser, output.open("x") as result:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/recognition.html")
                identity = page.locator("#package-identity")
                for row in rows:
                    path = photos / row.get("path", row["id"])
                    binary = path.read_bytes()
                    if sha256(binary).hexdigest() != row["sha256"]:
                        raise ValueError(f"checksum mismatch for {row['id']}")
                    with Image.open(path) as image:
                        mime = Image.MIME[image.format]
                    page.locator("#package-photo").set_input_files({
                        "name": "photo." + mime.split("/")[-1], "mimeType": mime, "buffer": binary})
                    page.locator('#package-reader [type="submit"]').click()
                    page.wait_for_function("""() => {
                      const form = document.getElementById('package-reader');
                      return !form.hasAttribute('aria-busy') && !document.getElementById('package-result').hidden;
                    }""", timeout=135_000)
                    status = page.locator("#package-status").inner_text()
                    if "마쳤습니다" not in status:
                        raise RuntimeError(f"reader did not finish for {row['id']}: {status}")
                    optical = page.locator("#package-barcode").inner_text()
                    matched = re.search(r"^상품 확정 · .*등록 바코드 (\d{13})$", optical)
                    code = matched.group(1) if matched else None
                    name = identity.get_attribute("data-product") if identity.count() else registry.get(code)
                    source = identity.get_attribute("data-source") if identity.count() else ("barcode" if code else "none")
                    if source not in ("visual", "barcode", "none"):
                        raise RuntimeError(f"missing final decision for {row['id']}")
                    entry = {"id": row["id"], "sha256": row["sha256"], "product": name or None,
                             "source": source, "barcode_order": registry.get(code), "optical_display": optical,
                             "display": identity.inner_text() if identity.count() else optical, "chromium": browser.version}
                    result.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    result.flush()
        finally:
            server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="CSV with id, sha256, optional path")
    parser.add_argument("photos", type=Path)
    parser.add_argument("--web", type=Path, default=Path(__file__).resolve().parents[1] / "web")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chromium")
    args = parser.parse_args()
    replay(args.web, args.manifest, args.photos, args.out, args.chromium)
