"""Detect the upright, blue open bin from registered RGB, metric depth and calibration."""
from dataclasses import dataclass

import cv2
import numpy as np

from .geometry import backproject
from .types import Observation, OperationError


@dataclass(frozen=True)
class BinEstimate:
    observation_id: str
    center_xy_m: tuple[float, float]
    inner_size_m: tuple[float, float]  # long opening dimension first
    yaw_rad: float                     # long axis, modulo pi
    floor_z_m: float
    rim_z_m: float
    rim_points: int
    floor_points: int

    def contains_payload(self, xy):
        # Circumscribe the 64 x 52 mm catalog footprint independent of parcel yaw.
        clearance = np.hypot(.032, .026) + .003
        c, s = np.cos(self.yaw_rad), np.sin(self.yaw_rad)
        local = (np.asarray(xy) - self.center_xy_m) @ np.array([[c, -s], [s, c]])
        return bool(np.all(np.abs(local) + clearance < np.asarray(self.inner_size_m) / 2))


def _opening_edges(local, half_extent):
    """Require top-surface depth samples spanning the middle of all four rails."""
    bounds = []
    for axis in (0, 1):
        across = 1 - axis
        span = half_extent[across] * .78
        middle = np.abs(local[:, across]) < span
        inner = []
        for sign in (-1, 1):
            distance = sign * local[:, axis]
            on_side = middle & (distance > half_extent[axis] - .024)
            if np.count_nonzero(on_side) < 15:
                return None
            coverage, _ = np.histogram(local[on_side, across], bins=12, range=(-span, span))
            if np.count_nonzero(coverage) < 11:
                return None
            # Small quantile suppresses individual antialiased edge/depth pixels.
            inner.append(sign * float(np.quantile(distance[on_side], .025)))
        bounds.append(inner)
    return np.asarray(bounds)


def _fit_bin(obs, mask):
    rows, cols = np.nonzero(mask & np.isfinite(obs.depth) & (obs.depth > .05) & (obs.depth < 3.))
    if len(rows) < 700:
        return None
    points = backproject(np.column_stack((cols, rows)), obs.depth[rows, cols], obs.K, obs.T_base_camera)
    # Surveyed tabletop work volume. No bin coordinates or dimensions are supplied.
    points = points[(points[:, 2] > .035) & (points[:, 2] < .25)]
    if len(points) < 700:
        return None
    z = points[:, 2]
    rim_z = np.quantile(z, .96)
    top = points[np.abs(z - rim_z) < .003]
    if len(top) < 130:
        return None
    rect = cv2.minAreaRect(top[:, :2].astype(np.float32))
    corners = cv2.boxPoints(rect).astype(float)
    sides = np.diff(np.vstack((corners, corners[0])), axis=0)
    lengths = np.linalg.norm(sides, axis=1)
    long, short = np.max(lengths), np.min(lengths)
    if not (.085 < short <= long < .40):
        return None
    direction = sides[np.argmax(lengths)]
    yaw = (np.arctan2(direction[1], direction[0]) + np.pi / 2) % np.pi - np.pi / 2
    c, s = np.cos(yaw), np.sin(yaw)
    axes = np.array([[c, -s], [s, c]])
    center = np.asarray(rect[0])
    bounds = _opening_edges((top[:, :2] - center) @ axes, np.array([long, short]) / 2)
    if bounds is None:
        return None
    size = bounds[:, 1] - bounds[:, 0]
    center = center + axes @ np.mean(bounds, axis=1)
    # Floor support must appear well inside the opening, at a second planar height.
    interior = np.all(np.abs((points[:, :2] - center) @ axes) < size * .42, axis=1)
    floor = z[interior]
    if len(floor) < 250:
        return None
    floor_z = float(np.median(floor))
    floor_inliers = np.abs(floor - floor_z) < .003
    rim_z = float(np.median(top[:, 2]))
    if np.mean(floor_inliers) < .80 or not .025 < rim_z - floor_z < .15:
        return None
    # Touching bins can merge into a single color component. A raised divider
    # crossing the interior rules out using its midpoint as a placement goal.
    interior_rim = int(np.count_nonzero(np.abs(floor - rim_z) < .003))
    if interior_rim > max(12, .015 * len(top)):
        raise OperationError('BIN_OPENING_OBSTRUCTED', {'interior_rim_points': interior_rim})
    return BinEstimate(obs.observation_id, tuple(center.tolist()), tuple(size.tolist()), float(yaw),
                       floor_z, rim_z, len(top), int(np.count_nonzero(floor_inliers)))


def detect_bin(obs: Observation, now_sim_time: float) -> BinEstimate:
    """Return one supported rectangular opening or a reason to hold."""
    try:
        obs.validate(now_sim_time)
    except ValueError as exc:
        raise OperationError(str(exc)) from exc
    hsv = cv2.cvtColor(obs.rgb, cv2.COLOR_RGB2HSV)
    blue = cv2.inRange(hsv, (90, 78, 35), (112, 255, 255))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(blue)
    fits = []
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < 700:
            continue
        fit = _fit_bin(obs, labels == label)
        if fit is not None:
            fits.append(fit)
    if len(fits) != 1:
        raise OperationError('BIN_AMBIGUOUS' if fits else 'BIN_NOT_FOUND', {'supported_bins': len(fits)})
    return fits[0]
