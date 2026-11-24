"""Replay the frozen three-flavour gate on external photos and separate MuJoCo camera captures."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
import os
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image, ImageDraw

from pickloop.catalogue_features import CatalogueEncoder
from pickloop.catalogue_model import CatalogueHead
from pickloop.grocery_catalogue import DEFAULT_HEAD, resolve_decision
from pickloop.grocery_evaluation import PREFIX
from pickloop.juice_gate import APPLE, ORANGE, MIX, apply_juice_gate
from pickloop.photo_evaluation import crop_pixels, write_csv, write_json

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/experiments/juice-gate"
NAMES = (APPLE, ORANGE, MIX, "God-Morgon-Red-Grapefruit-Juice")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def fingerprints(rgb):
    y = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(y, (9, 8), interpolation=cv2.INTER_AREA)
    dh = int.from_bytes(np.packbits(small[:, 1:] > small[:, :-1]).tobytes(), "big")
    low = cv2.dct(cv2.resize(y, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32))[:8, :8].ravel()
    ph = int.from_bytes(np.packbits(low > np.median(low[1:])).tobytes(), "big")
    identity = sha256(f"{rgb.shape}|".encode() + rgb.tobytes()).hexdigest()
    return identity, ph, dh


def reference_pool(archive):
    old = []
    for path in archive.namelist():
        if path.startswith(PREFIX) and path.lower().endswith(".jpg"):
            data = archive.read(path)
            rgb, _ = crop_pixels(data, {})
            old.append((path[len(PREFIX):], sha256(data).hexdigest(), *fingerprints(rgb)))
    if len(old) != 5502:
        raise ValueError(f"expected 5502 registered reference files, found {len(old)}")
    return old


def external_inputs(archive, cases, image_root):
    old = reference_pool(archive)
    accepted = []
    screened = []
    checks = []
    for case in cases:
        image_id = case["sample_id"]
        data = (image_root / case["path"]).read_bytes()
        digest = sha256(data).hexdigest()
        if digest != case["sha256"]:
            raise ValueError(f"source checksum mismatch: {image_id}")
        rgb, _ = crop_pixels(data, {})
        identity, ph, dh = fingerprints(rgb)
        match = None
        nearest = None
        for path, byte_sha, pixel_sha, pp, dd in old:
            pd, hd = (ph ^ pp).bit_count(), (dh ^ dd).bit_count()
            if nearest is None or (max(pd, hd), pd+hd, path) < nearest[0]:
                nearest = ((max(pd, hd), pd+hd, path), path, pd, hd)
            if digest == byte_sha or identity == pixel_sha or (pd <= 4 and hd <= 4):
                match = path
                break
        checks.append(dict(id=image_id, sha256=digest, nearest=nearest[1], phash_distance=nearest[2],
                           dhash_distance=nearest[3], duplicate_of=match or ""))
        if match is None:
            accepted.append(("", image_id, "", digest, rgb))
            old.append((image_id, digest, identity, ph, dh))
        else:
            screened.append(("", image_id, "", digest, rgb))
    return accepted, screened, checks


def render_texture(rgb, angle, blocked):
    import mujoco
    from io import BytesIO

    buf = BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    occluder = ('<geom type="box" pos="0 0.015 0.022" size=".15 .033 .008" rgba=".4 .43 .45 1"/>'
                if blocked else "")
    xml = f"""<mujoco><visual><global offwidth="384" offheight="384" fovy="35"/>
      <headlight ambient=".7 .7 .7" diffuse=".4 .4 .4"/></visual>
      <asset><texture name="art" type="2d" file="art.png"/><material name="wrap" texture="art"
       texrepeat="1 1" specular="0" shininess="0"/></asset>
      <worldbody><camera name="rgb" pos="0 0 .50" xyaxes="1 0 0 0 1 0"/>
       <geom type="plane" size=".5 .5 .01" pos="0 0 -.022" rgba=".42 .45 .49 1"/>
       <body euler="0 {angle} 0"><geom type="box" size=".135 .135 .008" material="wrap"/></body>
       {occluder}</worldbody></mujoco>"""
    model = mujoco.MjModel.from_xml_string(xml, assets={"art.png": buf.getvalue()})
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    with mujoco.Renderer(model, height=384, width=384) as renderer:
        renderer.update_scene(data, camera="rgb")
        return renderer.render().copy()


def camera_inputs(archive, out):
    fixture = []
    known = read_csv(ROOT / "docs/experiments/grocery-catalogue/training.csv")
    registrations = dict(zip(NAMES, (14, 10, 8, 14)))
    for name in NAMES:
        fit = sorted((r for r in known if r["role"] == "fit" and r["truth"] == name and
                      not r["path"].endswith(f"_{registrations[name]:03}.jpg")), key=lambda r: r["path"])
        for r in ([fit[0]] if name == NAMES[-1] else [fit[0], fit[len(fit)//2]]):
            data = archive.read(PREFIX + r["path"])
            if sha256(data).hexdigest() != r["sha256"]:
                raise ValueError(f"camera artwork checksum mismatch: {r['path']}")
            rgb, _ = crop_pixels(data, {})
            fixture.append((name, r["path"], r["sha256"], rgb))
    img = Image.new("RGB", (348, 348), (45, 55, 92))
    pen = ImageDraw.Draw(img)
    pen.rectangle((55, 70, 293, 280), fill=(195, 127, 39))
    pen.text((75, 150), "FIELD HOUSE\nAPPLE & ORANGE", fill="white", font_size=23)
    synthetic = np.asarray(img)
    fixture.append(("UNKNOWN", "invented mixed-flavour carton artwork", fingerprints(synthetic)[0], synthetic))
    trials, provenance = [], []
    for i, (name, path, source_sha, rgb) in enumerate(fixture):
        for view, angle, blocked in (("front", 0, False), ("tilted", 15, False), ("occluded", 0, True)):
            image_id = f"camera-{i+1:02}-{view}"
            im = render_texture(rgb, angle, blocked)
            digest = sha256(im.tobytes()).hexdigest()
            if out is not None:
                out.mkdir(parents=True, exist_ok=True)
                Image.fromarray(im).save(out / f"{image_id}.png")
            trials.append(("simulation", image_id, name, digest, im))
            provenance.append(dict(id=image_id, truth=name, source=path, source_sha256=source_sha,
                                   view=view, rgb_sha256=digest))
    return trials, provenance


def score(trials, weights):
    encoder = CatalogueEncoder(weights)
    head = CatalogueHead.load(DEFAULT_HEAD)
    result = []
    for cohort, image_id, truth, digest, rgb in trials:
        generic, = head.predict(encoder.encode([rgb]))
        before = resolve_decision(generic, lambda: rgb)
        after = apply_juice_gate(before, lambda: rgb)
        result.append(dict(cohort=cohort, id=image_id, sha256=digest, truth=truth, raw_top1=generic["top1"],
                           before=before["prediction"], after=after["prediction"], decision_source=before["decision_source"],
                           score=generic["score"], margin=generic["margin"], support=generic["support"],
                           juice_gate_reason=after.get("juice_gate_reason", "outside_route"),
                           juice_gate_text=json.dumps(after.get("juice_gate_text", []), ensure_ascii=False)))
    return result


def state(truth, prediction):
    if prediction == "UNKNOWN":
        return "held"
    return "correct" if truth == prediction else "wrong"


def stats(rows):
    transitions = Counter((state(r["truth"], r["before"]), state(r["truth"], r["after"])) for r in rows)
    summary = {"total": len(rows), "known": sum(r["truth"] != "UNKNOWN" for r in rows)}
    for method in ("before", "after"):
        calls = Counter(state(r["truth"], r[method]) for r in rows)
        summary[method] = {k: calls[k] for k in ("correct", "wrong", "held")}
        summary[method]["coverage"] = (calls["correct"] + calls["wrong"]) / len(rows)
        summary[method]["unknown_false_accepts"] = sum(r["truth"] == "UNKNOWN" and r[method] != "UNKNOWN" for r in rows)
    summary["wrong_to_hold"] = transitions["wrong", "held"]
    summary["wrong_to_correct"] = transitions["wrong", "correct"]
    summary["correct_to_hold"] = transitions["correct", "held"]
    summary["new_wrong"] = transitions["correct", "wrong"] + transitions["held", "wrong"]
    summary["routed"] = sum(r["juice_gate_reason"] != "outside_route" for r in rows)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--external-manifest", type=Path)
    parser.add_argument("--external-root", type=Path)
    parser.add_argument("--out", default=EVIDENCE, type=Path)
    parser.add_argument("--camera-output", type=Path)
    parser.add_argument("mode", choices=["external", "camera", "historical"])
    args = parser.parse_args()
    os.environ.setdefault("MUJOCO_GL", "egl")
    cv2.setNumThreads(1)
    hashes = {
        ROOT / "src/pickloop/juice_gate.py": "9b9c2dca045935d794c1bf291426dd4887b57896d31ad2d09f084a79e525aab5",
        DEFAULT_HEAD: "55b1af5108cb748b05702f14976a9bee471872730ce5221ad2c9be16a906fcd1",
    }
    for path, digest in hashes.items():
        if sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"frozen method changed: {path.name}")
    screened = []
    args.out.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.archive) as archive:
        if args.mode == "external":
            if args.external_manifest is None or args.external_root is None:
                parser.error("external mode needs --external-manifest and --external-root")
            blind = args.external_manifest.with_name("blind-inputs.csv")
            if (sha256(blind.read_bytes()).hexdigest() != "0a8c69b9074682ab2e413a0bcb89dadbd977bc320b3fbaa1612efa7e10034aac"
                or sha256(args.external_manifest.read_bytes()).hexdigest() != "fa6a3f32e0d98881621ebb48c57502916cb7b95eede614cc79a668e5a244db7d"):
                raise ValueError("external source manifest differs from the frozen independent selection")
            trials, screened, validation = external_inputs(archive, read_csv(blind), args.external_root)
            write_csv(args.out/"deduplication.csv", validation)
        elif args.mode == "historical":
            previous = read_csv(ROOT / "docs/experiments/grocery-catalogue/predictions.csv")
            selected = [r for r in previous if r["split"] == "test" and r["truth"] == MIX]
            if len(selected) != 19:
                raise ValueError("historical cohort must contain all 19 official mixed-juice test photos")
            trials = []
            for row in selected:
                data = archive.read(PREFIX + row["path"])
                if sha256(data).hexdigest() != row["sha256"]:
                    raise ValueError(f"historical photo differs from frozen source: {row['path']}")
                rgb, _ = crop_pixels(data, {})
                trials.append(("previously inspected official test", row["path"], MIX, row["sha256"], rgb))
        else:
            trials, validation = camera_inputs(archive, args.camera_output)
            write_csv(args.out/"camera-sources.csv", validation)
    rows = score(trials + screened, args.weights)
    if args.mode == "external":
        gold = {r["sample_id"]: r for r in read_csv(args.external_manifest)}
        for row in rows:
            source = gold[row["id"]]
            if source["sha256"] != row["sha256"]:
                raise ValueError("gold and blind image digests disagree")
            row.update(cohort=source["capture_type"], truth=source["truth"])
        if screened:
            excluded_ids = {trial[1] for trial in screened}
            excluded_rows = [r for r in rows if r["id"] in excluded_ids]
            write_csv(args.out/"external-screened-predictions.csv", excluded_rows)
            rows = [r for r in rows if r["id"] not in excluded_ids]
    if not rows:
        raise ValueError("no eligible trials")
    write_csv(args.out/f"{args.mode}-predictions.csv", rows)
    cohorts = defaultdict(list)
    for row in rows:
        cohorts[row["cohort"]].append(row)
    summary = {"mode": args.mode, "overall": stats(rows), "by_cohort": {k: stats(v) for k,v in cohorts.items()}}
    write_json(args.out/f"{args.mode}-summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
