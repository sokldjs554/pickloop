"""Render the Korean review page from the three recorded studies, without running inference."""
import argparse
import csv
import html
import json
import shutil
from pathlib import Path
from string import Template
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PICKS = ROOT / "runs/order-pick"
EXPERIMENTS = ROOT / "docs/experiments"
TEMPLATE = Path(__file__).with_name("templates") / "orders.html"
FLAVOURS = {
    "God-Morgon-Orange-Juice": "오렌지주스",
    "God-Morgon-Orange-Red-Grapefruit-Juice": "오렌지·레드자몽 혼합주스",
    "God-Morgon-Red-Grapefruit-Juice": "레드자몽 단일 맛 주스",
    "God-Morgon-Apple-Juice": "사과주스",
    "Unregistered-Mint-Tea": "미등록 민트차",
    "UNKNOWN": "보류",
}
STAGES = {
    "OBSERVE": "전체 장면 관측", "APPROACH": "선택한 상품에 접근", "SEALED": "흡착 확인",
    "LIFTED": "상품 들어 올림", "TRANSPORTED": "상자 위로 운반", "PLACED": "상품 내려놓기",
    "RELEASED": "흡착 해제", "VERIFIED": "배치 확인", "HELD": "작업 보류",
}
SCENARIOS = {
    "orange": "기본 배치", "orange-swapped": "두 주스의 위치 교환",
    "mixed": "두 주스의 위치 교환", "mixed-standard": "기본 배치",
    "duplicate": "같은 맛·용량 두 개 중 한 개 주문", "wrong-volume": "주문과 다른 용량만 있음",
    "unspecified-volume": "같은 맛·다른 용량, 주문 용량 미지정", "unreadable-volume": "같은 맛 두 개, 용량 표기 없음", "unreadable": "맛 표시 가림", "absent": "주문 상품 없음",
}
REASONS = {
    "ORDER_NOT_FOUND": "주문과 일치한다고 확인한 상품이 없습니다.",
    "ORDER_VOLUME_MISMATCH": "읽은 용량과 주문한 용량이 다릅니다.",
    "ORDER_VOLUME_UNCONFIRMED": "두 번의 촬영에서 같은 용량을 확인할 수 없습니다.",
    "ORDER_VOLUME_AMBIGUOUS": "서로 다른 용량을 읽었고 주문에 용량이 없습니다.",
    "ORDER_NO_SAFE_APPROACH": "후보의 흡착면 여유 또는 접근 경로를 확보하지 못했습니다.",
    "ORDER_LABEL_UNCONFIRMED": "주문 후보의 포장 표기를 확인할 수 없습니다.",
    "RELEASE_NOT_CONFIRMED": "흡착 해제를 확인할 수 없습니다.",
    "EVALUATOR_DISAGREEMENT": "최종 물리 판정과 카메라 확인 결과가 다릅니다.",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe(value):
    return html.escape(str(value), quote=True)


def name(sku):
    return FLAVOURS.get(sku, sku or "없음")


def media_url(path):
    source = (PICKS / path).resolve()
    if not source.is_relative_to(PICKS) or not source.is_file():
        raise ValueError(f"missing or invalid camera evidence: {path}")
    return "data/order-pick/" + quote(source.relative_to(PICKS).as_posix())


def table(headers, rows):
    head = "".join(f'<th scope="col">{safe(item)}</th>' for item in headers)
    content = []
    for label, *values in rows:
        cells = "".join(f"<td>{safe(value)}</td>" for value in values)
        content.append(f'<tr><th scope="row">{safe(label)}</th>{cells}</tr>')
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(content)}</tbody></table></div>'


def figure(path, caption):
    src = media_url(path)
    return (f'<figure><a href="{src}"><img loading="lazy" src="{src}" alt="{safe(caption)}"></a>'
            f'<figcaption>{safe(caption)}</figcaption></figure>')


