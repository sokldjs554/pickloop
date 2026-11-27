"""Publish measured results from the frozen external photo study."""
import argparse
import csv
import json
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
    reference = "https://github.com/marcusklasson/GroceryStoreDataset/blob/fc80ba90f803d79d0383df52c5a4ac5de99ff6fc/dataset/"
    studies = ROOT / "docs/experiments"
    with (studies / "registered-recall/archive-labels.csv").open(newline="") as stream:
        visual, = (row for row in csv.DictReader(stream) if row["id"] == "RR-787b9393075dd1b4")
    with (studies / "grocery-catalogue/training.csv").open(newline="") as stream:
        hold, = (row for row in csv.DictReader(stream)
                 if Path(row["path"]).name == "God-Morgon-Red-Grapefruit-Juice_001.jpg")
    enrolled = {row["sha256"] for row in read(studies / "registered-photo-recall/enrollment.json")}
    values = {}
    for label, filename, path, digest in (
        ("visual", "orange-side-store.jpg", visual["native_id"], visual["sha256"]),
        ("example", "grapefruit-front.jpg", hold["path"], hold["sha256"]),
    ):
        if sha256((MEDIA / filename).read_bytes()).hexdigest() != digest or digest in enrolled:
            raise ValueError(f"expected a credited non-enrollment photograph: {filename}")
        values[label + "_src"] = f"media/new-photos/{filename}"
        values[label + "_credit"] = " · ".join((
            external(reference + path, "Grocery Store Dataset 원본"),
            '<a href="media/new-photos/LICENSE-GroceryStoreDataset.txt">Marcus Klasson · MIT</a>'))
    return values


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


def store_photo_study():
    study = ROOT / "docs/experiments/store-package-recovery"
    records = {row["id"]: row for row in map(json.loads, (study / "field-browser.jsonl").read_text().splitlines())}
    scenes = [
        ("L01", "사과 1 L · 앞면 일부와 옆면"),
        ("L02", "오렌지·레드자몽 1 L · 앞면과 윗면"),
        ("L03", "미등록 사과 1.75 L · 같은 매대"),
        ("S01", "오렌지·레드자몽 1 L · 옆에 놓인 팩"),
        ("S02", "사과 1 L · 바코드가 보이지 않는 옆 팩"),
    ]
    rows = [(label, sku(records[key]["product"]) if records[key]["product"] else "보류") for key, label in scenes]
    return ("<h3>스웨덴 매장 사진 재시험</h3>"
            "<p>처음 세 입력은 보완에 사용했습니다. 마지막 두 입력은 같은 원본에서 옆에 놓인 팩을 잘라 시험했습니다. "
            "가격표는 입력에서 제외했습니다.</p>" + table(("촬영 조건", "브라우저 상품 판정"), rows)
            + side_lettering_study())


