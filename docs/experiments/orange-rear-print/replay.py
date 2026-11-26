"""Replay the additional rear-print verifier on hash-checked local photos using the shipped browser assets."""
import argparse
import csv
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent
WEB = HERE.parents[2] / "web"
PROBE = """
importScripts('opencv.js','orange-nutrition.js','orange-rear.js');
function scoped(run) {
  const mats=[];
  try {return run(mat=>{mats.push(mat);return mat;});}
  finally {for(const mat of mats.reverse())mat.delete();}
}
self.onmessage=async({data})=>{
  try {
    await new Promise(resolve=>cv.then(()=>resolve()));
    const registry=await (await fetch('registry.json')).json();
    const bitmap=await createImageBitmap(new Blob([data]));
    const canvas=new OffscreenCanvas(bitmap.width,bitmap.height),ctx=canvas.getContext('2d');
    ctx.drawImage(bitmap,0,0);bitmap.close();
    const frame=cv.matFromImageData(ctx.getImageData(0,0,canvas.width,canvas.height));
    try {postMessage({ok:true,result:await readOrangeRear(frame,registry)});}
    finally {frame.delete();}
  } catch(error) {postMessage({ok:false,error:String(error)});}
};
"""
READ_JS = """async bytes=>{
 const worker=new Worker('vendor/package-reader/probe.js');
 try {
  return await new Promise((resolve,reject)=>{
   worker.onmessage=({data})=>data.ok?resolve(data.result):reject(Error(data.error));
   worker.onerror=e=>reject(Error(e.message));
   worker.postMessage(Uint8Array.from(bytes));
  });
 } finally {worker.terminate();}
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photos", type=Path, help="Directory containing the input files by ID")
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, default=HERE / "inputs.csv")
    parser.add_argument("--web", type=Path, default=WEB)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    with TemporaryDirectory() as directory:
        web = Path(directory)
        vendor = web / "vendor/package-reader"
        vendor.mkdir(parents=True)
        for source in (args.web / "vendor/package-reader").iterdir():
            (vendor / source.name).symlink_to(source.resolve())
        (web / "data").symlink_to((args.web / "data").resolve())
        (web / "index.html").write_text("<!doctype html><title>Rear print replay</title>")
        (vendor / "probe.js").write_text(PROBE)
        handler = partial(SimpleHTTPRequestHandler, directory=directory)
        with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as playwright:
            Thread(target=server.serve_forever, daemon=True).start()
            try:
                with playwright.chromium.launch(executable_path=args.chromium) as browser:
                    page = browser.new_page()
                    page.goto(f"http://127.0.0.1:{server.server_port}/")
                    with args.manifest.open(newline="") as manifest, args.output.open("x") as output:
                        for row in csv.DictReader(manifest):
                            binary = (args.photos / row.get("path", row["id"])).read_bytes()
                            if sha256(binary).hexdigest() != row["sha256"]:
                                raise ValueError(f"Source hash mismatch for {row['id']}")
                            decision = page.evaluate(READ_JS, list(binary))
                            output.write(json.dumps({"id": row["id"], "result": decision}) + "\n")
                            output.flush()
            finally:
                server.shutdown()


if __name__ == "__main__":
    main()