def receipt_html(result):
    selected = result["selected"]
    evaluation = result["evaluation"]
    trace = result["trace"]
    volume = result.get("order_volume_ml")
    facts = [("주문", f'{name(result["order_sku"])} {volume} mL × 1' if volume else name(result["order_sku"]) + " 1개 · 용량 미지정")]
    if selected:
        xyz = " / ".join(f"{v * 1000:.0f}" for v in selected["position_m"])
        facts.extend([("카메라 선택", name(selected["prediction"])), ("선택 좌표 X / Y / Z", xyz + " mm")])
    if selected and selected.get("volume_ml"):
        facts.append(("확인한 용량", f'{selected["volume_ml"]} mL'))
    selection = result.get("selection", {})
    if len(selection.get("matching_ids", [])) > 1:
        paths = [f'{c["candidate_id"]} {1000 * c["pick_plan"]["approach_distance_m"]:.1f} mm'
                 for c in result["candidates"] if c.get("pick_plan", {}).get("eligible")]
        facts.append(("안전 접근 후보", " / ".join(paths)))
        facts.append(("선택 근거", f'컵이 들어갈 면적과 접근 경로를 확인한 뒤 시작 위치에서 가장 가까운 {selected["candidate_id"]}를 선택했습니다.'))
    if result["reason"]:
        reason = result["reason"]
        facts.append(("보류 사유", REASONS.get(reason, reason)))
    issued = any(row["stage"] == "VALVE_COMMAND" and row.get("value") for row in trace)
    if issued:
        facts.append(("상자 안 상품", f'{name(evaluation["delivered_sku"])} · {evaluation["count_in_bin"]}개'))
        facts.append(("배치 확인", "카메라 재관측과 물리 판정 모두 일치" if
                      result["placement_camera"]["verified"] and evaluation["verified"] else "확인 미완료"))
    else:
        facts.append(("흡착 명령", "0회"))
    if result["reason"] == "ORDER_NOT_FOUND":
        in_scene = any(obj["sku"] == result["order_sku"] for obj in evaluation["objects"])
        facts.append(("실행 후 정답 대조", "주문 상품이 있었으나 식별에 실패했습니다." if in_scene else "주문 상품이 장면에 없었습니다."))
    facts.append(("종료 시 밸브", "열림" if trace[-1]["valve_on"] else "꺼짐"))
    items = "".join(f"<dt>{safe(key)}</dt><dd>{safe(value)}</dd>" for key, value in facts)
    return f"<dl>{items}</dl>"


def candidates_html(result, entry):
    directory = Path(entry["result"]).parent
    pictures = []
    for i, row in enumerate(result["candidates"], start=1):
        selected = result["selected"] and result["selected"]["candidate_id"] == row["candidate_id"]
        title = f"후보 {i} · {name(row['prediction'])}" + (" · 선택" if selected else "")
        interpreted = row["shipping_label"]["reads"]
        detail = f"인식기 {name(row['generic']['prediction'])}"
        if interpreted:
            detail += " · 라벨 읽기 " + " / ".join(interpreted)
        pictures.append(figure(directory / row["crop"], f"{title}. {detail}"))
    return ('<details><summary>카메라가 읽은 후보별 포장</summary>'
            f'<div class="candidates">{"".join(pictures)}</div></details>')


def case_html(entry, initial=False):
    result = read(PICKS / entry["result"])
    poster = media_url(entry["poster"])
    if entry.get("clip"):
        media = (f'<video controls playsinline muted preload="none" poster="{poster}" aria-label="로봇 작업 장면">'
                 f'<source src="{media_url(entry["clip"])}" type="video/mp4"></video>')
    else:
        media = f'<img class="still" src="{poster}" alt="피킹 시뮬레이션의 기록된 장면">'
    status = entry["status"]
    if status not in ("COMPLETED", "HELD") or status != result["status"]:
        raise ValueError(f"unexpected order outcome: {status}")
    done = status == "COMPLETED"
    state_label = "배치 완료" if done else "작업 보류"
    stages = entry["frames"]
    # Keep the recorded order when two consecutive stages have the same simulation time.
    captures = "".join(figure(step["image"], f'{STAGES.get(step["stage"], step["stage"])} · {step["sim_time_s"]:.2f}초')
                       for step in stages)
    return (f'<details class="order-case" name="order-case" id="{safe(entry["id"])}"{" open" if initial else ""}>'
            f'<summary>{safe(SCENARIOS.get(entry["id"],entry["id"]))} · {safe(name(entry["order_sku"]))}'
            f'<span class="{"" if done else "held"}">{state_label}</span></summary>'
            f'<div class="case-content"><div class="case-lead">{media}'
            f'{receipt_html(result)}</div>{candidates_html(result,entry)}'
            f'<details><summary>주요 시점의 원본 장면 {len(stages)}장</summary><div class="timeline">{captures}</div></details>'
            f'<div class="evidence-links"><a href="{media_url(entry["result"])}">이 실행의 판정·좌표·측정 원문</a></div></div></details>')


