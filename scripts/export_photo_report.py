"""Publish measured results from the frozen external photo study."""
import argparse
import csv
from hashlib import sha256
from itertools import groupby
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

from export_order_study import ROOT, WEB, name, read, safe, table


MEDIA = WEB / "media/new-photos"
STUDY = ROOT / "docs/experiments/new-photos"
TEMPLATE = Path(__file__).with_name("templates") / "recognition.html"
ROLES = {
    "new_primary": "새 사진 · 등록 제품과 미등록 대조품",
    "alternate_gtin_challenge": "같은 맛 · 다른 상품 코드",
    "prior_development": "개발에 사용한 이전 사진",
    "produce_control": "별도 생과일·채소 시험",
}
NAMES = {
    "Banana": "바나나", "Orange": "오렌지", "Cucumber": "오이", "Pineapple": "파인애플",
    "Carrots": "당근", "Carrot": "당근", "Avocado": "아보카도", "Lemon": "레몬",
    "Lime": "라임", "Paprika": "파프리카", "Red-Bell-Pepper": "빨간 파프리카",
    "Broccoli": "브로콜리", "Strawberry": "딸기",
    "Artichoke": "아티초크", "Pumpkin": "호박", "Kiwi": "키위", "Mango": "망고", "Aubergine": "가지", "UNKNOWN": "미등록",
}


VIEWS = {
    "front": "포장 앞면", "back": "포장 뒷면", "side": "포장 옆면",
    "side_back": "포장 옆·뒷면", "back_side": "포장 옆·뒷면",
    "barcode": "바코드 면", "ingredients": "성분 표시", "shelf": "진열 장면",
    "context": "주변이 보이는 제품 사진", "whole": "전체 모습", "unclassified": "별도 구분 없음",
}
ROUTES = {
    "baseline": "기존 인식기", "package_text": "포장 글자 확인",
    "registered_panel_and_text": "등록 포장 면·글자 확인", "barcode": "바코드 확인",
}


def view(value):
    return VIEWS.get(value, value)


def sku(value):
    return NAMES.get(value) or name(value)


def as_prediction(value):
    return "보류" if value == "UNKNOWN" else sku(value)


def external(url, label):
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"unusable source URL: {url}")
    return f'<a href="{safe(url)}" rel="noreferrer">{safe(label)}</a>'


def counts(rows):
    known = [r for r in rows if r["exact_truth"] != "UNKNOWN"]
    unknown = [r for r in rows if r["exact_truth"] == "UNKNOWN"]
    def score(key):
        return {
            "correct": sum(r[key] == r["exact_truth"] for r in known),
            "wrong": sum(r[key] not in (r["exact_truth"], "UNKNOWN") for r in known),
            "held": sum(r[key] == "UNKNOWN" for r in known),
            "false_accept": sum(r[key] != "UNKNOWN" for r in unknown),
        }
    return len(known), len(unknown), score("before_prediction"), score("after_prediction")


def metrics(rows):
    known, unknown, before, after = counts(rows)
    cards = (("등록 상품 정답", f"{after['correct']} / {known}"),
             ("등록 상품 보류", f"{after['held']} / {known}"),
             ("미등록 상품에 이름 부여", f"{after['false_accept']} / {unknown}"))
    block = "".join(f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in cards)
    content = [
        ("등록 상품을 맞힘", before["correct"], after["correct"], known),
        ("등록 상품을 다른 이름으로 판정", before["wrong"], after["wrong"], known),
        ("등록 상품을 보류", before["held"], after["held"], known),
        ("미등록 상품에 등록 이름을 붙임", before["false_accept"], after["false_accept"], unknown)]
    return (f'<p>Codespaces용 상품명 판별기를 고정한 뒤 채점한 새 주스 사진 {len(rows)}장입니다. 세 주스의 등록 기준은 '
            '제품 종류와 포장 규격입니다. 맛이 같아도 다른 규격에 등록 상품명을 붙이면 오답입니다.</p>'
            f'<dl class="metrics">{block}</dl>' + table(("판정", "기존", "수정 후", "대상 사진 수"), content))


def group_table(rows, field, heading):
    values = []
    for key, group in groupby(sorted(rows, key=lambda r: r[field]), key=lambda r: r[field]):
        known, unknown, before, after = counts(list(group))
        right = f"{before['correct']} → {after['correct']}" if known else "—"
        wrong = f"{before['false_accept']} → {after['false_accept']}" if unknown else "—"
        values.append((view(key), known, right, unknown, wrong))
    return table((heading, "등록 사진", "정답 전 → 후", "미등록 사진", "오수락 전 → 후"), values)


