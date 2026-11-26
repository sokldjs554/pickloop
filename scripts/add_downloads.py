"""Copy the current review pages and preserved evaluation downloads into a static release."""
import argparse
import json
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    web = Path(__file__).resolve().parents[1] / "web"
    downloads = args.dist / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archives = {
        "PickLoop-소스와-실행증거.zip": "pickloop-source.zip",
        "PickLoop-실행-데모.mp4": "pickloop-demo.mp4",
        "검증-결과.md": "summary.md",
        "비교-지표.json": "metrics.json",
        "원본-실행목록.csv": "trials.csv",
        "공고-대응표.md": "job-requirements.md",
        "PCB-경험-정리.md": "pcb-experience.md",
        "파일-검증.json": "checksums.json",
    }
    for name, target in archives.items():
        shutil.copy2(args.delivery / name, downloads / target)
    for name in ("index.html", "app.js", "styles.css", "evidence.html", "evidence.css", "grocery-catalogue.js", "work-scene.js", "work-scene.css", "labels.html", "handoff.partial.html", "orders.html", "orders.css", "recognition.html", "recognition.css", "recognition.js", "package-reader.js"):
        shutil.copy2(web / name, args.dist / name)
    shutil.copytree(web / "vendor/package-reader", args.dist / "vendor/package-reader", dirs_exist_ok=True)
    shutil.copytree(web / "media", args.dist / "media", dirs_exist_ok=True)
    (args.dist / "data").mkdir(exist_ok=True)
    for name in ("grocery-catalogue.json", "grocery-previous-photos.json", "featured-run.json",
                 "registered-pack-gallery.json", "registered-detail-gallery.json",
                 "registered-collar.json", "orange-side.json", "orange-nutrition.json", "orange-values.json", "outside-family.json"):
        shutil.copy2(web / "data" / name, args.dist / "data" / name)
    featured = json.loads((web / "data/featured-run.json").read_text())
    run_dir = Path("data/runs") / featured["run_id"]
    if run_dir.parent != Path("data/runs") or featured["run_url"] != (run_dir / "run.json").as_posix():
        raise ValueError("invalid featured run location")
    shutil.copytree(web / run_dir, args.dist / run_dir, dirs_exist_ok=True)
    shutil.copytree(web / "data/order-pick", args.dist / "data/order-pick", dirs_exist_ok=True)
    shutil.copytree(web / "data/role", args.dist / "data/role", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