def side_lettering_study():
    studies = ROOT / "docs/experiments"
    ledgers = (studies / "side-panel-retry/browser.jsonl",
               studies / "side-print-evidence/browser.jsonl")
    predictions = []
    for path in ledgers:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        index = {row["id"]: row for row in rows}
        if len(index) != len(rows):
            raise ValueError(f"duplicate photo IDs in {path}")
        predictions.append(index)
    selected = {group: [] for group in ("apple", "orange", "mixed", "side", "front", "control")}
    with (studies / "registered-recall/archive-labels.csv").open(newline="") as source:
        for label in csv.DictReader(source):
            pair = tuple(ledger[label["id"]] for ledger in predictions)
            if any(row["sha256"] != label["sha256"] for row in pair):
                raise ValueError(f"photo checksum changed for {label['id']}")
            truth = label["truth"]
            if truth == "UNKNOWN":
                selected["control"].append(tuple(bool(row["product"]) for row in pair))
                continue
            outcome = tuple(row["product"] == truth for row in pair)
            if label["view"] == "front":
                selected["front"].append(outcome)
                continue
            if label["view"] != "side visible":
                raise ValueError(f"unhandled archive view for {label['id']}")
            selected["side"].append(outcome)
            if truth == "God-Morgon-Apple-Juice":
                selected["apple"].append(outcome)
            elif truth == "God-Morgon-Orange-Juice":
                selected["orange"].append(outcome)
            elif truth == "God-Morgon-Orange-Red-Grapefruit-Juice":
                selected["mixed"].append(outcome)

    labels = (("apple", "사과 1 L 옆면 정답"), ("orange", "오렌지 1 L 옆면 정답"), ("mixed", "오렌지·레드자몽 1 L 옆면 정답"),
              ("side", "등록 상품 전체 옆면 정답"), ("front", "등록 상품 전체 앞면 정답"),
              ("control", "미등록 레드자몽 오인"))
    scores = []
    for group, label in labels:
        outcomes = selected[group]
        scores.append((label, *(f"{sum(column)} / {len(outcomes)}장"
                                for column in zip(*outcomes, strict=True))))
    challenge = studies / "side-unknown-challenge"
    previous_rows = (challenge / "printed-titles/browser.jsonl").read_text().splitlines()
    previous = sum("미등록" in r["display"] or "목록 밖" in r["display"] for r in map(json.loads, previous_rows))
    outside = [json.loads(line) for line in (challenge / "foreground-titles/browser.jsonl").read_text().splitlines()]
    with (challenge / "blind.csv").open(newline="") as manifest:
        expected = {row["id"]: row["sha256"] for row in csv.DictReader(manifest)}
    if len(outside) != len(expected) or {row["id"]: row["sha256"] for row in outside} != expected:
        raise ValueError("Outside product replays do not match the frozen photo set")
    photos = len(outside)
    wrong_names = sum(bool(row["product"]) for row in outside)
    wrong_orders = sum(bool(row["barcode_order"]) for row in outside)
    positive = sum("미등록" in row["display"] or "목록 밖" in row["display"] for row in outside)
    return ("<h3>기존 매장 사진의 상품 인식 비교</h3>"
            "<p>같은 매장 사진을 두 판독기의 파일 선택창에 올렸습니다. 오렌지는 앞면과 이어진 옆면 인쇄를, "
            "혼합주스는 포장 글자 또는 같은 팩의 브랜드·뚜껑 아래 과일 무늬를 대조합니다.</p>"
            + table(("사진 조건", "이전 판독기(v28)", "이번 판독기"), scores)
            + "<p>새 매장에서 촬영한 전체 옆면 평가 사진은 사과 0건, 혼합주스 0건입니다.</p>"
            + f"<p>별도로 모은 미등록 유사 상품 사진 {photos}장에서 등록 상품명 오인은 {wrong_names}건, 잘못된 주문 확정은 {wrong_orders}건이었습니다. "
            + f"미등록 근거를 확인한 사진은 {previous}장에서 {positive}장으로 늘었고, {photos - positive}장은 보류했습니다. "
            + "새로 구별한 6장은 개선에 사용한 원본입니다. 이어 같은 상품의 다른 구도 9장을 재시험했습니다. 성분과 용량을 함께 읽는 판독기의 사진별 결과를 확인할 수 있습니다.</p>"
            + '<p><a href="https://github.com/sokldjs554/pickloop/tree/main/docs/experiments/side-print-evidence">옆면 사진별 판정</a> · '
            + '<a href="https://github.com/sokldjs554/pickloop/tree/main/docs/experiments/side-unknown-challenge/foreground-titles">미등록 앞면 결과</a> · <a href="https://github.com/sokldjs554/pickloop/tree/main/docs/experiments/side-unknown-challenge/alternate-views">다른 구도 9장과 기울기 시험</a> · <a href="https://colab.research.google.com/github/sokldjs554/pickloop/blob/main/docs/experiments/side-unknown-challenge/printed-titles/replay.ipynb">Colab에서 사진 재시험</a> · '
            + '<a href="https://github.com/sokldjs554/pickloop/tree/main/docs/experiments/short-retail-codes">서로 다른 바코드가 함께 보일 때의 주문 판정</a></p>')


