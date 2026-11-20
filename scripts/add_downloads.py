"""Copy the current review pages and preserved evaluation downloads into a static release."""
import argparse
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
    for name in ("index.html", "styles.css", "evidence.html", "evidence.css", "grocery-catalogue.js", "labels.html", "handoff.partial.html"):
        shutil.copy2(web / name, args.dist / name)
    (args.dist / "data").mkdir(exist_ok=True)
    for name in ("grocery-catalogue.json", "grocery-previous-photos.json"):
        shutil.copy2(web / "data" / name, args.dist / "data" / name)
    shutil.copytree(web / "data/role", args.dist / "data/role", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
