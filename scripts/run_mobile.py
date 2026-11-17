#!/usr/bin/env python3
"""Run the bounded mobile simulator and existing physics picker; no UI shortcuts."""
import argparse
import json

from pickloop.mobile import run_mission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--scenario', choices=['normal', 'blocked', 'zone_contention'], default='normal')
    parser.add_argument('--out-dir', default='runs/mobile')
    parser.add_argument('--mission-id')
    parser.add_argument('--sim-deadline-s', type=float, default=240.)
    parser.add_argument('--wall-deadline-s', type=float, default=120.)
    args = parser.parse_args()
    result = run_mission(**vars(args))
    print(json.dumps({key: result[key] for key in ('mission_id', 'job_id', 'status', 'reason', 'metrics')}, indent=2))
    return 0 if result['status'] == 'COMPLETED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