def oblique_photo_study():
    scores = read(ROOT / "docs/experiments/oblique-packages/scores.json")["scores"]
    cohorts = (("archive_registered_side_visible", "옆면이 많이 보인 등록품", "correct_registered"),
               ("archive_registered_front", "앞면이 보인 등록품", "correct_registered"),
               ("archive_registered", "등록품 전체", "correct_registered"),
               ("archive_controls", "미등록 레드자몽에 등록 이름을 붙인 경우", "wrong_registered"))
    rows = []
    for key, label, outcome in cohorts:
        row = [label, scores["browser"][key]["n"]]
        for runtime in ("browser", "python"):
            pair = scores[runtime][key]
            row.append(f'{pair["baseline"][outcome]} → {pair["candidate"][outcome]}')
        rows.append(row)
    return ("<h3>이전 옆면 판독 실험 · v23</h3><p>같은 매장 사진을 v23과 그 이전 배포본에 각각 넣어 상품명을 비교했습니다. "
            "마지막 행은 미등록 상품에 등록 이름을 잘못 붙인 장수입니다. 같은 진열대에서 찍은 여러 장과 이전 개발에서 확인한 사진도 포함됩니다.</p>"
            + table(("촬영 조건", "사진 수", "브라우저 · 전 → 후", "Python · 전 → 후"), rows)
            + "<p>이전 버전을 평가한 매장 사진을 같은 조건으로 다시 읽었습니다. 한 상품을 여러 각도에서 찍은 사진이 포함되며, 새로 수집한 등록품 옆면 사진은 0장입니다.</p>"
            + '<p><a href="https://github.com/sokldjs554/pickloop/tree/main/docs/experiments/oblique-packages">사진별 판정·촬영 조건·재현 방법</a></p>')


