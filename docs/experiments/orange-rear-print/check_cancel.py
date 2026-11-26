"""Cancel the real uploader while its supplemental English OCR worker is alive."""
import argparse
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import time

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("--web", type=Path, default=Path(__file__).resolve().parents[3] / "web")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    photo = args.photo.read_bytes()
    if sha256(photo).hexdigest() != "398059de4d64a3169d7550b97ae43d5ce37df4991595c8b2bafcca1f8146788a":
        raise ValueError("Supply the reviewed rear photo")
    handler = partial(SimpleHTTPRequestHandler, directory=str(args.web))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as playwright:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with playwright.chromium.launch(executable_path=args.chromium) as browser:
                protocol = browser.new_browser_cdp_session()
                protocol.send("Target.setDiscoverTargets", {"discover": True})
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/recognition.html")
                page.locator("#package-photo").set_input_files(
                    {"name": "rear.jpg", "mimeType": "image/jpeg", "buffer": photo}
                )
                page.locator("#package-reader button[type=submit]").click()
                workers, readers = set(), set()
                started = time.monotonic()
                while time.monotonic() - started < 119:
                    targets = protocol.send("Target.getTargets")["targetInfos"]
                    for target in targets:
                        if target["type"] == "worker":
                            workers.add(target["targetId"])
                            if target["url"].endswith("/ocr-worker.js"):
                                readers.add(target["targetId"])
                    if len(readers) >= 2:
                        page.locator("#package-cancel").click()
                        break
                    if not page.locator("#package-reader").get_attribute("aria-busy"):
                        break
                    page.wait_for_timeout(50)
                if len(readers) < 2:
                    raise RuntimeError("Did not observe the supplemental worker before the deadline")
                for _ in range(100):
                    targets = protocol.send("Target.getTargets")["targetInfos"]
                    remaining = workers.intersection(target["targetId"] for target in targets)
                    if not remaining:
                        break
                    page.wait_for_timeout(50)
                hidden = page.locator("#package-result").is_hidden()
                status = page.locator("#package-status").inner_text()
                if remaining or not hidden or "취소" not in status:
                    raise RuntimeError("The active upload, result or workers survived cancellation")
                print(json.dumps({"observed_workers": len(workers), "remaining_after_cancel": 0,
                                  "result_hidden": hidden, "visible_status": status}, ensure_ascii=False))
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
