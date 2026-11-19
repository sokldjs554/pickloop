"""Run and compare small paired PickLoop experiments in the learner's own copy."""
import argparse
import difflib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "src/pickloop/engine.py"
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MUJOCO_GL", "egl")
CASES = [
    ("path_blocked", "reobserve"), ("path_blocked", "recovery"),
    ("calibration_error", "recovery"), ("normal", "recovery"),
    ("suction_permanent", "recovery"),
]


def execute(folder, seed):
    from pickloop.conditions import make_condition
    from pickloop.engine import run_job

    folder.mkdir(parents=True, exist_ok=False)
    (folder / "engine.py.txt").write_bytes(ENGINE.read_bytes())
    rows = []
    for fault, policy in CASES:
        condition = make_condition(seed, fault, "development")
        result = run_job(seed=seed, fault=fault, policy=policy, out_dir=folder,
                         condition=condition, record=False)
        metrics = result["metrics"]
        run_id = result["run_id"]
        print(f"\n{fault} / {policy} / {run_id}", flush=True)
        trace = folder / run_id / "events.jsonl"
        for line in trace.read_text().splitlines():
            event = json.loads(line)
            kind, data = event["event"], event["data"]
            if kind in {"STATE_FAILED", "RECOVERY_BEGIN", "RECOVERY_END", "HOLD_POLICY",
                        "PLACEMENT_VERIFIED", "TERMINAL"}:
                detail = data.get("action") or data.get("reason") or ""
                print(f"  {event['sim_time']:7.3f}s  시도 {event['attempt']}  {kind} {detail}")
        row = {key: result[key] for key in ("run_id", "seed", "fault", "policy", "condition_id",
                                              "status", "reason", "sim_duration_s", "retries")}
        row.update({k: metrics[k] for k in ("collisions", "drops", "wrong_placements")})
        row["model_sha256"] = result["provenance"]["model_sha256"]
        row["stop_action"] = (result.get("terminal_policy") or {}).get("action")
        rows.append(row)
    (folder / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\n기록 {folder}/summary.json")


def compare(before, after):
    rows_a, rows_b = [json.loads((p / "summary.json").read_text()) for p in (before, after)]
    def indexed(rows):
        return {(r["condition_id"], r["policy"]): r for r in rows}
    left, right = indexed(rows_a), indexed(rows_b)
    if left.keys() != right.keys() or len(left) != len(CASES):
        raise SystemExit("조건 ID와 정책이 같은 두 개의 완료된 실험을 선택하세요.")
    if any(a["model_sha256"] != right[k]["model_sha256"] for k, a in left.items()):
        raise SystemExit("두 실행의 모델 파일이 다릅니다.")
    diff = list(difflib.unified_diff(
        (before / "engine.py.txt").read_text().splitlines(True),
        (after / "engine.py.txt").read_text().splitlines(True),
        fromfile="before/engine.py", tofile="after/engine.py"))
    (after / "engine.diff").write_text("".join(diff))
    print("".join(diff) or "두 실행의 engine.py가 같습니다.")
    for key, a in left.items():
        b = right[key]
        print(f"\n{a['fault']} / {a['policy']}")
        for row in (a, b):
            print(f"  {row['run_id']}  {row['status']} {row['reason'] or ''}  "
                  f"{row['sim_duration_s']:.3f}s  재시도 {row['retries']}  "
                  f"충돌 {row['collisions']}  낙하·강제분리 {row['drops']}  "
                  f"오배치 {row['wrong_placements']}  종료출력 {row['stop_action'] or '—'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("folder", type=Path)
    run.add_argument("--seed", type=int, choices=range(200, 210), default=200)
    pair = commands.add_parser("compare")
    pair.add_argument("before", type=Path)
    pair.add_argument("after", type=Path)
    args = parser.parse_args()
    if args.command == "compare":
        compare(args.before, args.after)
    elif args.folder.exists():
        parser.error("이 이름의 폴더가 이미 있습니다. 새 폴더 이름을 사용하세요.")
    else:
        execute(args.folder, args.seed)


if __name__ == "__main__":
    main()