def registered_photo_study():
    root = ROOT / "docs/experiments/registered-recall"
    web_registry = read(WEB / "vendor/package-reader/registry.json")
    sections = []
    for cohort, heading in (("archive", "공식 테스트 분할의 매장 사진"), ("public", "포장 추가 등록 전에 평가한 공개 사진")):
        with (root / f"{cohort}-labels.csv").open(newline="") as stream:
            labels = {row["id"]: row for row in csv.DictReader(stream)}
        results = []
        for method, title in (("browser", "브라우저"), ("model", "Python")):
            truth = {key: (web_registry.get(row["gtin"]) if method == "browser" else row["truth"])
                     for key, row in labels.items()}
            known = sum(value not in ("", None, "UNKNOWN") for value in truth.values())
            counts = []
            for revision in ("before", "production" if cohort == "archive" else "after"):
                prefix = f"{cohort}-browser-" if method == "browser" else cohort + "-"
                with (root / f"{prefix}{revision}.jsonl").open() as stream:
                    raw = [json.loads(line) for line in stream]
                if len(raw) != len(labels) or {row["id"] for row in raw} != labels.keys():
                    raise ValueError(f"Incomplete {cohort} {method} {revision} ledger")
                correct = wrong_known = wrong_unknown = held = 0
                for row in raw:
                    target = truth[row["id"]]
                    prediction = row["product"] if method == "browser" else row["ordinary"]["photo_name"]
                    if not prediction or prediction == "UNKNOWN":
                        held += 1
                    elif prediction == target:
                        correct += 1
                    elif target not in ("", None, "UNKNOWN"):
                        wrong_known += 1
                    elif prediction in web_registry.values():
                        wrong_unknown += 1
                counts.append((correct, wrong_known, wrong_unknown, held))
            formatted = [f"{a} → {b}" for a, b in zip(*counts, strict=True)]
            results.append((title, f"{formatted[0]} / {known}장", formatted[1],
                            f"{formatted[2]} / {len(labels) - known}장", formatted[3]))
        sections.append(f"<h3>{heading} {len(labels)}장</h3>"
                        + table(("실행 경로", "등록품 정답", "등록품에 다른 이름", "미등록에 등록 이름 부여", "보류"), results))
    # The update was prompted by these two cases. Keep the repeat outside the fresh-photo table.
    names = {"RR-08be70619c12080f": "제조사 사과 1 L · 새로 등록한 디자인", "RR-cbaea96197c4f7c6": "비스듬히 찍은 사과 1 L · 등록에 쓰지 않은 사진"}
    repeated = {}
    for stem in ("public-browser-production", "public-production"):
        with (root / f"{stem}.jsonl").open() as stream:
            repeated[stem] = {row["id"]: row for row in map(json.loads, stream)}
    cases = []
    for key, label in names.items():
        browser = repeated["public-browser-production"][key]
        model = repeated["public-production"][key]["ordinary"]
        cases.append((label, sku(browser["product"]) if browser["product"] else "보류",
                      sku(model["photo_name"]) if model["photo_name"] else "보류"))
    sections.append("<h3>두 사과 주스 사진의 후속 수정 확인</h3><p>제조사에서 확인한 새 포장을 등록하고, "
                    "1 L 표기가 반복해 읽히면 다른 용량의 경쟁 후보를 제외하도록 Python 판정을 수정했습니다. "
                    "같은 두 사진을 다시 사용한 결과입니다. 첫 사진은 새 기준 사진과 구도가 같아 독립 성능 집계에서 제외합니다.</p>"
                    + table(("다시 읽은 사진", "당시 브라우저 판정", "당시 Python 판정"), cases))
    return (store_photo_study() + oblique_photo_study() + '<details class="score-details"><summary>이전 등록 상품 판독 실험</summary>'
            + "<p>같은 원본 사진을 수정 전후에 한 장씩 입력했습니다. 매장 표는 바코드 중심 판독기와 옆면 보완 전 배포본의 상품명을 비교합니다. 공개 사진 표는 두 사과 사진을 검토하기 전에 동결한 첫 수정본까지의 비교입니다. "
            "Python은 주문품 외 식료품도 이름을 붙일 수 있습니다. 미등록품 열에는 등록 주문명을 잘못 붙인 경우만 셉니다. 주문 규격은 등록 바코드를 읽었을 때 별도로 확정합니다. 브라우저에는 250mL 시연 상품이 추가 등록돼 있습니다.</p>"
            + "".join(sections)
            + "<p>매장 사진의 상품 코드는 데이터셋이 각 품목에 연결한 ICA 상품 페이지에서 확인했습니다. "
              "같은 제품의 여러 각도가 있고 기준 사진과 촬영 환경이 비슷한 경우도 있습니다. 이 자료는 이전 프로젝트 평가에도 사용했습니다. 매장 사진 12장은 초기 브라우저 시험에 사용했고, 추가 27장은 개발 중 미리 확인한 사진입니다. "
              "기존에 보류했던 스웨덴산 1 L 오렌지 영양표 사진은 이번에 등록 자료로 사용해 새 정답 수에서 제외했습니다.</p></details>")