def juice_html():
    directory = EXPERIMENTS / "juice-gate"
    def counts(study, measure):
        return f"{study['before'][measure]} → {study['after'][measure]}"

    groups = (("historical", "기존에 틀린 혼합주스 사진"), ("external", "새로 수집한 외부 사진"),
              ("camera", "모의 카메라로 다시 찍은 포장"))
    rows, summaries = [], {}
    for key, label in groups:
        stats = read(directory / f"{key}-summary.json")["overall"]
        summaries[key] = stats
        rows.append((label, stats["total"], counts(stats, "correct"), counts(stats, "wrong"), counts(stats, "held")))
    scores = table(("사진 집합", "장수", "정답 전 → 후", "오답 전 → 후", "보류 전 → 후"), rows)
    with (directory / "external-manifest.csv").open() as handle:
        originals = list(csv.DictReader(handle))
    predictions = {}
    for filename in ("external-predictions.csv", "external-screened-predictions.csv"):
        with (directory / filename).open() as handle:
            for row in csv.DictReader(handle):
                predictions[row["id"]] = (row, filename == "external-predictions.csv")
    sources = []
    for original in originals:
        row, eligible = predictions[original["sample_id"]]
        truth = name(row["truth"]) if row["truth"] != "UNKNOWN" else "미등록 블러드오렌지·사과"
        status = "집계" if eligible else "유사 이미지 기준으로 제외"
        link = f'<a href="{safe(original["source_url"])}">{safe(original["source_name"])}</a>'
        sources.append(f'<li>{safe(truth)} · {safe(name(row["before"]))} → {safe(name(row["after"]))}'
                       f' · {safe(status)} · {link}</li>')
    hist, external, camera = (summaries[key] for key in ("historical", "external", "camera"))
    return (f'<p>고드 모르곤 주스 세 종류에 포장 글자 확인을 적용했습니다. 같은 사진을 적용 전후로 비교했습니다.</p>{scores}'
            f'<p>기존 오답 중 {hist["wrong_to_correct"]}장은 맛을 바로잡고 {hist["wrong_to_hold"]}장은 보류했습니다. '
            f'외부 사진 {len(originals)}장 중 유사 이미지 판별 기준을 통과한 {external["total"]}장은 '
            f'전후 모두 보류했습니다. 이 중 등록 상품은 {external["known"]}장입니다. '
            f'모의 카메라에서는 원래 정답이던 {camera["correct_to_hold"]}장까지 보류로 바뀌었습니다.</p>'
            f'<details><summary>외부 사진 {len(originals)}장의 출처와 개별 결과</summary><ul>{"".join(sources)}</ul></details>')


def height_html():
    study = read(EXPERIMENTS / "current-height/summary.json")
    before, after = (study["aggregate"][k] for k in ("before", "after"))
    labels = {"normal": "정상 작업", "suction_once": "일시적 흡착 실패",
              "path_blocked": "경로 차단", "suction_permanent": "지속 흡착 실패",
              "mixed": "흡착 장애와 경로 차단"}
    per_condition = {(r["scenario"], r["variant"]): r for r in study["by_condition"]}
    rows = []
    for key, title in labels.items():
        old, current = (per_condition[key, v] for v in ("before", "after"))
        rows.append((title, f'{old["completed"]}/{old["n"]} → {current["completed"]}/{current["n"]}',
                     f'{old["mean_sim_s"]:.3f}초', f'{current["mean_sim_s"]:.3f}초'))
    results = table(("조건", "완료 건수 · 전 → 후", "기존 평균", "현재 평균"), rows)
    def time_delta(key):
        return per_condition[key, "after"]["mean_sim_s"] - per_condition[key, "before"]["mean_sim_s"]

    return (f'<p class="finding">일시적 흡착 실패에서는 {abs(time_delta("suction_once")):.3f}초 단축됐고, '
            f'흡착 실패와 경로 차단이 겹치면 재시도가 늘어 {time_delta("mixed"):.3f}초 더 걸렸습니다.</p>'
            f'<p>Codex가 {before["n"]}쌍을 실행했습니다. 평균 시간은 완료와 보류를 모두 포함한 시뮬레이션 시간입니다.</p>{results}'
            f'<p>두 규칙 모두 {after["completed"]}/{after["n"]}건을 완료했습니다. 총 재시도는 '
            f'{before["retries"]}회에서 {after["retries"]}회로 바뀌었습니다. '
            f'전후 충돌 {before["collisions"]} → {after["collisions"]}건, '
            f'낙하·강제 분리 {before["drops"]} → {after["drops"]}건, '
            f'오배치 {before["wrong_placements"]} → {after["wrong_placements"]}건입니다.</p>')


def generate():
    records = read(PICKS / "index.json")["runs"]
    if not records:
        raise ValueError("no order recordings")
    return Template(TEMPLATE.read_text()).substitute(
        completed=sum(entry["status"] == "COMPLETED" for entry in records),
        held=sum(entry["status"] == "HELD" for entry in records),
        cases="\n".join(case_html(entry, i == 0) for i, entry in enumerate(records)),
        juice=juice_html(), height=height_html())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    page = WEB / "orders.html"
    published = WEB / "data/order-pick"
    html_text = generate()
    if args.check:
        if page.read_text() != html_text:
            raise SystemExit("web/orders.html is stale")
        for artifact in PICKS.rglob("*"):
            if artifact.is_file() and artifact.read_bytes() != (published / artifact.relative_to(PICKS)).read_bytes():
                raise SystemExit(f"stale published artifact: {artifact}")
    else:
        page.write_text(html_text, encoding="utf-8")
        shutil.copytree(PICKS, published, dirs_exist_ok=True)


if __name__ == "__main__":
    main()