def detail_block(rows, role, readouts):
    if not rows:
        return ""
    items = []
    for row in rows:
        gold = sku(row["exact_truth"])
        if role == "alternate_gtin_challenge" and row.get("family_truth"):
            gold += f' · {sku(row["family_truth"])}와 같은 맛'
        extra = ""
        if row["id"] in readouts:
            evidence = readouts[row["id"]]
            labels = {"apple": "사과", "orange": "오렌지", "grapefruit": "자몽"}
            words = " · ".join(labels[w] for w in evidence["printed_fruit_words"]) or "없음"
            confirmed = sku(evidence["confirmed_order_sku"]) if evidence["confirmed_order_sku"] else "미확인"
            extra = f'<td>{safe(words)}</td><td>{safe(confirmed)}</td>'
        links = f'{external(row["image_url"], "사진")} · {external(row["source_url"], "출처")}'
        items.append(f'<tr><th scope="row">{safe(gold)}</th><td>{safe(view(row["view_type"]))}</td>'
                     f'<td>{safe(as_prediction(row["before_prediction"]))}</td>'
                     f'<td>{safe(as_prediction(row["after_prediction"]))}<br>'
                     f'<small>{safe(ROUTES.get(row["recognition_source"], row["recognition_source"]))}</small></td>'
                     f'{extra}<td>{links}</td></tr>')
    headers = ["등록 정답", "촬영 형태", "기존 판정", "수정 후 상품명"]
    if rows[0]["id"] in readouts:
        headers.extend(("반복해 읽힌 과일 단어", "바코드 규격"))
    headers.append("원본")
    head = "".join(f'<th scope="col">{title}</th>' for title in headers)
    return (f'<details><summary>{ROLES[role]} {len(rows)}장</summary><div class="table-wrap">'
            f'<table class="result-table"><thead><tr>{head}</tr></thead><tbody>{"".join(items)}</tbody>'
            '</table></div></details>')


def examples_html(records):
    rows = {row["id"]: row for row in records}
    cards = []
    for credit in read(MEDIA / "credits.json"):
        row = rows[credit["id"]]
        filename = credit["thumbnail"]
        if Path(filename).name != filename or not (MEDIA / filename).is_file():
            raise ValueError(f"missing licensed thumbnail for {row['id']}")
        if row["sha256"] != credit["original_sha256"]:
            raise ValueError(f"source hash mismatch for {row['id']}")
        description = sku(row["exact_truth"])
        if row["role"] == "alternate_gtin_challenge":
            description = f'{sku(row["family_truth"])} · 같은 맛의 미등록 규격'
        title = f'{description} · {view(row["view_type"])}'
        result = f'{as_prediction(row["before_prediction"])} → {as_prediction(row["after_prediction"])}'
        byline = external(credit["author_url"], credit["author"]) if credit["author_url"] else safe(credit["author"])
        cards.append(f'<figure><a href="{safe(row["image_url"])}"><img width="400" height="300" loading="lazy"'
                     f' src="media/new-photos/{safe(filename)}" alt="{safe(title)}"></a><figcaption>'
                     f'<strong>{safe(title)}</strong><br>{safe(result)}<br><small>축소본 · {byline} 제공 · '
                     f'{external(credit["licence_url"], credit["licence"])}</small></figcaption></figure>')
    return '<div class="examples">' + "".join(cards) + '</div>'


def reader_example():
    credit, = (row for row in read(MEDIA / "credits.json") if "reader_example" in row)
    filename = credit["reader_example"]
    if Path(filename).name != filename or sha256((MEDIA / filename).read_bytes()).hexdigest() != credit["original_sha256"]:
        raise ValueError("the one-click example must match the credited original")
    return {
        "example_src": f"media/new-photos/{safe(filename)}",
        "example_credit": " · ".join((
            external(credit["author_url"], credit["author"]),
            external(credit["original_url"], "Open Food Facts 원본"),
            external(credit["licence_url"], credit["licence"]),
        )),
    }


