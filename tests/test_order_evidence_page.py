"""The public order examples and both comparison tables must point to the recorded evidence."""
import json
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_order_evidence_is_linked_from_both_entry_points():
    for name in ("index.html", "evidence.html"):
        elements = Elements((WEB / name).read_text()).elements
        assert any(tag == "a" and attrs.get("href") == "orders.html" for tag, attrs in elements)


def test_order_page_and_downloads_match_the_original_run_evidence():
    elements = Elements((WEB / "orders.html").read_text()).elements
    sections = {attrs.get("id") for tag, attrs in elements if tag == "section"}
    assert {"order-pick", "juice-check", "height-trial"} <= sections
    records = json.loads((ROOT / "runs/order-pick/index.json").read_text())["runs"]
    ids = [attrs["id"] for tag, attrs in elements if tag == "details" and attrs.get("name") == "order-case"]
    assert ids == [record["id"] for record in records]
    assert len(ids) >= 3
    assert any(tag == "video" and "controls" in attrs for tag, attrs in elements)
    links = {attrs.get("href") for tag, attrs in elements if tag == "a"}
    for row in records:
        assert "data/order-pick/" + row["result"] in links
    for _, attrs in elements:
        for key in ("href", "src", "poster"):
            uri = attrs.get(key, "")
            if uri.startswith("data/order-pick/"):
                source = ROOT / "runs" / uri.removeprefix("data/")
                assert (WEB / uri).read_bytes() == source.read_bytes(), uri


def test_fresh_photo_report_is_reachable_and_identifies_the_evidence():
    for path in ("index.html", "evidence.html", "orders.html"):
        links = Elements((WEB / path).read_text()).elements
        assert any(tag == "a" and attrs.get("href") == "recognition.html" for tag, attrs in links), path
    page = Elements((WEB / "recognition.html").read_text()).elements
    ids = {attrs.get("id") for tag, attrs in page if tag == "section"}
    assert {"new-photos", "photo-results", "try-photo"} <= ids
    assert any(tag == "a" and "experiments/new-photos" in attrs.get("href", "") for tag, attrs in page)


def test_browser_product_readout_links_to_separate_picking_and_defers_study_tables():
    html = (WEB / "recognition.html").read_text()
    page = Elements(html).elements
    assert ('a', {'href': 'orders.html#order-pick'}) in page
    assert 'id="order-pick"' in (WEB / 'orders.html').read_text()
    assert html.index('id="package-result" hidden') < html.index('href="orders.html#order-pick"') < html.index('id="package-text"')
    summary = html.index('현재 Python 판독기 · 등록 6장 중 4장 정답 / 미등록 27장 중 0장에 등록 이름 부여')
    assert html.index('id="new-photos"') < summary < html.index('<details class="score-details">', summary) < html.index('<table', summary)


def test_photo_benchmark_keeps_order_confirmation_separate_from_candidate_names():
    html = (WEB / "recognition.html").read_text()
    start = html.index('id="size-study"')
    study = html[start:html.index('id="new-photos"', start)]
    assert "<details" in study and "처음 보는 포장" in study
    assert "상품명 후보 · 수정 후" in study
    assert "주문 SKU 확정 · 브라우저" in study
    assert "주문 SKU 확정 · Python" in study
    assert "기존 33장 재검사" in study
    assert "docs/experiments/fresh-size-eval" in study


def test_visual_example_uses_a_credited_evaluation_photo_in_the_normal_reader():
    from hashlib import sha256
    import csv
    labels = ROOT / "docs/experiments/registered-recall/archive-labels.csv"
    with labels.open(newline="") as stream:
        row, = (item for item in csv.DictReader(stream) if item["id"] == "RR-787b9393075dd1b4")
    html = (WEB / "recognition.html").read_text()
    buttons = [attrs for tag, attrs in Elements(html).elements
               if tag == "button" and attrs.get("id") == "package-visual-example"]
    button, = buttons
    assert sha256((WEB / button["data-src"]).read_bytes()).hexdigest() == row["sha256"]
    assert row["native_id"] in html
    assert row["view"] == "side visible"
    with (ROOT / "docs/experiments/oblique-packages/paired.csv").open(newline="") as stream:
        decisions = [result for result in csv.DictReader(stream) if result["id"] == row["id"]]
    assert {result["runtime"] for result in decisions} == {"browser", "python"}
    for result in decisions:
        assert result["baseline_outcome"] != "correct_registered"
        assert result["candidate_name"] == row["truth"]
        assert not result["candidate_order"]
