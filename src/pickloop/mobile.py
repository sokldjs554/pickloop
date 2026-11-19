"""Known-map mobile simulation; wheel kinematics, not MuJoCo contact dynamics.

The controller receives only an EKF estimate, encoder samples and ray ranges.
Truth is confined to the simulated plant, sensor generation and evaluator gates.
No SLAM, real charging, hardware safety or physical mobile/manipulator coupling.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import threading
import time
import uuid
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DT = .04
TRACK_M = .38
MAX_WHEEL_M_S = .55
MAX_WHEEL_ACCEL_M_S2 = .8


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


class MobileHold(RuntimeError):
    """A bounded failure stops motion and prevents downstream picking."""


class MobileMap:
    def __init__(self, config):
        self.config = config
        self.bounds = config['bounds_m']
        self.obstacles = [list(rect) for rect in config['obstacles_m']]
        self.resolution = config['grid_resolution_m']
        self.radius = config['robot_radius_m']
        self.margin = config['planning_margin_m']
        self.landmarks = np.array(config['landmarks_m'], dtype=float)

    @classmethod
    def load(cls, path=None):
        return cls(json.loads(Path(path or ROOT / 'configs/mobile-map.json').read_text()))

    def clear(self, point, radius):
        x, y = point[:2]
        x0, y0, x1, y1 = self.bounds
        if not (x0 + radius < x < x1 - radius and y0 + radius < y < y1 - radius):
            return False
        for left, bottom, right, top in self.obstacles:
            dx, dy = max(left - x, 0., x - right), max(bottom - y, 0., y - top)
            if math.hypot(dx, dy) <= radius:
                return False
        return True

    def segment_clear(self, start, end):
        n = max(2, math.ceil(np.linalg.norm(np.array(end) - start) / (.4 * self.resolution)))
        return all(self.clear(p, self.radius + self.margin) for p in np.linspace(start, end, n))

    def plan(self, start, goal):
        """8-neighbor A* over circular-footprint inflated occupancy; no corner cuts."""
        start, goal = np.array(start[:2]), np.array(goal[:2])
        resolution = self.resolution
        node = lambda p: tuple(np.rint(np.array(p) / resolution).astype(int))
        first, last = node(start), node(goal)
        radius = self.radius + self.margin
        if not self.clear(start, radius) or not self.clear(goal, radius):
            raise MobileHold('NO_PATH')
        valid_cache = {}
        def valid(cell):
            if cell not in valid_cache:
                valid_cache[cell] = self.clear(np.array(cell) * resolution, radius)
            return valid_cache[cell]
        frontier = [(0., first)]; previous = {}; cost = {first: 0.}
        while frontier:
            _, current = heapq.heappop(frontier)
            if current == last:
                path = [last]
                while path[-1] != first:
                    path.append(previous[path[-1]])
                points = [start] + [np.array(c) * resolution for c in reversed(path)] + [goal]
                # Visibility smoothing preserves the inflated footprint along every segment.
                route = [points[0]]; i = 0
                while i < len(points) - 1:
                    j = len(points) - 1
                    while j > i + 1 and not self.segment_clear(points[i], points[j]):
                        j -= 1
                    route.append(points[j]); i = j
                return [p.tolist() for p in route]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                nxt = (current[0] + dx, current[1] + dy)
                if not valid(nxt) or not valid((current[0] + dx, current[1])) or not valid((current[0], current[1] + dy)):
                    continue
                candidate = cost[current] + math.hypot(dx, dy)
                if candidate < cost.get(nxt, math.inf):
                    cost[nxt] = candidate; previous[nxt] = current
                    heapq.heappush(frontier, (candidate + math.dist(nxt, last), nxt))
        raise MobileHold('NO_PATH')

    def lidar(self, pose, rng):
        """36 exact 2D ray/AABB intersections, noisy range samples in metres."""
        angles = pose[2] + np.linspace(-math.pi, math.pi, 36, endpoint=False)
        directions = np.column_stack([np.cos(angles), np.sin(angles)])
        ranges = np.full(36, 8.)
        origin = np.asarray(pose[:2])
        # Intersection with the outer room boundary: exit distance.
        inverse = np.divide(1., directions, out=np.full_like(directions, 1e12), where=np.abs(directions) > 1e-12)
        bounds = np.array(self.bounds)
        a = (bounds[:2] - origin) * inverse; b = (bounds[2:] - origin) * inverse
        ranges = np.minimum(ranges, np.min(np.maximum(a, b), axis=1))
        for rect in self.obstacles:
            r = np.array(rect)
            a = (r[:2] - origin) * inverse; b = (r[2:] - origin) * inverse
            near, far = np.max(np.minimum(a, b), axis=1), np.min(np.maximum(a, b), axis=1)
            hit = (far >= np.maximum(near, 0.)) & (far >= 0.)
            ranges[hit] = np.minimum(ranges[hit], np.maximum(near[hit], 0.))
        return np.clip(ranges + rng.normal(0., .008, 36), 0., 8.)


class PoseEKF:
    """SE(2) encoder prediction + known-landmark range/bearing updates; not SLAM."""
    def __init__(self, initial):
        self.pose = np.array(initial, dtype=float)
        self.cov = np.diag([.08 ** 2, .08 ** 2, .05 ** 2])

    def predict(self, encoders, dt=DT):
        left, right = encoders
        v, omega = (left + right) / 2, (right - left) / TRACK_M
        heading = self.pose[2] + omega * dt / 2
        distance = v * dt
        self.pose += [distance * math.cos(heading), distance * math.sin(heading), omega * dt]
        self.pose[2] = wrap(self.pose[2])
        jacobian = np.eye(3)
        jacobian[0, 2] = -distance * math.sin(heading)
        jacobian[1, 2] = distance * math.cos(heading)
        self.cov = jacobian @ self.cov @ jacobian.T + np.diag([.001 ** 2, .001 ** 2, .0015 ** 2])

    def observe(self, landmark, measurement):
        dx, dy = np.asarray(landmark) - self.pose[:2]
        square = dx * dx + dy * dy; distance = math.sqrt(square)
        if distance < .05:
            return
        predicted = np.array([distance, wrap(math.atan2(dy, dx) - self.pose[2])])
        innovation = np.asarray(measurement) - predicted; innovation[1] = wrap(innovation[1])
        jacobian = np.array([[-dx / distance, -dy / distance, 0.], [dy / square, -dx / square, -1.]])
        noise = np.diag([.025 ** 2, .012 ** 2])
        gain = np.linalg.solve(jacobian @ self.cov @ jacobian.T + noise, jacobian @ self.cov).T
        self.pose += gain @ innovation; self.pose[2] = wrap(self.pose[2])
        residual = np.eye(3) - gain @ jacobian
        self.cov = residual @ self.cov @ residual.T + gain @ noise @ gain.T


class FleetScheduler:
    """Single-process two-robot allocator and fail-closed exclusive-zone lease.

    An expired owner stays fenced and blocks reassignment until positive clearance.
    There is no distributed consensus, persistence, or network partition recovery.
    """
    def __init__(self, robots, lease_s=90.):
        self.robots = list(robots); self.assignments = {}; self.finished = set()
        self.owner = None; self.expires = -math.inf; self.lease_s = lease_s
        self.occupied = set(); self.fenced = False

    def allocate(self, task, target, poses):
        if task in self.assignments:
            return self.assignments[task]
        busy = {robot for key, robot in self.assignments.items() if key not in self.finished}
        free = [robot for robot in self.robots if robot not in busy]
        if not free:
            return None
        robot = min(free, key=lambda name: (math.dist(poses[name][:2], target[:2]), name))
        self.assignments[task] = robot
        return robot

    def valid(self, robot, now):
        if self.owner is not None and now >= self.expires:
            self.fenced = True
        return self.owner == robot and not self.fenced

    def acquire(self, robot, now):
        if robot not in self.robots:
            raise ValueError('unknown robot')
        if self.owner is None and not self.occupied:
            self.owner = robot; self.expires = now + self.lease_s; self.fenced = False
            return True
        return self.valid(robot, now)

    def renew(self, robot, now):
        if not self.valid(robot, now):
            raise MobileHold('ZONE_LEASE_EXPIRED')
        self.expires = now + self.lease_s

    def enter(self, robot, now):
        if not self.valid(robot, now) or self.occupied - {robot}:
            raise MobileHold('ZONE_CONFLICT')
        self.occupied.add(robot)

    def release(self, robot, estimated_clear):
        if self.owner != robot:
            raise MobileHold('ZONE_OWNER_MISMATCH')
        if not estimated_clear:
            raise MobileHold('ZONE_NOT_CLEAR')
        self.occupied.discard(robot); self.owner = None; self.fenced = False


def dock_check(estimate, truth, target, wheels):
    """Evaluator truth is a veto only, never a navigation feedback input."""
    estimate, truth, target = map(np.asarray, (estimate, truth, target))
    ep = float(np.linalg.norm(estimate[:2] - target[:2]))
    tp = float(np.linalg.norm(truth[:2] - target[:2]))
    ea, ta = abs(wrap(estimate[2] - target[2])), abs(wrap(truth[2] - target[2]))
    stopped = bool(np.max(np.abs(wheels)) < .015)
    return dict(accepted=ep <= .06 and tp <= .06 and ea <= .06 and ta <= .06 and stopped,
                estimate_error_m=ep, truth_error_m=tp, estimate_yaw_error_rad=ea,
                truth_yaw_error_rad=ta, stopped=stopped)


class DeadlineCancel:
    def __init__(self, cancel, deadline):
        self.cancel, self.deadline = cancel, deadline

    def is_set(self):
        return self.cancel.is_set() or time.monotonic() >= self.deadline


class MobileSimulation:
    def __init__(self, world, seed, emit, fleet, cancel, sim_deadline, wall_deadline):
        self.world, self.rng, self.emit, self.fleet = world, np.random.default_rng(seed), emit, fleet
        self.truth = {name: np.array(p, dtype=float) for name, p in world.config['robot_starts_m_rad'].items()}
        # Initialization uses a surveyed start plus a sampled error, not the plant's current pose.
        self.estimators = {name: PoseEKF(np.array(p) + self.rng.normal(0., [.025, .025, .02]))
                           for name, p in world.config['robot_starts_m_rad'].items()}
        self.wheels = {name: np.zeros(2) for name in self.truth}
        self.cancel, self.sim_deadline, self.wall_deadline = cancel, sim_deadline, wall_deadline
        self.t = 0.; self.count = 0

    def guard(self):
        if self.cancel.is_set():
            raise MobileHold('CANCELLED')
        if time.monotonic() >= self.wall_deadline:
            raise MobileHold('WALL_DEADLINE')
        if self.t >= self.sim_deadline:
            raise MobileHold('SIM_DEADLINE')

    def zone_overlap(self, pose, inflation=0.):
        x0, y0, x1, y1 = self.world.config['shared_zone_m']
        return x0 - inflation < pose[0] < x1 + inflation and y0 - inflation < pose[1] < y1 + inflation

    def tick(self, robot, requested, state, emergency_brake=False):
        if emergency_brake:
            requested = [0., 0.]
        else:
            self.guard()
        estimator = self.estimators[robot]
        if self.fleet.owner == robot and not emergency_brake:
            self.fleet.renew(robot, self.t)
        # Occupancy uses the estimated circular footprint enlarged by 3-sigma position error.
        uncertainty = 3 * math.sqrt(float(np.linalg.eigvalsh(estimator.cov[:2, :2]).max()))
        in_zone = self.zone_overlap(estimator.pose, self.world.radius + uncertainty + .10)
        if in_zone and not emergency_brake:
            self.fleet.enter(robot, self.t)
        scan = self.world.lidar(self.truth[robot], self.rng)
        requested = np.asarray(requested, dtype=float)
        if min(scan) < self.world.radius + .055 and max(abs(requested)) > 0:
            requested = np.zeros(2)
            self.emit('LIDAR_STOP', self.t, robot, state, {'minimum_range_m': float(min(scan))})
        old = self.wheels[robot].copy()
        wheel = old + np.clip(np.clip(requested, -MAX_WHEEL_M_S, MAX_WHEEL_M_S) - old,
                              -MAX_WHEEL_ACCEL_M_S2 * DT, MAX_WHEEL_ACCEL_M_S2 * DT)
        self.wheels[robot] = wheel
        pose = self.truth[robot].copy()
        # Small fixed wheel gain errors make encoder integration alone imperfect.
        actual = wheel * np.array([1.004, .996])
        v, omega = actual.mean(), (actual[1] - actual[0]) / TRACK_M
        heading = pose[2] + omega * DT / 2
        pose += [v * DT * math.cos(heading), v * DT * math.sin(heading), omega * DT]
        pose[2] = wrap(pose[2])
        collision = not self.world.clear(pose[:2], self.world.radius)
        collision |= any(np.linalg.norm(pose[:2] - other[:2]) <= 2 * self.world.radius
                         for name, other in self.truth.items() if name != robot)
        self.truth[robot] = pose
        encoder = wheel + self.rng.normal(0., .004, 2)
        estimator.predict(encoder)
        observations = []
        if self.count % 5 == 0:
            for i, landmark in enumerate(self.world.landmarks):
                delta = landmark - pose[:2]
                measurement = np.array([np.linalg.norm(delta), wrap(math.atan2(delta[1], delta[0]) - pose[2])])
                measurement += self.rng.normal(0., [.025, .012])
                measurement[1] = wrap(measurement[1])
                estimator.observe(landmark, measurement)
                observations.append({'landmark_id': i, 'range_m': float(measurement[0]), 'bearing_rad': float(measurement[1])})
        self.t += DT; self.count += 1
        self.emit('SAMPLE', self.t, robot, state,
                  dict(truth_pose_m_rad=pose.tolist(), estimate_pose_m_rad=estimator.pose.tolist(),
                       estimate_covariance=estimator.cov.tolist(), wheel_m_s=wheel.tolist(),
                       wheel_accel_m_s2=((wheel - old) / DT).tolist(), encoder_m_s=encoder.tolist(),
                       lidar_ranges_m=scan.tolist(), landmark_observations=observations,
                       zone_owner=self.fleet.owner, zone_occupied=sorted(self.fleet.occupied),
                       collision=bool(collision)))
        if collision:
            raise MobileHold('COLLISION')

    def brake_to_rest(self):
        """Bounded emergency deceleration remains simulated and logged after cancellation.

        Cancellation/deadline prevents new mission work. Braking may take at most
        MAX_WHEEL_M_S / MAX_WHEEL_ACCEL_M_S2 simulated seconds beyond that boundary.
        Zone ownership is retained; no lease handover occurs during the stop.
        """
        for robot in self.wheels:
            while np.max(np.abs(self.wheels[robot])) > 1e-12:
                self.tick(robot, [0., 0.], 'BRAKING', emergency_brake=True)

    def docking_measurements(self, robot):
        estimator = self.estimators[robot]
        dock = dock_check(estimator.pose, self.truth[robot], self.world.config['dock_m_rad'], self.wheels[robot])
        dock['position_sigma_m'] = math.sqrt(float(np.linalg.eigvalsh(estimator.cov[:2, :2]).max()))
        return dock

    def require_dock(self, robot):
        dock = self.docking_measurements(robot)
        if not dock['accepted'] or dock['position_sigma_m'] > .025:
            self.emit('DOCK_REJECTED', self.t, robot, 'HELD', dock)
            raise MobileHold('DOCK_TOLERANCE')
        self.emit('DOCK_ACCEPTED', self.t, robot, 'DOCKED', dock)

    def release_clear_zone(self, robot):
        estimator = self.estimators[robot]
        sigma = 3 * math.sqrt(float(np.linalg.eigvalsh(estimator.cov[:2, :2]).max()))
        clear = not self.zone_overlap(estimator.pose, self.world.radius + sigma + .10)
        if self.zone_overlap(self.truth[robot], self.world.radius):
            raise MobileHold('EVALUATOR_ZONE_NOT_CLEAR')
        self.fleet.release(robot, estimated_clear=clear)
        self.emit('ZONE_RELEASED', self.t, robot, 'EXITED', {'estimated_clear': clear})

    def drive(self, robot, target, state):
        estimator = self.estimators[robot]
        route = self.world.plan(estimator.pose[:2], target[:2])
        self.emit('ROUTE', self.t, robot, state, {'waypoints_m': route, 'planner': 'inflated_grid_A_star'})
        for index, waypoint in enumerate(route[1:]):
            final = index == len(route) - 2
            tolerance = .018 if final else .045
            start = self.t
            while True:
                delta = np.array(waypoint) - estimator.pose[:2]
                distance = float(np.linalg.norm(delta))
                if distance < tolerance:
                    break
                if self.t - start > 90:
                    raise MobileHold('NAV_PROGRESS_TIMEOUT')
                error = wrap(math.atan2(delta[1], delta[0]) - estimator.pose[2])
                # Stop to turn, avoiding large corner arcs through inflated obstacles.
                linear = min(.38, 1.0 * distance) * max(0., math.cos(error)) if abs(error) < .35 else 0.
                angular = float(np.clip(2.4 * error, -1.2, 1.2))
                self.tick(robot, [linear - angular * TRACK_M / 2, linear + angular * TRACK_M / 2], state)
        start = self.t
        while abs(wrap(target[2] - estimator.pose[2])) > .018:
            if self.t - start > 15:
                raise MobileHold('DOCK_HEADING_TIMEOUT')
            angular = float(np.clip(2.4 * wrap(target[2] - estimator.pose[2]), -.8, .8))
            self.tick(robot, [-angular * TRACK_M / 2, angular * TRACK_M / 2], state)
        # Finish with acceleration-limited deceleration, then stationary sensor samples.
        for _ in range(15):
            self.tick(robot, [0., 0.], state)


def metrics_from_rows(rows):
    samples = [r for r in rows if r['event'] == 'SAMPLE']
    distance = 0.; last = {}; errors = []; speed = []; accel = []
    for row in samples:
        robot, data = row['robot'], row['data']
        pose, estimate = np.array(data['truth_pose_m_rad']), np.array(data['estimate_pose_m_rad'])
        if robot in last:
            distance += float(np.linalg.norm(pose[:2] - last[robot][:2]))
        last[robot] = pose
        errors.append(float(np.linalg.norm(pose[:2] - estimate[:2])))
        speed.extend(abs(v) for v in data['wheel_m_s'])
        accel.extend(abs(v) for v in data['wheel_accel_m_s2'])
    return dict(sample_count=len(samples), distance_m=distance,
                localization_rmse_m=float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
                max_wheel_speed_m_s=max(speed, default=0.), max_wheel_acceleration_m_s2=max(accel, default=0.),
                collision_count=sum(r['data']['collision'] for r in samples),
                sim_duration_s=max((r['mission_time_s'] for r in rows), default=0.),
                zone_max_simultaneous_occupants=max((len(r['data']['zone_occupied']) for r in samples), default=0))


def trajectory_svg(rows, world):
    """Static map plot derived directly from logged plant and estimate samples."""
    scale = 100.
    def point(p):
        return f'{50 + scale * p[0]:.3f},{650 - scale * p[1]:.3f}'
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="720" viewBox="0 0 900 720">',
             '<rect width="900" height="720" fill="#fafafa"/>',
             '<text x="50" y="25" font-family="sans-serif" font-size="18">Computed trajectory: kinematic simulator (not wheel/contact physics)</text>',
             '<rect x="50" y="50" width="800" height="600" fill="white" stroke="#222"/>']
    for rect in world.obstacles:
        left, bottom, right, top = rect
        parts.append(f'<rect x="{50 + scale * left}" y="{650 - scale * top}" width="{scale * (right - left)}" height="{scale * (top - bottom)}" fill="#ddd" stroke="#555"/>')
    left, bottom, right, top = world.config['shared_zone_m']
    parts.append(f'<rect x="{50 + scale * left}" y="{650 - scale * top}" width="{scale * (right - left)}" height="{scale * (top - bottom)}" fill="none" stroke="#555" stroke-dasharray="6 4"/>')
    for robot, colors in [('amr-1', ('#164d9c', '#f29d28')), ('amr-2', ('#177145', '#a14b99'))]:
        samples = [r['data'] for r in rows if r['event'] == 'SAMPLE' and r['robot'] == robot]
        for key, color in zip(('truth_pose_m_rad', 'estimate_pose_m_rad'), colors):
            points = ' '.join(point(row[key]) for row in samples)
            parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>')
    dock = world.config['dock_m_rad']
    parts.append(f'<circle cx="{50 + scale * dock[0]}" cy="{650 - scale * dock[1]}" r="6" fill="none" stroke="black"/>')
    parts += ['<text x="50" y="680" font-family="sans-serif" font-size="14">x east / y north [m]; room 8 x 6 m; dashed = exclusive zone; circle = dock</text>',
              '<text x="50" y="703" font-family="sans-serif" font-size="13">amr-1: blue truth / orange EKF; amr-2: green truth / purple EKF. Lines are measured samples.</text>', '</svg>']
    return '\n'.join(parts)


def run_mission(seed=0, scenario='normal', out_dir='runs/mobile', mission_id=None,
                pick_runner=None, cancel=None, sim_deadline_s=240., wall_deadline_s=120.):
    """Drive -> accepted dock -> existing physics job -> exit -> second robot task.

    An injected pick_runner is for lightweight orchestration tests only. The CLI always
    invokes the existing engine and labels that physics provenance in the manifest.
    """
    if scenario not in ('normal', 'blocked', 'zone_contention'):
        raise ValueError('unsupported mobile scenario')
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    started = time.monotonic(); mission_id = mission_id or f'mobile-{scenario}-{seed}-{uuid.uuid4().hex[:8]}'
    if Path(mission_id).name != mission_id or mission_id in ('.', '..'):
        raise ValueError('mission_id must be a single path component')
    directory = Path(out_dir) / mission_id; directory.mkdir(parents=True, exist_ok=False)
    rows = []; job_id = mission_id + '-pick'; pick_result = None; next_task = None
    def emit(event, now, robot=None, state=None, data=None):
        row = dict(schema_version=1, event_id=len(rows), mission_id=mission_id, job_id=job_id,
                   mission_time_s=round(now, 6), robot=robot, state=state, event=event, data=data or {})
        rows.append(row)
        handle.write(json.dumps(row, allow_nan=False) + '\n'); handle.flush()
    world = MobileMap.load(); fleet = FleetScheduler(world.config['robot_starts_m_rad'])
    cancel = cancel or threading.Event()
    sim = MobileSimulation(world, seed, emit, fleet, cancel, sim_deadline_s, started + wall_deadline_s)
    status, reason = 'HELD', None
    with (directory / 'trajectory.jsonl').open('w') as handle:
        emit('MISSION_START', 0., data={'seed': seed, 'scenario': scenario, 'frame': world.config['frame']})
        try:
            sim.guard()
            if scenario == 'blocked':
                world.obstacles.append([3.2, 0., 3.7, 6.])
            poses = {name: ekf.pose for name, ekf in sim.estimators.items()}
            robot = fleet.allocate(job_id, world.config['dock_m_rad'], poses)
            other_task = mission_id + '-reposition'
            other = fleet.allocate(other_task, world.config['next_task_m_rad'], poses)
            emit('TASK_ALLOCATED', sim.t, robot, 'QUEUED', {'task_id': job_id})
            emit('TASK_ALLOCATED', sim.t, other, 'QUEUED', {'task_id': other_task})
            if scenario == 'zone_contention':
                fleet.acquire(other, sim.t); fleet.enter(other, sim.t)
                # A stationary contending robot physically occupies the reserved zone.
                sim.truth[other] = np.array([6.2, 2., 0.])
                sim.estimators[other] = PoseEKF([6.2, 2., 0.])
                emit('CONTENDING_ROBOT', sim.t, other, 'STATIONARY', {'pose_m_rad': sim.truth[other].tolist()})
            # Plan before reserving; an impossible route never obtains a lease.
            world.plan(sim.estimators[robot].pose[:2], world.config['dock_m_rad'][:2])
            wait_start = sim.t
            while not fleet.acquire(robot, sim.t):
                if sim.t - wait_start >= 5.:
                    raise MobileHold('ZONE_WAIT_TIMEOUT')
                sim.tick(robot, [0., 0.], 'WAIT_ZONE')
            emit('ZONE_RESERVED', sim.t, robot, 'NAVIGATING', {'expires_s': fleet.expires})
            sim.drive(robot, world.config['dock_m_rad'], 'NAVIGATING')
            sim.require_dock(robot)
            sim.guard()
            # The pick engine bounds itself to 60 simulated seconds; reserve that budget.
            if sim.t + 60 >= sim_deadline_s:
                raise MobileHold('SIM_DEADLINE')
            fleet.renew(robot, sim.t)
            emit('PICK_STARTED', sim.t, robot, 'PICKING', {'picker': 'engine.run_job' if pick_runner is None else 'injected_test_runner'})
            if pick_runner is None:
                from .engine import run_job
                runner = run_job
            else:
                runner = pick_runner
            pick_result = runner(seed=seed, fault='normal', policy='recovery', out_dir=directory / 'pick',
                                 job_id=job_id, record=False, cancel=DeadlineCancel(cancel, sim.wall_deadline))
            sim.t += float(pick_result.get('sim_duration_s', 0.))
            emit('PICK_FINISHED', sim.t, robot, 'PICKING', {'run_id': pick_result.get('run_id'),
                                                        'job_id': pick_result.get('job_id'), 'success': pick_result.get('success')})
            sim.guard(); fleet.renew(robot, sim.t)
            if not pick_result.get('success') or pick_result.get('job_id') != job_id:
                raise MobileHold('PICK_NOT_VERIFIED')
            sim.drive(robot, world.config['exit_m_rad'], 'EXITING')
            sim.release_clear_zone(robot)
            fleet.finished.add(job_id)
            # The next queued fleet task is a real computed reposition, not another pick.
            sim.drive(other, world.config['next_task_m_rad'], 'NEXT_TASK')
            fleet.finished.add(other_task)
            next_task = {'task_id': other_task, 'robot': other, 'type': 'reposition', 'status': 'COMPLETED'}
            emit('NEXT_TASK_COMPLETED', sim.t, other, 'COMPLETED', next_task)
            status = 'COMPLETED'
        except MobileHold as exc:
            reason = str(exc); status = 'CANCELLED' if reason == 'CANCELLED' else 'HELD'
        except Exception as exc:
            reason = 'UNHANDLED_' + type(exc).__name__
            emit('EXCEPTION', sim.t, state='HELD', data={'type': type(exc).__name__, 'message': str(exc)})
        # Safety braking is simulated and logged, not a hardware braking certificate.
        # Expired/occupied zone ownership remains retained and cannot be reassigned.
        if status != 'COMPLETED':
            emit('STOP_COMMAND', sim.t, state=status, data={'reason': reason, 'zone_owner_retained': fleet.owner})
            try:
                sim.brake_to_rest()
            except MobileHold as exc:
                reason = reason + '_BRAKE_' + str(exc)
                emit('BRAKE_FAILED', sim.t, state=status, data={'reason': str(exc)})
        emit('TERMINAL', sim.t, state=status, data={'reason': reason})
    (directory / 'trajectory.svg').write_text(trajectory_svg(rows, world))
    # Hash all extension inputs and fixed-cell runtime source/assets/model.
    paths = [ROOT / 'scripts/run_mobile.py', ROOT / 'models/appearance.pt']
    for prefix in ('src', 'cpp', 'assets', 'configs'):
        paths += [p for p in sorted((ROOT / prefix).rglob('*')) if p.is_file()
                  and '__pycache__' not in str(p) and p.suffix != '.pyc']
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema_version=1, mission_id=mission_id, job_id=job_id, seed=seed, scenario=scenario,
                  status=status, reason=reason, pick_result=pick_result, next_task=next_task,
                  physics_picker=pick_runner is None and any(r['event'] == 'PICK_STARTED' for r in rows),
                  picker_backend='engine.run_job' if pick_runner is None else 'injected_test_runner',
                  metrics=metrics_from_rows(rows), wall_duration_s=time.monotonic() - started,
                  provenance={'source_sha256': digest, 'source_files': hashes,
                              'trajectory_sha256': hashlib.sha256((directory / 'trajectory.jsonl').read_bytes()).hexdigest()},
                  model='differential_drive_kinematic_known_map_EKF', slam_implemented=False,
                  frame=world.config['frame'], limits={'dt_s': DT, 'track_m': TRACK_M,
                    'max_wheel_speed_m_s': MAX_WHEEL_M_S, 'max_wheel_accel_m_s2': MAX_WHEEL_ACCEL_M_S2,
                    'sim_deadline_s': sim_deadline_s, 'wall_deadline_s': wall_deadline_s},
                  final_zone={'owner': fleet.owner, 'occupied': sorted(fleet.occupied), 'fenced': fleet.fenced})
    (directory / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    return result
