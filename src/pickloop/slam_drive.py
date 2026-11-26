"""Follow a reconstructed route with encoders and live scans in the first-scan frame."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .lidar_slam import MAX_RANGE_M, compose, integrate_encoders, match_scans, relative
from .mobile import DT, MAX_WHEEL_ACCEL_M_S2, MAX_WHEEL_M_S, TRACK_M, wrap


GOAL_TOLERANCE_M = .025
TRACKING_MARGIN_M = .055
_FIX_PERIOD_TICKS = 8
_MAX_TICKS_WITHOUT_FIX = 100
_ZERO = np.zeros(2)


def valid_scan(scan):
    return scan.shape == (36,) and np.isfinite(scan).all() and np.all((scan > 0.) & (scan <= MAX_RANGE_M))


def stopping_distance(encoders):
    # The fastest wheel bounds centre speed while turning. Allow for one tick
    # of acceleration, encoder noise and the response time of the next update.
    speed = max(abs(encoders)) + .016 + MAX_WHEEL_ACCEL_M_S2 * DT
    return speed * DT + speed ** 2 / (2 * MAX_WHEEL_ACCEL_M_S2)


def lidar_clear(scan, minimum_clearance):
    return bool(np.min(scan) > minimum_clearance / math.cos(math.pi / 36))


class ScanReference:
    """Local registration against immutable scans anchored at reconstructed poses."""

    def __init__(self, poses, scans):
        self.poses = np.asarray(poses, dtype=float).copy()
        self.scans = np.asarray(scans, dtype=float).copy()
        if (self.poses.ndim != 2 or self.poses.shape[1] != 3 or not len(self.poses)
                or self.scans.shape != (len(self.poses), 36) or not np.isfinite(self.poses).all()
                or not np.isfinite(self.scans).all() or np.any((self.scans <= 0) | (self.scans > MAX_RANGE_M))):
            raise ValueError('expected finite reconstructed poses and matching LiDAR scans')
        self.poses.setflags(write=False)
        self.scans.setflags(write=False)

    def locate(self, prior, scan):
        distances = np.linalg.norm(self.poses[:, :2] - prior[:2], axis=1)
        best = None
        for index in np.argsort(distances, kind='stable')[:4]:
            if distances[index] > 1.7:
                break
            anchor = self.poses[index]
            match = match_scans(self.scans[index], scan, relative(anchor, prior))
            if match.accepted:
                score = (match.overlap, -match.rms_m)
                if best is None or score > best[0]:
                    best = score, compose(anchor, match.delta), int(index)
        return (None, None) if best is None else best[1:]


class RouteFollower:
    """Sensor-only controller in the first-scan coordinate frame."""

    def __init__(self, navigation, route, reference=None, *, initial_pose=(0., 0., 0.)):
        self.navigation = navigation
        self.reference = reference
        self.pose = np.asarray(initial_pose, dtype=float).copy()
        if self.pose.shape != (3,) or not np.isfinite(self.pose).all():
            raise ValueError('expected a finite initial pose in the map frame')
        self.wheel_pose = self.pose.copy()
        self.status = 'RUNNING'
        self.ticks = 0
        self.fix_attempts = 0
        self.accepted_fixes = 0
        self.last_fix_tick = 0
        self.matched_keyframe = None
        self.waypoint = 1
        try:
            self.route = np.asarray(route, dtype=float)
        except (TypeError, ValueError):
            self.status = 'NO_PATH'
            return
        if (self.route.ndim != 2 or self.route.shape[1] != 2 or len(self.route) < 2
                or not np.isfinite(self.route).all() or math.dist(self.route[0], self.pose[:2]) > 1e-9
                or not all(navigation.segment_clear(a, b) for a, b in zip(self.route, self.route[1:]))):
            self.status = 'NO_PATH'

    def predict(self, encoders):
        encoders = np.asarray(encoders, dtype=float)
        if encoders.shape != (2,) or not np.isfinite(encoders).all():
            self.status = 'SENSOR_INVALID'
            return
        self.pose = integrate_encoders(self.pose, encoders, DT)
        self.wheel_pose = integrate_encoders(self.wheel_pose, encoders, DT)

    def command(self, scan, encoders):
        self.matched_keyframe = None
        if self.status != 'RUNNING':
            return _ZERO.copy()
        scan, encoders = np.asarray(scan, dtype=float), np.asarray(encoders, dtype=float)
        if not valid_scan(scan) or encoders.shape != (2,) or not np.isfinite(encoders).all():
            return self._hold('SENSOR_INVALID')

        body_allowance = self.navigation.radius + TRACKING_MARGIN_M
        min_clearance = body_allowance + stopping_distance(encoders)
        if not lidar_clear(scan, min_clearance):
            return self._hold('LIDAR_STOP')

        if self.reference is not None and self.ticks % _FIX_PERIOD_TICKS == 0:
            self.fix_attempts += 1
            corrected, self.matched_keyframe = self.reference.locate(self.pose, scan)
            if corrected is not None:
                correction = relative(self.pose, corrected)
                self.pose = compose(self.pose, .45 * correction)
                self.accepted_fixes += 1
                self.last_fix_tick = self.ticks
        if self.reference is not None and self.ticks - self.last_fix_tick >= _MAX_TICKS_WITHOUT_FIX:
            return self._hold('LOCALIZATION_LOST')
        if not self.navigation.clear(self.pose[:2], min_clearance):
            return self._hold('MAP_CLEARANCE')

        delta = self.route[self.waypoint] - self.pose[:2]
        distance = np.linalg.norm(delta)
        while distance <= GOAL_TOLERANCE_M:
            self.waypoint += 1
            if self.waypoint == len(self.route):
                return self._hold('GOAL_REACHED')
            delta = self.route[self.waypoint] - self.pose[:2]
            distance = np.linalg.norm(delta)
        error = wrap(math.atan2(delta[1], delta[0]) - self.pose[2])
        linear = min(.34, 1.25 * distance) * math.cos(error) if abs(error) < .32 else 0.
        angular = float(np.clip(2.4 * error, -1.2, 1.2))
        # Slow before narrow sections so that the next stopping envelope can
        # fit. Use a short sweep toward the target and a separate guard at the
        # measured speed above, which still latches if this estimate is wrong.
        lookahead = self.pose[:2] + delta * min(1., .22 / distance) if linear else self.pose[:2]
        available = self.navigation.segment_clearance(self.pose[:2], lookahead) - body_allowance
        reaction = MAX_WHEEL_ACCEL_M_S2 * DT
        speed_limit = math.sqrt(reaction ** 2 + 2 * MAX_WHEEL_ACCEL_M_S2 * max(0., available)) - 2 * reaction - .026
        requested = np.array([linear - angular * TRACK_M / 2, linear + angular * TRACK_M / 2])
        peak = max(abs(requested))
        self.ticks += 1
        return requested * min(1., max(0., speed_limit) / peak) if peak else requested

    def _hold(self, status):
        self.status = status
        return _ZERO.copy()


class KinematicPlant:
    """Existing mobile wheel model and LiDAR raycasting, without a landmark estimator."""

    def __init__(self, world, start, seed):
        self.world = world
        self.truth_pose = np.asarray(start, dtype=float).copy()
        self.wheels_m_s = np.zeros(2)
        self.encoder_rng, self.lidar_rng = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(2)]

    def scan(self):
        return self.world.lidar(self.truth_pose, self.lidar_rng)

    def advance(self, requested):
        target = np.clip(requested, -MAX_WHEEL_M_S, MAX_WHEEL_M_S)
        self.wheels_m_s += np.clip(target - self.wheels_m_s,
                                   -MAX_WHEEL_ACCEL_M_S2 * DT, MAX_WHEEL_ACCEL_M_S2 * DT)
        # Same gain mismatch and noise as the known-map plant.
        actual = self.wheels_m_s * [1.004, .996]
        self.truth_pose = integrate_encoders(self.truth_pose, actual, DT)
        return self.wheels_m_s + self.encoder_rng.normal(0., .004, 2)


@dataclass
class DriveSample:
    time_s: float
    status: str
    requested_m_s: np.ndarray
    encoder_m_s: np.ndarray
    minimum_lidar_range_m: float
    matched_keyframe: int | None
    estimate_pose: np.ndarray
    wheel_pose: np.ndarray
    truth_pose: np.ndarray
    wheels_m_s: np.ndarray


@dataclass
class DriveResult:
    status: str
    samples: list[DriveSample]


def drive_route(follower, plant, *, max_steps=1500):
    """Connect command and observations. Copies of plant state feed only the trace."""
    samples = []
    if follower.status != 'RUNNING':
        return DriveResult(follower.status, samples)
    encoders = np.zeros(2)

    def tick(requested, scan):
        nonlocal encoders
        encoders = plant.advance(requested)
        follower.predict(encoders)
        samples.append(DriveSample((len(samples) + 1) * DT, follower.status, requested, encoders,
                                   float(np.min(scan)), follower.matched_keyframe, follower.pose.copy(),
                                   follower.wheel_pose.copy(), plant.truth_pose.copy(), plant.wheels_m_s.copy()))

    for _ in range(max_steps):
        scan = plant.scan()
        requested = follower.command(scan, encoders)
        tick(requested, scan)
        if follower.status != 'RUNNING':
            break
    if follower.status == 'RUNNING':
        follower.status = 'MOTION_TIMEOUT'
    # A fixed command-only braking interval keeps truth out of the stop decision.
    for _ in range(math.ceil(MAX_WHEEL_M_S / (MAX_WHEEL_ACCEL_M_S2 * DT))):
        scan = plant.scan()
        tick(follower.command(scan, encoders), scan)
    return DriveResult(follower.status, samples)
