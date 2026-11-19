#!/usr/bin/env python3
"""Run the two-AMR charging mission and save its mobile and electrical telemetry."""
import argparse
import json

from pickloop.dock_charging import SCENARIOS, run_dock_fleet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--scenario', choices=SCENARIOS, default='normal')
    parser.add_argument('--initial-soc', nargs=2, type=float, metavar=('AMR1', 'AMR2'), default=(.198, .199),
                        help='initial battery fractions, one per vehicle')
    parser.add_argument('--out-dir', default='runs/dock-charging')
    parser.add_argument('--mission-id')
    result = run_dock_fleet(**vars(parser.parse_args()))
    print(json.dumps({k: result[k] for k in ('mission_id', 'status', 'reason', 'batteries', 'final_zone')}, indent=2))
    return 0 if result['status'] == 'COMPLETED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
