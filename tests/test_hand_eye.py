import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from scipy.spatial.transform import Rotation


def pose(angles, translation):
    matrix = np.eye(4)
    matrix[:3, :3] = Rotation.from_euler("xyz", angles, degrees=True).as_matrix()
    matrix[:3, 3] = translation
    return matrix


def calibration_pairs(yaw_only=False):
    # Generate a fixed target from a nontrivial camera mount and independent robot poses.
    mount = pose([10, -25, 35], [.043, -.012, .092])
    board = pose([12, 56, -87], [.44, -.27, .19])
    generator = np.random.default_rng(82)
    robot, camera = [], []
    for _ in range(16):
        angles = generator.uniform(-40, 40, 3)
        if yaw_only:
            angles[:2] = 0
        wrist = pose(angles, generator.uniform(-.4, .4, 3))
        robot.append(wrist)
        camera.append(np.linalg.inv(wrist @ mount) @ board)
    return mount, board, robot, camera


def test_recovers_camera_in_tool_and_predicts_a_board_outside_the_fit():
    from pickloop.hand_eye import fit_hand_eye, score_poses

    mount, board, robot, camera = calibration_pairs()
    fit = fit_hand_eye(robot[:10], camera[:10])
    np.testing.assert_allclose(fit.tool_T_camera, mount, atol=1e-9)
    np.testing.assert_allclose(fit.base_T_target, board, atol=1e-9)
    errors = score_poses(fit, robot[10:], camera[10:])
    assert max(errors["translation_mm"]) < 1e-5
    assert max(errors["rotation_deg"]) < 1e-5

    moved = board.copy()
    moved[:3, 3] += [.003, -.004, 0]
    moved_camera = np.linalg.inv(robot[-1] @ mount) @ moved
    error = score_poses(fit, [robot[-1]], [moved_camera])
    assert error["translation_mm"] == pytest.approx([5.0])
    assert error["rotation_deg"] == pytest.approx([0.0], abs=1e-6)


def test_rejects_parallel_axes_even_with_large_xyz_translations():
    from pickloop.hand_eye import fit_hand_eye

    _, _, robot, camera = calibration_pairs(yaw_only=True)
    with pytest.raises(ValueError, match="INSUFFICIENT_ROTATION"):
        fit_hand_eye(robot, camera)


def test_unpaired_poses_and_invalid_rotations_cannot_enter_fit():
    from pickloop.hand_eye import fit_hand_eye

    _, _, robot, camera = calibration_pairs()
    with pytest.raises(ValueError):
        fit_hand_eye(robot, camera[:-1])
    robot[0][:3, 0] *= -1
    with pytest.raises(ValueError):
        fit_hand_eye(robot, camera)


def test_cli_keeps_observations_replayable_and_scores_unseen_pixels(tmp_path):
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/run_hand_eye.py"),
                    "--out-dir", str(tmp_path)], cwd=root, check=True)
    report = json.loads((tmp_path / "synthetic-report.json").read_text())
    observations = json.loads((tmp_path / "synthetic-observations.json").read_text())
    fit_ids = set(report["fit_ids"])
    test_ids = set(report["heldout_ids"])
    assert fit_ids.isdisjoint(test_ids)
    assert fit_ids | test_ids == {view["id"] for view in observations["views"]}
    assert report["heldout"]["prediction_reprojection_rms_px"] < 2
    assert report["heldout"]["translation_rms_mm"] < 4
    assert report["degenerate_scara"]["rejected"]
    assert report["simulation_truth_error"]["translation_mm"] < 4


def test_physical_observations_replay_and_holdout_cannot_change_fit(tmp_path):
    root = Path(__file__).resolve().parents[1]
    runner = str(root / "scripts/run_hand_eye.py")
    source = root / "runs/hand-eye/usda-observations.json"
    baseline = json.loads((root / "runs/hand-eye/usda-report.json").read_text())
    captures = json.loads(source.read_text())
    assert len(captures["views"]) == 88
    for view in captures["views"]:
        if view["split"] == "heldout":
            view["pixels"] = (np.asarray(view["pixels"]) + [12, 6]).tolist()
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(captures))
    subprocess.run([sys.executable, runner, "--observations", str(altered),
                    "--out-dir", str(tmp_path)], cwd=root, check=True)
    report = json.loads((tmp_path / "usda-report.json").read_text())
    np.testing.assert_allclose(report["tool_T_camera"], baseline["tool_T_camera"], atol=1e-10)
    np.testing.assert_allclose(report["intrinsics"], baseline["intrinsics"], atol=1e-10)
    assert report["heldout"]["prediction_reprojection_rms_px"] > baseline["heldout"]["prediction_reprojection_rms_px"] + 7
