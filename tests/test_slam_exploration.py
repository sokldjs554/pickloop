import json
import subprocess
import sys

from pickloop.mobile import ROOT


def test_online_frontier_run_reveals_more_cells_without_preloaded_map(tmp_path):
    subprocess.run([sys.executable, 'scripts/run_slam_exploration.py', '--out-dir', str(tmp_path)], cwd=ROOT, check=True)
    report = json.loads((tmp_path / 'summary.json').read_text())
    assert report['status'] == 'FRONTIER_BUDGET_REACHED'
    assert report['initial_free_cells'] > 0
    assert report['final_free_cells'] > report['initial_free_cells'] + 100
    assert len(report['legs']) == 2
    assert all(leg['status'] == 'GOAL_REACHED' for leg in report['legs'])
    assert report['truth_travel_m'] > 1.
    assert report['truth_min_body_clearance_m'] > .10
    assert report['stopped']