def make_thumbnails(directory):
    from PIL import Image, ImageOps
    photos = {}
    for location in directory.rglob("*"):
        if location.is_file() and location.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            data = location.read_bytes()
            photos[sha256(data).hexdigest()] = location
    for credit in read(MEDIA / "credits.json"):
        source = photos[credit["original_sha256"]]
        with Image.open(source) as original:
            thumb = ImageOps.exif_transpose(original).convert("RGB")
            thumb.thumbnail((480, 360), Image.Resampling.LANCZOS)
            thumb.save(MEDIA / credit["thumbnail"], "JPEG", quality=85, optimize=True)


def produce_study():
    study = ROOT / "docs/experiments/produce-rescue"
    summary = read(study / "summary.json")
    with (study / "results.csv").open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    if len(records) != summary["total"]:
        raise ValueError("produce rows differ from their scored population")
    rows = []
    for category, group in sorted(summary["by_source_class"].items()):
        before, after = (group["policies"][arm] for arm in ("before", "after"))
        if group["known"]:
            label, field = "등록 · 이름 정답", "correct_named"
        else:
            label, field = "미등록 · 잘못 이름 붙임", "outside_false_named"
        rows.append((sku(category), label, group["total"], before[field], after[field]))
    before, after = (summary["policies"][arm] for arm in ("before", "after"))
    return (f'<p>판별기를 고정한 뒤 별도로 모은 실물 사진 {summary["total"]}장을 확인했습니다. '
            f'등록된 바나나·오이·파인애플 {summary["known"]}장의 정답은 '
            f'<strong>{before["correct_named"]}장에서 {after["correct_named"]}장</strong>이었습니다. '
            f'미등록 {summary["outside"]}장에 잘못 이름을 붙인 수는 {before["outside_false_named"]}장에서 '
            f'{after["outside_false_named"]}장이었습니다.</p>' +
            table(("품목", "집계 기준", "사진 수", "기존 판정", "추가 확인 후"), rows))


def generate():
    with (STUDY / "rows.csv").open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    summary = read(STUDY / "summary.json")
    cohorts = {}
    for role in ROLES:
        cohort = [r for r in records if r["role"] == role]
        if not cohort:
            continue
        result = summary["roles"][role]
        known, unknown, before, after = counts(cohort)
        if (len(cohort), known, unknown, before["correct"], after["correct"]) != (
                result["n"], result["known"], result["unknown"], result["before"]["correct_names"],
                result["after"]["correct_names"]):
            raise ValueError(f"published rows differ from the aggregate for {role}")
        cohorts[role] = cohort
    if sum(map(len, cohorts.values())) != len(records):
        raise ValueError("rows with unexpected evaluation role")
    primary = cohorts["new_primary"]
    new_rows = primary + cohorts["alternate_gtin_challenge"]
    receipt = read(STUDY / "order-readouts.json")
    readouts = {row["id"]: row for row in receipt["rows"]}
    if set(readouts) != {row["id"] for row in new_rows} or receipt["total"] != len(new_rows):
        raise ValueError("strict identity readout does not cover the new juice photos")
    views = '<h3>등록 제품과 미등록 대조품 15장의 촬영 방향별 결과</h3>' + group_table(primary, "view_type", "촬영 형태")
    others = []
    for role, caption in (
        ("alternate_gtin_challenge", "용량이나 상품 코드가 다른 같은 맛 제품"),
        ("prior_development", "이전의 7장으로 수정 사항을 개발한 결과"),
        ("produce_control", "주스 외 일반 식료품을 따로 촬영한 사진")):
        if role not in cohorts:
            continue
        known, unknown, before, after = counts(cohorts[role])
        outcomes = []
        if known:
            outcomes.append(f"등록 {known}장 중 정답 {before['correct']} → {after['correct']}장")
        if unknown:
            outcomes.append(f"미등록 {unknown}장 중 오수락 {before['false_accept']} → {after['false_accept']}장")
        others.append((caption, " · ".join(outcomes)))
    return Template(TEMPLATE.read_text()).substitute(
        **reader_example(), produce=produce_study(), primary=metrics(new_rows), examples=examples_html(records), strata=views,
        other='<h3>별도로 측정한 사진</h3>' + table(("대상", "기존 → 수정 후"), others),
        details="".join(detail_block(rows, role, readouts) for role, rows in cohorts.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--thumbnails-from", type=Path, help="local directory containing the credited source photos")
    args = parser.parse_args()
    if args.thumbnails_from:
        make_thumbnails(args.thumbnails_from)
    page = WEB / "recognition.html"
    body = generate()
    if args.check:
        if page.read_text() != body:
            raise SystemExit("web/recognition.html differs from the original per-photo results")
    else:
        page.write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
