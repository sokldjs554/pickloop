"""Offline 2D pose-graph SLAM in the first scan's frame.

The estimator consumes wheel odometry poses and beam ranges (index 0 at -pi,
increasing counterclockwise). No map is loaded here.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix

from .mobile import TRACK_M, wrap


ANGLES = np.linspace(-np.pi, np.pi, 36, endpoint=False)
DIRECTIONS = np.column_stack((np.cos(ANGLES), np.sin(ANGLES)))
MAX_RANGE_M = 8.
# The simulator adds noise after clipping at maximum range. Treat the last
# four centimetres as free-space-only to avoid inventing occupied endpoints.
HIT_LIMIT_M = MAX_RANGE_M - .04


def rotation(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s], [s, c]])


def compose(pose, delta):
    xy = pose[:2] + rotation(pose[2]) @ delta[:2]
    return np.array([*xy, wrap(pose[2] + delta[2])])


def relative(first, second):
    xy = rotation(-first[2]) @ (second[:2] - first[:2])
    return np.array([*xy, wrap(second[2] - first[2])])


def integrate_encoders(pose, wheels_m_s, dt_s):
    distance = np.mean(wheels_m_s) * dt_s
    angle = (wheels_m_s[1] - wheels_m_s[0]) * dt_s / TRACK_M
    return compose(pose, [distance * np.cos(angle / 2), distance * np.sin(angle / 2), angle])


def _scan(ranges):
    ranges = np.asarray(ranges, dtype=float)
    if ranges.shape != (36,) or not np.isfinite(ranges).all() or np.any((ranges <= 0) | (ranges > MAX_RANGE_M)):
        raise ValueError('expected 36 finite ranges in (0, 8] metres')
    return ranges


def _walls(ranges):
    """Approximate observed surfaces by adjacent collinear triples of beam hits."""
    points = ranges[:, None] * DIRECTIONS
    starts, ends = np.roll(points, 1, axis=0), np.roll(points, -1, axis=0)
    vectors = ends - starts
    lengths = np.linalg.norm(vectors, axis=1)
    unit = vectors / np.maximum(lengths[:, None], 1.e-12)
    normals = np.column_stack((-unit[:, 1], unit[:, 0]))
    hit = ranges < HIT_LIMIT_M
    valid = hit & np.roll(hit, 1) & np.roll(hit, -1)
    valid &= (lengths > .12) & (lengths < 2.8)
    valid &= np.abs(np.sum((points - starts) * normals, axis=1)) < .035
    return starts[valid], normals[valid], unit[valid], lengths[valid]


def _associations(points, lines, pose, distance_gate):
    starts, normals, directions, lengths = lines
    rotated = points @ rotation(pose[2]).T
    offsets = rotated[:, None, :] + pose[:2] - starts
    parallel = np.sum(offsets * directions, axis=2)
    residuals = np.sum(offsets * normals, axis=2)
    overhang = np.maximum(np.maximum(-parallel, parallel - lengths), 0.)
    distances = np.hypot(residuals, overhang)
    best = np.argmin(distances, axis=1)
    rows = np.arange(len(points))
    keep = (distances[rows, best] < distance_gate) & (overhang[rows, best] < .09)
    chosen = best[keep]
    normal = normals[chosen]
    rotated = rotated[keep]
    yaw_derivative = -normal[:, 0] * rotated[:, 1] + normal[:, 1] * rotated[:, 0]
    return np.column_stack((normal, yaw_derivative)), residuals[rows[keep], chosen]


@dataclass
class ScanMatch:
    delta: np.ndarray
    accepted: bool = False
    overlap: float = 0.
    rms_m: float | None = None


def match_scans(reference, current, prior, *, loop=False):
    """Point-to-line ICP followed by a bidirectional geometrical check."""
    reference, current = _scan(reference), _scan(current)
    first_lines, second_lines = _walls(reference), _walls(current)
    first_points = (DIRECTIONS * reference[:, None])[reference < HIT_LIMIT_M]
    second_points = (DIRECTIONS * current[:, None])[current < HIT_LIMIT_M]
    pose = np.array(prior, dtype=float, copy=True)
    if min(len(first_lines[0]), len(second_lines[0])) < 5:
        return ScanMatch(pose)
    for _ in range(14):
        jac, residual = _associations(second_points, first_lines, pose, .42)
        if len(residual) < 7 or np.linalg.matrix_rank(jac) < 3:
            return ScanMatch(pose)
        weights = np.sqrt(np.minimum(1., .04 / np.maximum(np.abs(residual), 1.e-9)))
        step, *_ = np.linalg.lstsq(jac * weights[:, None], -residual * weights, rcond=None)
        pose += step
        pose[2] = wrap(pose[2])
        if np.linalg.norm(step) < 1.e-5:
            break

    forward, f_res = _associations(second_points, first_lines, pose, .085)
    backward, b_res = _associations(first_points, second_lines, relative(pose, np.zeros(3)), .085)
    overlap = min(len(f_res) / len(second_points), len(b_res) / len(first_points))
    residuals = np.r_[f_res, b_res]
    rms = float(np.sqrt(np.mean(residuals ** 2))) if len(residuals) else None
    # At least two distinct normal directions must constrain translation in each scan.
    observable = all(len(j) >= 7 and np.linalg.eigvalsh(j[:, :2].T @ j[:, :2] / len(j))[0] > .08
                     for j in (forward, backward))
    correction = relative(np.asarray(prior), pose)
    consistent = np.linalg.norm(correction[:2]) < (.65 if loop else .14) and abs(correction[2]) < (.32 if loop else .10)
    accepted = observable and consistent and overlap >= (.64 if loop else .46) and rms is not None and rms < .031
    return ScanMatch(pose, bool(accepted), float(overlap), rms)


@dataclass
class LoopEdge:
    start: int
    end: int
    match: ScanMatch


def _optimize(frontend, steps, loops):
    if not loops:
        return frontend.copy()
    indices = [(i, i + 1) for i in range(len(steps))] + [(e.start, e.end) for e in loops]
    a, b = np.asarray(indices).T
    measurements = np.array(list(steps) + [e.match.delta for e in loops])
    sigma = np.array([[.035, .035, .016]] * len(steps) + [[.018, .018, .009]] * len(loops))
    sparsity = lil_matrix((3 * len(indices), 3 * (len(frontend) - 1)), dtype=int)
    for i, pair in enumerate(indices):
        for node in pair:
            if node:
                sparsity[3*i:3*i+3, 3*node-3:3*node] = 1

    def residuals(variables):
        poses = np.vstack((frontend[0], variables.reshape(-1, 3)))
        diff = poses[b] - poses[a]
        c, s = np.cos(poses[a, 2]), np.sin(poses[a, 2])
        predicted = np.column_stack((c * diff[:, 0] + s * diff[:, 1],
                                    -s * diff[:, 0] + c * diff[:, 1], diff[:, 2]))
        error = predicted - measurements
        error[:, 2] = wrap(error[:, 2])
        return (error / sigma).ravel()

    fit = least_squares(residuals, frontend[1:].ravel(), jac_sparsity=sparsity.tocsr(),
                        loss='soft_l1', max_nfev=100)
    if not fit.success:
        raise RuntimeError(f'pose graph did not converge: {fit.message}')
    optimized = np.vstack((frontend[0], fit.x.reshape(-1, 3)))
    optimized[:, 2] = wrap(optimized[:, 2])
    return optimized


@dataclass
class SlamResult:
    frontend: np.ndarray
    poses: np.ndarray
    loops: list[LoopEdge]
    local_matches: int
    loop_candidates: int


def estimate(odometry, scans):
    """Estimate keyframe poses. Both inputs are synchronized at scan acquisition."""
    odometry = np.asarray(odometry, dtype=float)
    scans = [_scan(scan) for scan in scans]
    if odometry.shape != (len(scans), 3) or not scans or not np.isfinite(odometry).all():
        raise ValueError('expected a finite odometry pose per scan')
    frontend = [np.zeros(3)]
    travel = [0.]
    steps, loops = [], []
    local_matches = candidates = 0
    for i in range(1, len(scans)):
        wheel = relative(odometry[i - 1], odometry[i])
        match = match_scans(scans[i - 1], scans[i], wheel)
        step = wheel.copy()
        if match.accepted:
            local_matches += 1
            step[:2] += .75 * (match.delta[:2] - wheel[:2])
            step[2] = wrap(wheel[2] + .75 * wrap(match.delta[2] - wheel[2]))
        steps.append(step)
        frontend.append(compose(frontend[-1], step))
        travel.append(travel[-1] + np.linalg.norm(wheel[:2]))
        eligible = []
        for j in range(i - 1):
            prior = relative(frontend[j], frontend[i])
            if travel[i] - travel[j] > 5. and np.linalg.norm(prior[:2]) < .75 and abs(prior[2]) < .8:
                eligible.append((np.linalg.norm(prior[:2]), j, prior))
        if loops and i - loops[-1].end < 3:
            continue
        for _, j, prior in sorted(eligible, key=lambda e: e[0]):
            candidates += 1
            match = match_scans(scans[j], scans[i], prior, loop=True)
            if match.accepted:
                loops.append(LoopEdge(j, i, match))
                break
    frontend = np.array(frontend)
    return SlamResult(frontend, _optimize(frontend, steps, loops), loops, local_matches, candidates)


def occupancy_grid(poses, scans, resolution=.07):
    """Ray-carved grid (-1 unknown, 0 free, 100 occupied), row 0 at minimum y."""
    poses = np.asarray(poses, dtype=float)
    if not np.isfinite(resolution) or resolution <= 0 or poses.shape != (len(scans), 3) or not len(scans):
        raise ValueError('expected matching poses and scans, and positive resolution')
    endpoints = [pose[:2] + (_scan(scan)[:, None] * DIRECTIONS) @ rotation(pose[2]).T
                 for pose, scan in zip(poses, scans)]
    all_points = np.vstack([poses[:, :2], *endpoints])
    origin = (np.floor(all_points.min(axis=0) / resolution) - 2) * resolution
    def cells(points):
        return np.floor((points - origin) / resolution + 1.e-9).astype(int)
    width, height = cells(all_points.max(axis=0)) + 3
    score = np.zeros((height, width), dtype=np.int32)
    for pose, points, ranges in zip(poses, endpoints, scans):
        start = tuple(cells(pose[:2]))
        free = np.zeros_like(score, dtype=np.uint8)
        ends = cells(points)
        for end in ends:
            cv2.line(free, start, tuple(end), 1, 1)
        hits = ends[np.asarray(ranges) < HIT_LIMIT_M]
        free[hits[:, 1], hits[:, 0]] = 0
        score -= free
        # Count each cell at most once per scan.
        score[hits[:, 1], hits[:, 0]] += 4
    return np.where(score > 0, 100, np.where(score < 0, 0, -1)).astype(np.int8), origin
