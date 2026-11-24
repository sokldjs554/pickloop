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
