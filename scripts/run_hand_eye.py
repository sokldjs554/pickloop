#!/usr/bin/env python3
"""Run an eye-in-hand benchmark with raw USDA images or a seeded synthetic board."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from pickloop.geometry import scara_fk
from pickloop.hand_eye import fit_hand_eye, score_poses

USDA_SHA256 = "5ea8ab9b0781ea4431d5ea0316d0df695c1b0244eb7b22d6341a6f241c3a279d"


def transform(rotation, translation):
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = rotation.as_matrix(), translation
    return matrix


def grid(columns, rows, spacing):
    return np.array([[x * spacing, y * spacing, 0.] for y in range(rows) for x in range(columns)])


def project(board, camera_T_target, intrinsics, distortion):
    rotation = Rotation.from_matrix(camera_T_target[:3, :3]).as_rotvec()
    uv, _ = cv2.projectPoints(board, rotation, camera_T_target[:3, 3], intrinsics, distortion)
    return uv.reshape(-1, 2)


def synthetic_capture():
    mount = transform(Rotation.from_euler("xyz", [8, -12, 26], degrees=True), [.047, -.022, .086])
    target = transform(Rotation.from_euler("xyz", [5, -4, 92], degrees=True), [.42, .12, .085])
    board = grid(8, 6, .025)
    board -= board.mean(axis=0)
    intrinsics = np.array([[615., 0, 320], [0, 615, 240], [0, 0, 1]])
    views = []
    for split, count, seed in [("fit", 32, 641), ("heldout", 16, 1097)]:
        rng = np.random.default_rng(seed)
        for index in range(count):
            camera_T_target = transform(Rotation.from_euler("xyz", rng.uniform(-30, 30, 3), degrees=True),
                                        rng.uniform([-.06, -.06, .44], [.06, .06, .66]))
            robot = target @ np.linalg.inv(camera_T_target) @ np.linalg.inv(mount)
            noise = transform(Rotation.from_rotvec(rng.normal(0, np.deg2rad(.03), 3)), rng.normal(0, .0001, 3))
            pixels = project(board, camera_T_target, intrinsics, None)
            pixels += rng.normal(0, .25, pixels.shape)
            if not np.all((pixels >= 0) & (pixels < [640, 480])):
                raise ValueError("Synthetic board left the field of view")
            views.append({"id": f"{split}-{index:02}", "split": split,
                          "base_T_tool": (robot @ noise).tolist(), "pixels": pixels.tolist()})
    return {"name": "synthetic", "board_m": board.tolist(), "image_size": [640, 480],
            "intrinsics": intrinsics.tolist(), "views": views}, mount


def extract_usda(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != USDA_SHA256:
        raise ValueError("Expected the original USDA DS1.zip archive")
    with zipfile.ZipFile(path) as archive:
        numbers = np.fromstring(archive.read("DS1/robot_cali.txt").decode(), sep=" ")
        pose_count = int(numbers[0])
        wrist_T_base = numbers[1:].reshape(pose_count, 4, 4)
        wrist_T_base[:, :3, 3] /= 1000.  # Source poses and board dimensions use millimetres.
        views = []
        for i, robot in enumerate(wrist_T_base):
            key = f"image{i}.png"
            image = cv2.imdecode(np.frombuffer(archive.read(f"DS1/images/camera0/{key}"), np.uint8),
                                 cv2.IMREAD_GRAYSCALE)
            found, corners = cv2.findChessboardCorners(image, (8, 6))
            if not found:
                raise ValueError(f"Chessboard detection failed on {key}")
            cv2.cornerSubPix(image, corners, (3, 3), (-1, -1),
                             (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, .001))
            # The long board axis points toward the top of the image in DS1.
            # Make the corner IDs agree across views of this symmetric pattern.
            pixels = corners.reshape(-1, 2)
            if pixels[7, 1] > pixels[0, 1]:
                pixels = pixels[::-1]
            views.append({"id": key, "split": "heldout" if i % 4 == 3 else "fit",
                          "base_T_tool": np.linalg.inv(robot).tolist(), "pixels": pixels.tolist()})
    return {"name": "usda", "source": "https://doi.org/10.15482/USDA.ADC/1340592",
            "archive_sha256": USDA_SHA256, "license": "U.S. Public Domain",
            "board_m": grid(8, 6, .0285).tolist(), "image_size": [640, 480], "views": views}


def rms(values):
    return float(np.sqrt(np.mean(np.square(values))))


def evaluate(data):
    board = np.array(data["board_m"])
    views = data["views"]
    split = np.array([view["split"] for view in views])
    if len({view["id"] for view in views}) != len(views) or set(split) != {"fit", "heldout"}:
        raise ValueError("Expected unique IDs and a fit/heldout split")
    fitting, held = split == "fit", split == "heldout"
    robot = np.array([view["base_T_tool"] for view in views])
    corners = np.array([view["pixels"] for view in views], dtype=float)
    if "intrinsics" in data:
        intrinsics, distortion = np.array(data["intrinsics"]), np.zeros(5)
    else:
        _, intrinsics, distortion, _, _ = cv2.calibrateCamera(
            [board.astype(np.float32)] * sum(fitting), list(corners[fitting].astype(np.float32)),
            tuple(data["image_size"]), None, None,
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-9),
        )
    measured, pnp_errors = [], []
    for points in corners:
        ok, rvec, tvec = cv2.solvePnP(board, points, intrinsics, distortion, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            raise ValueError("PnP failed")
        estimate = transform(Rotation.from_rotvec(rvec.ravel()), tvec.ravel())
        if np.min((board @ estimate[:3, :3].T + tvec.ravel())[:, 2]) <= 0:
            raise ValueError("Board behind the camera")
        measured.append(estimate)
        pnp_errors.append(rms(np.linalg.norm(project(board, estimate, intrinsics, distortion) - points, axis=1)))
    measured = np.array(measured)
    fit = fit_hand_eye(robot[fitting], measured[fitting])
    errors = score_poses(fit, robot[held], measured[held])
    # Only robot pose, the camera model and the two fitting transforms enter this prediction.
    predicted_camera_T_target = np.linalg.inv(robot[held] @ fit.tool_T_camera) @ fit.base_T_target
    predicted = np.array([project(board, pose, intrinsics, distortion) for pose in predicted_camera_T_target])
    pixel_errors = np.linalg.norm(predicted - corners[held], axis=2)
    ids = np.array([v["id"] for v in views])
    report = {
        "name": data["name"], "solver": "OpenCV Park-Martin AX=XB", "opencv": cv2.__version__,
        "fit_ids": ids[fitting].tolist(), "heldout_ids": ids[held].tolist(),
        "tool_T_camera": fit.tool_T_camera.tolist(), "base_T_target": fit.base_T_target.tolist(),
        "rotation_excitation_deg": fit.rotation_excitation_deg.tolist(),
        "intrinsics": intrinsics.tolist(), "distortion": distortion.ravel().tolist(),
        "heldout": {"translation_rms_mm": rms(errors["translation_mm"]),
                    "rotation_rms_deg": rms(errors["rotation_deg"]),
                    "prediction_reprojection_rms_px": rms(pixel_errors),
                    "per_view_pnp_reprojection_rms_px": rms(np.array(pnp_errors)[held]),
                    "corner_count": int(pixel_errors.size)},
        "heldout_per_view": [
            {"id": name, "translation_mm": translation, "rotation_deg": angle,
             "prediction_reprojection_rms_px": rms(pixels), "pnp_reprojection_rms_px": pnp}
            for name, translation, angle, pixels, pnp in zip(
                ids[held], errors["translation_mm"], errors["rotation_deg"], pixel_errors, np.array(pnp_errors)[held])
        ],
    }
    return report, predicted


def scara_negative_control(mount):
    robot = []
    target = np.eye(4)
    for i in range(12):
        q = [.12 * i, .18 + .08 * i, -.13 - .01 * i, -.02 * i]
        robot.append(transform(Rotation.from_euler("z", q[0] + q[1] + q[3]), scara_fk(q)))
    camera = np.linalg.inv(np.array(robot) @ mount) @ target
    try:
        fit_hand_eye(robot, camera)
    except ValueError as exc:
        if "INSUFFICIENT_ROTATION" not in str(exc):
            raise
        return {"poses": len(robot), "rejected": True, "reason": str(exc)}
    raise RuntimeError("SCARA yaw-only motion unexpectedly returned a 6-DoF estimate")


def write_overlay(archive_path, data, predicted, output):
    view = next(v for v in data["views"] if v["split"] == "heldout")
    with zipfile.ZipFile(archive_path) as archive:
        raw = archive.read("DS1/images/camera0/" + view["id"])
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    for measured, prediction in zip(view["pixels"], predicted[0]):
        point = tuple(np.rint(measured).astype(int))
        cv2.circle(image, point, 3, (55, 200, 60), 1, cv2.LINE_AA)
        cv2.drawMarker(image, tuple(np.rint(prediction).astype(int)), (10, 110, 255), cv2.MARKER_CROSS, 5, 1)
    cv2.rectangle(image, (0, 0), (639, 29), (26, 28, 27), -1)
    cv2.putText(image, f"USDA DS1 {view['id']}  |  green: measured   orange: predicted",
                (9, 20), cv2.FONT_HERSHEY_SIMPLEX, .49, (242, 242, 242), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(output), image):
        raise OSError(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--usda-zip", type=Path, help="Original USDA DS1.zip")
    group.add_argument("--observations", type=Path, help="Replay an exported observation file")
    parser.add_argument("--out-dir", type=Path, default=Path("runs/hand-eye"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    mount = None
    if args.observations:
        data = json.loads(args.observations.read_text())
    elif args.usda_zip:
        data = extract_usda(args.usda_zip)
    else:
        data, mount = synthetic_capture()
    report, predicted = evaluate(data)
    if mount is not None:
        fitted = np.array(report["tool_T_camera"])
        delta = np.linalg.inv(mount) @ fitted
        report["simulation_truth_error"] = {"translation_mm": 1000 * np.linalg.norm(delta[:3, 3]),
                                            "rotation_deg": np.rad2deg(Rotation.from_matrix(delta[:3, :3]).magnitude())}
        report["degenerate_scara"] = scara_negative_control(mount)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    name = data["name"]
    if name not in {"synthetic", "usda"}:
        raise ValueError("Unrecognized experiment name")
    if not args.observations:
        (args.out_dir / f"{name}-observations.json").write_text(json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n")
    if args.usda_zip:
        write_overlay(args.usda_zip, data, predicted, args.out_dir / "usda-heldout-image3.jpg")
    (args.out_dir / f"{name}-report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report["heldout"], indent=2))


if __name__ == "__main__":
    main()