def fresh_size_study():
    report = read(ROOT / "docs/experiments/fresh-size-eval/public-summary.json")
    final = read(ROOT / "docs/experiments/fresh-size-eval/metrics.json")["final"]
    sections = []
    labels = {"dev": "개발 사진", "final": "최종 평가 사진"}
    for group in sorted(report["subsets"], key=lambda g: g["split"] != "final"):
        rows = []
        for key, label in (("before", "상품명 후보 · 수정 전"), ("after", "상품명 후보 · 수정 후"),
                           ("order", "주문 SKU 확정 · Python"), ("browser", "주문 SKU 확정 · 브라우저")):
            score = group[key]
            if score["correct"] + score["wrong"] + score["held"] != group["n"]:
                raise ValueError(f"photo counts differ for {group['split']}/{key}")
            rows.append((label, score["correct"], score["wrong"], score["held"]))
        block = (f"<h4>{labels[group['split']]} {group['n']}장</h4>"
                        f"<p class='score-summary'>상품명 정답 {group['before']['correct']} → {group['after']['correct']}장 · "
                        f"잘못 부여한 이름 {group['before']['wrong']} → {group['after']['wrong']}장</p>"
                        f"<p>이 중 Python 등록품은 {group['model_known']}장, "
                        f"250mL까지 등록한 브라우저의 등록품은 {group['web_known']}장입니다.</p>"
                        + table(("판정", "정답 상품명", "잘못 부여한 이름", "보류"), rows))
        if group["split"] == "final":
            block += (f"<p>최종 사진에서 눈으로 바코드가 보이는 {final['visibly_coded']}장 중 "
                      f"브라우저가 올바른 코드를 읽은 사진은 {final['visible_correctly_decoded']}장이었습니다. "
                      "두 사진 모두 미등록 상품이어서 주문 확정을 보류했습니다.</p>")
        if group["split"] == "dev":
            block = "<details><summary>개발 사진 결과 보기</summary>" + block + "</details>"
        sections.append(block)
    old = read(ROOT / "docs/experiments/size-review/results.json")["juice_33"]
    before, after = old["before"], old["after"]
    sections.append(f"<h4>설계에 사용한 기존 {old['photos']}장 재검사</h4>"
                    f"<p>미등록 {old['unknown']}장에 등록 이름을 잘못 붙인 경우는 "
                    f"{before['unknown_false_accept']} → {after['unknown_false_accept']}장, "
                    f"등록 {old['known']}장을 맞힌 경우는 {before['known_correct']} → "
                    f"{after['known_correct']}장이었습니다. 같은 맛·용량의 다른 상품 코드는 "
                    "포장 글자만으로 구분하기 어렵습니다.</p>")
    examples = []
    example_titles = {"registered_1l_reverse": "등록 1 L 뒷면", "demo_only_250ml_front": "시연용 250mL 앞면",
                      "unregistered_alternate_1l_front": "다른 코드의 1 L 앞면"}
    for item in report.get("examples", []):
        link = external(item["image_url"], example_titles[item["role"]])
        candidate = sku(item["photo_name"]) if item["photo_name"] else "보류"
        examples.append(f"<li>{link} · 실제 상품 코드 {safe(item['gtin'])} · "
                        f"수정 후 상품명 후보 {safe(candidate)}</li>")
    if examples:
        sections.append("<h4>결과를 사진과 대조하기</h4><ul>" + "".join(examples) + "</ul>")
    return ("<p>같은 실물 사진을 수정 전후로 읽었습니다. 개발과 최종 평가에는 서로 다른 상품 코드를 배정했습니다. "
            "이전 연구와 같은 상품이나 사진 제공처가 포함됩니다. 정답은 실제 상품에 등록 이름을 부여한 장수입니다. 보류에는 미등록 상품과 놓친 등록 상품이 모두 들어갑니다.</p>"
            + "".join(sections))


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
    with (ROOT / "docs/experiments/market-rival-retry/historical-paired.csv").open(newline="") as stream:
        current = list(csv.DictReader(stream))
    if {r["sha256"] for r in current} != {r["sha256"] for r in new_rows} or len(current) != len(new_rows):
        raise ValueError("latest comparison uses different juice photographs")
    known = [r for r in current if r["exact_truth"] != "UNKNOWN"]
    outside = [r for r in current if r["exact_truth"] == "UNKNOWN"]
    correct = sum(r["after_prediction"] == r["exact_truth"] for r in known)
    wrong = sum(r["after_prediction"] != "UNKNOWN" for r in outside)
    score_summary = (f'<p class="score-summary">현재 Python 판독기 · 등록 {len(known)}장 중 {correct}장 정답 / '
                     f'미등록 {len(outside)}장 중 {wrong}장에 등록 이름 부여</p>')
    with (STUDY / "rescan/labels.csv").open() as stream:
        confirm, = (row for row in csv.DictReader(stream) if row["gtin"] == "6415130089834")
    if sha256((MEDIA / "orange-250ml-original.jpg").read_bytes()).hexdigest() != confirm["sha256"]:
        raise ValueError("250 mL example differs from the credited photograph")
    confirm_credit = " · ".join((external(confirm["uploader_url"], confirm["uploader"]),
                                 external(confirm["image_url"], "Open Food Facts 원본"),
                                 external(confirm["licence_url"], "CC BY-SA 3.0")))
    return Template(TEMPLATE.read_text()).substitute(score_summary=score_summary, confirm_credit=confirm_credit, fresh_study=fresh_size_study(), registered_study=registered_photo_study(),
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
