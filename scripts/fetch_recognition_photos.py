"""Reacquire original public images by frozen hash without redistributing the photographs."""
import argparse
import csv
import hashlib
import re
import shutil
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen


STUDY = Path(__file__).resolve().parents[1] / "docs/experiments/new-photos"


def download(row):
    request = Request(row["image_url"], headers={"User-Agent": "PickLoop photo evaluation reproduction/1.0"})
    with urlopen(request, timeout=60) as response:
        data = response.read()
    source_hash = row.get("source_sha256")
    if source_hash and hashlib.sha256(data).hexdigest() != source_hash:
        raise ValueError(f"publisher source checksum changed for {row['image_url']}")
    if row["image_url"].lower().endswith(".pdf"):
        from pypdf import PdfReader
        from pypdf.generic import IndirectObject
        match = re.search(r"\bxref\s+(\d+)\b", row["retrieval"])
        if not match:
            raise ValueError("PDF image object not specified in frozen manifest")
        pdf = PdfReader(BytesIO(data))
        obj = pdf.get_object(IndirectObject(int(match[1]), 0, pdf))
        if obj.get("/Subtype") != "/Image" or obj.get("/Filter") != "/DCTDecode":
            raise ValueError("expected original JPEG stream in source PDF")
        data = obj.get_data()
    elif row.get("pixel_sha256"):
        from PIL import Image
        with Image.open(BytesIO(data)) as photo:
            rgb = photo.convert("RGB")
            if hashlib.sha256(rgb.tobytes()).hexdigest() != row["pixel_sha256"]:
                raise ValueError("decoded control image differs from frozen pixels")
            if row.get("source_group", "").startswith("openimages-test:"):
                # The fresh test freeze strips embedded profiles after RGB decoding.
                rgb.info.clear()
            buffer = BytesIO()
            rgb.save(buffer, format="PNG")
            data = buffer.getvalue()
    return data


def cache_image(path, digest, row, fetch=download):
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return
    data = fetch(row)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"photo checksum changed for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        source = Path(tmp.name)
        tmp.write(data)
    try:
        source.replace(path)
    finally:
        source.unlink(missing_ok=True)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def photo_id(row):
    return row.get("id") or row["sample_id"]


def fetch_cohort(root, group, only):
    if group == "produce":
        inputs = STUDY.parent / "produce-rescue/original-blind.csv"
        labels = STUDY.parent / "produce-rescue/labels-joined-after.csv"
    else:
        inputs = STUDY / f"original-blind-{group}.csv"
        labels = STUDY / f"original-labels-{group}.csv"
    cases = read_csv(inputs)
    sources = {photo_id(row): row for row in read_csv(labels)}
    if only and only not in sources:
        raise ValueError(f"{only} is not in the frozen {group} manifest")
    directory = (root / group).resolve()
    for item in cases:
        identity = photo_id(item)
        if only and identity != only:
            continue
        path = (directory / item["path"]).resolve()
        if not path.is_relative_to(directory):
            raise ValueError(f"non-local path in blind manifest for {identity}")
        cache_image(path, item["sha256"], sources[identity])
        print(path, flush=True)
    if not only:
        shutil.copyfile(inputs, directory / "blind.csv")
        shutil.copyfile(labels, directory / "labels.csv")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--cohort", choices=("new", "prior", "control", "produce"))
    parser.add_argument("--id", help="download just one photo from the selected cohort")
    args = parser.parse_args()
    if args.id and not args.cohort:
        parser.error("--id needs a cohort")
    for group in ([args.cohort] if args.cohort else ["new", "prior", "control"]):
        fetch_cohort(args.cache, group, args.id)


if __name__ == "__main__":
    main()
