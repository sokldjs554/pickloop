"""Eye-in-hand calibration. A_T_B maps coordinates from B to A, in metres."""

from dataclasses import dataclass

import cv2
import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class HandEyeFit:
    tool_T_camera: np.ndarray
    base_T_target: np.ndarray
    rotation_excitation_deg: np.ndarray


def _transforms(matrices):
    poses = np.asarray(matrices, dtype=float)
    if poses.ndim != 3 or poses.shape[1:] != (4, 4) or not np.isfinite(poses).all():
        raise ValueError("Expected an array of finite 4x4 transforms")
    rotations = poses[:, :3, :3]
    if not (np.allclose(poses[:, 3], [0, 0, 0, 1], atol=1e-8, rtol=0)
            and np.allclose(rotations.transpose(0, 2, 1) @ rotations, np.eye(3), atol=1e-5, rtol=0)
            and np.allclose(np.linalg.det(rotations), 1, atol=1e-5, rtol=0)):
        raise ValueError("Expected proper rigid transforms")
    return poses


def _pairs(base_T_tool, camera_T_target):
    robot, camera = _transforms(base_T_tool), _transforms(camera_T_target)
    if len(robot) != len(camera) or len(robot) == 0:
        raise ValueError("Expected paired robot and camera observations")
    return robot, camera


def _rotation_excitation(rotations):
    # Singular values of all relative rotation vectors expressed in the input frame.
    i, j = np.triu_indices(len(rotations), 1)
    relative = rotations[j].transpose(0, 2, 1) @ rotations[i]
    vectors = Rotation.from_matrix(relative).as_rotvec()
    return np.rad2deg(np.linalg.svd(vectors, compute_uv=False) / np.sqrt(len(vectors)))


def fit_hand_eye(base_T_tool, camera_T_target):
    """Fit X = tool_T_camera from G_i X C_i = Y for a stationary target.

    The OpenCV Park–Martin solver receives absolute G and C transforms. Their
    paired relative motions satisfy A X = X B with A = inv(G_j) G_i and
    B = C_j inv(C_i). Y uses only the supplied fitting poses.
    """
    robot, camera = _pairs(base_T_tool, camera_T_target)
    if len(robot) < 3:
        raise ValueError("At least three paired poses required")
    excitation = _rotation_excitation(robot[:, :3, :3])
    if excitation[1] < 2.0 or excitation[1] < 0.05 * excitation[0]:
        raise ValueError(f"INSUFFICIENT_ROTATION: second independent RMS component {excitation[1]:.3f} deg")

    rotation, translation = cv2.calibrateHandEye(
        robot[:, :3, :3], robot[:, :3, 3], camera[:, :3, :3], camera[:, :3, 3],
        method=cv2.CALIB_HAND_EYE_PARK,
    )
    mount = np.eye(4)
    mount[:3, :3], mount[:3, 3] = rotation, translation.ravel()
    _transforms([mount])
    boards = robot @ mount @ camera
    reference = np.eye(4)
    reference[:3, :3] = Rotation.from_matrix(boards[:, :3, :3]).mean().as_matrix()
    reference[:3, 3] = boards[:, :3, 3].mean(axis=0)
    return HandEyeFit(mount, reference, excitation)


def score_poses(fit, base_T_tool, camera_T_target):
    """Compare predicted static board poses to the reference fixed at fit time."""
    robot, camera = _pairs(base_T_tool, camera_T_target)
    boards = robot @ fit.tool_T_camera @ camera
    translation = np.linalg.norm(boards[:, :3, 3] - fit.base_T_target[:3, 3], axis=1)
    relative = fit.base_T_target[:3, :3].T @ boards[:, :3, :3]
    angles = np.rad2deg(Rotation.from_matrix(relative).magnitude())
    return {"translation_mm": (1000 * translation).tolist(), "rotation_deg": angles.tolist()}
