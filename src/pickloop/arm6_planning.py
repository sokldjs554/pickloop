"""Six-revolute-joint planning and actuator effort in a standalone MuJoCo cell."""

import argparse
from dataclasses import dataclass
from itertools import combinations
import json
from pathlib import Path

import mujoco
import numpy as np


DEMO_START = np.array([-0.92, -0.18, 0.37, -0.28, 0.28, -0.53])
DEMO_GOAL = np.array([0.88, -0.08, 0.48, 0.33, 0.17, 0.47])
DEMO_SEEDS = (3, 17, 41)
PLANNING_STEP_RAD = 0.02
VALIDATION_STEP_RAD = 0.005
CLEARANCE_M = 0.008
EXTENSION_RAD = 0.28

_SCENE_XML = """
<mujoco model="pickloop_arm6">
  <compiler angle="radian"/>
  <option timestep=".002" integrator="implicitfast"/>
  <default>
    <joint type="hinge" limited="true" armature=".015" damping=".15"/>
    <geom type="capsule" density="450" rgba=".16 .48 .58 1"/>
    <motor gear="1" forcelimited="true"/>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 .05" rgba=".28 .30 .36 1"/>
    <geom name="pedestal" type="cylinder" pos="0 0 .24" size=".09 .24" rgba=".30 .40 .45 1"/>
    {fixture}
    <body name="base_yaw" pos="0 0 .49">
      <joint name="j1" axis="0 0 1" range="-2.8 2.8"/>
      <geom name="link1" fromto="0 0 .012 0 0 .068" size=".055"/>
      <body name="shoulder" pos="0 0 .09">
        <joint name="j2" axis="0 1 0" range="-1.7 1.4"/>
        <geom name="link2" fromto="0 0 0 .32 0 0" size=".043"/>
        <body name="elbow" pos=".32 0 0">
          <joint name="j3" axis="0 1 0" range="-2.15 2.15"/>
          <geom name="link3" fromto="0 0 0 .255 0 0" size=".037"/>
          <body name="forearm_roll" pos=".255 0 0">
            <joint name="j4" axis="1 0 0" range="-2.8 2.8"/>
            <geom name="link4" fromto="0 0 0 .105 .026 0" size=".03"/>
            <body name="wrist_pitch" pos=".105 .026 0">
              <joint name="j5" axis="0 1 0" range="-1.8 1.8"/>
              <geom name="link5" fromto="0 0 0 .09 0 .02" size=".025"/>
              <body name="tool_roll" pos=".09 0 .02">
                <joint name="j6" axis="1 0 0" range="-2.8 2.8"/>
                <geom name="link6" fromto="0 0 0 .13 0 -.063" size=".024"/>
                <site name="tool_tip" pos=".13 0 -.063" size=".008" rgba="1 .7 .2 1"/>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="m1" joint="j1" forcerange="-60 60"/>
    <motor name="m2" joint="j2" forcerange="-60 60"/>
    <motor name="m3" joint="j3" forcerange="-40 40"/>
    <motor name="m4" joint="j4" forcerange="-16 16"/>
    <motor name="m5" joint="j5" forcerange="-12 12"/>
    <motor name="m6" joint="j6" forcerange="-8 8"/>
  </actuator>
  <sensor>
    <jointactuatorfrc name="t1" joint="j1"/>
    <jointactuatorfrc name="t2" joint="j2"/>
    <jointactuatorfrc name="t3" joint="j3"/>
    <jointactuatorfrc name="t4" joint="j4"/>
    <jointactuatorfrc name="t5" joint="j5"/>
    <jointactuatorfrc name="t6" joint="j6"/>
  </sensor>
</mujoco>
"""
_FIXTURE_XML = (
    '<geom name="fixture" type="box" pos=".48 0 .31" size=".055 .10 .31" '
    'rgba=".84 .51 .18 1"/>'
)


@dataclass(frozen=True)
class SampleCheck:
    valid: bool
    separation_m: float | None
    blocking_pair: tuple[str, str] | None = None
    detail: str | None = None


@dataclass(frozen=True)
class EdgeCheck:
    valid: bool
    samples: int
    min_separation_m: float | None
    blocking_pair: tuple[str, str] | None = None
    blocking_q_rad: list[float] | None = None


@dataclass(frozen=True)
class PlanResult:
    status: str
    iterations: int
    waypoints_rad: np.ndarray
    direct: EdgeCheck | None = None
    detail: str | None = None


class Arm6Scene:
    def __init__(self, *, with_fixture: bool = True):
        self.model = mujoco.MjModel.from_xml_string(
            _SCENE_XML.format(fixture=_FIXTURE_XML if with_fixture else '')
        )
        self.data = mujoco.MjData(self.model)
        self.lower, self.upper = self.model.jnt_range.T.copy()
        links = [f'link{index}' for index in range(1, 7)]
        pairs = [(name, 'floor') for name in links]
        pairs.extend((name, 'pedestal') for name in links[1:])
        if with_fixture:
            pairs.extend((name, 'fixture') for name in links)
        # Adjacent capsules intentionally overlap at their shared joints.
        pairs.extend((links[i], links[j]) for i, j in combinations(range(len(links)), 2)
                     if j - i > 1)
        self.collision_pairs = [
            (pair, *(self.model.geom(name).id for name in pair)) for pair in pairs
        ]

    def configuration(self, q: np.ndarray) -> SampleCheck:
        q = np.asarray(q, dtype=float)
        if q.shape != self.lower.shape or not np.isfinite(q).all():
            return SampleCheck(False, None, detail='invalid_configuration')
        if np.any(q < self.lower) or np.any(q > self.upper):
            return SampleCheck(False, None, detail='joint_limit')
        self.data.qpos[:] = q
        mujoco.mj_kinematics(self.model, self.data)
        nearest = None
        minimum = 10.0
        for pair, left, right in self.collision_pairs:
            distance = mujoco.mj_geomDistance(self.model, self.data, left, right, 10.0, None)
            if distance < minimum:
                nearest, minimum = pair, distance
        if minimum <= CLEARANCE_M:
            detail = 'collision' if minimum <= 0 else 'clearance'
            return SampleCheck(False, minimum, nearest, detail)
        return SampleCheck(True, minimum)

    def edge(self, left: np.ndarray, right: np.ndarray, *, max_step_rad: float) -> EdgeCheck:
        if not np.isfinite(max_step_rad) or max_step_rad <= 0:
            raise ValueError('max_step_rad must be finite and positive')
        left = np.asarray(left, dtype=float)
        right = np.asarray(right, dtype=float)
        if left.shape != self.lower.shape or right.shape != self.upper.shape:
            raise ValueError('edge endpoints must have six coordinates')
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError('edge endpoints must be finite')
        subdivisions = max(1, int(np.ceil(np.max(np.abs(right - left)) / max_step_rad)))
        minimum = None
        for samples, q in enumerate(np.linspace(left, right, subdivisions + 1), 1):
            check = self.configuration(q)
            if check.separation_m is not None:
                minimum = check.separation_m if minimum is None else min(minimum, check.separation_m)
            if not check.valid:
                return EdgeCheck(False, samples, minimum, check.blocking_pair, q.tolist())
        return EdgeCheck(True, samples, minimum)


class _Tree:
    def __init__(self, root: np.ndarray):
        self.nodes = [root]
        self.parents = [-1]

    def nearest(self, q: np.ndarray) -> int:
        return int(np.argmin(np.sum((np.asarray(self.nodes) - q) ** 2, axis=1)))

    def extend(self, scene: Arm6Scene, target: np.ndarray) -> tuple[int | None, bool]:
        parent = self.nearest(target)
        origin = self.nodes[parent]
        distance = np.linalg.norm(target - origin)
        if distance == 0:
            return parent, True
        reached = distance <= EXTENSION_RAD
        node = target if reached else origin + (target - origin) * (EXTENSION_RAD / distance)
        if not scene.edge(origin, node, max_step_rad=PLANNING_STEP_RAD).valid:
            return None, False
        self.nodes.append(node)
        self.parents.append(parent)
        return len(self.nodes) - 1, reached

    def connect(self, scene: Arm6Scene, target: np.ndarray) -> int | None:
        while True:
            index, reached = self.extend(scene, target)
            if index is None or reached:
                return index

    def path(self, index: int) -> list[np.ndarray]:
        nodes = []
        while index != -1:
            nodes.append(self.nodes[index])
            index = self.parents[index]
        return nodes[::-1]


def plan_path(
    scene: Arm6Scene,
    start: np.ndarray,
    goal: np.ndarray,
    *,
    seed: int = 3,
    max_iterations: int = 2500,
) -> PlanResult:
    """Run bidirectional RRT-Connect in a bounded six-dimensional joint space."""
    if max_iterations < 0:
        raise ValueError('max_iterations must be nonnegative')
    start, goal = np.asarray(start, dtype=float), np.asarray(goal, dtype=float)
    empty = np.empty((0, scene.model.nq))
    for name, q in [('start', start), ('goal', goal)]:
        check = scene.configuration(q)
        if not check.valid:
            return PlanResult(f'invalid_{name}', 0, empty, detail=check.detail)
    direct = scene.edge(start, goal, max_step_rad=VALIDATION_STEP_RAD)
    if direct.valid:
        return PlanResult('direct_path', 0, np.stack((start, goal)), direct)

    rng = np.random.default_rng(seed)
    start_tree, goal_tree = _Tree(start), _Tree(goal)
    active, passive = start_tree, goal_tree
    for iterations in range(1, max_iterations + 1):
        target = rng.uniform(scene.lower, scene.upper)
        active_idx, _ = active.extend(scene, target)
        if active_idx is not None:
            passive_idx = passive.connect(scene, active.nodes[active_idx])
            if passive_idx is not None:
                first, second = active.path(active_idx), passive.path(passive_idx)
                if active is goal_tree:
                    first, second = second, first
                path = np.array([*first, *reversed(second[:-1])])
                if all(scene.edge(a, b, max_step_rad=VALIDATION_STEP_RAD).valid
                       for a, b in zip(path, path[1:])):
                    return PlanResult('path_found', iterations, path, direct)
        active, passive = passive, active

    return PlanResult('search_budget_exhausted', max_iterations, empty, direct)


def simulated_torque_probe(scene: Arm6Scene) -> dict:
    """Evaluate unit-transmission motor effort and virtual joint sensors at one state."""
    data = mujoco.MjData(scene.model)
    data.qpos[:] = DEMO_START
    data.ctrl[:] = [0.4, -1.2, 1.6, -2.2, 3.4, 12.0]
    mujoco.mj_forward(scene.model, data)
    return {
        'evaluation': 'mj_forward at one stationary state',
        'sensor_type': 'jointactuatorfrc',
        'q_rad': data.qpos.tolist(),
        'requested_motor_torque_nm': data.ctrl.tolist(),
        'joint_actuator_sensor_nm': data.sensordata.tolist(),
        'simulator_qfrc_actuator_nm': data.qfrc_actuator.tolist(),
    }


def run_demo() -> dict:
    scene = Arm6Scene()
    blocked = scene.edge(DEMO_START, DEMO_GOAL, max_step_rad=VALIDATION_STEP_RAD)
    plans = []
    for seed in DEMO_SEEDS:
        plan = plan_path(scene, DEMO_START, DEMO_GOAL, seed=seed)
        path = plan.waypoints_rad
        checks = [
            scene.edge(left, right, max_step_rad=VALIDATION_STEP_RAD)
            for left, right in zip(path, path[1:])
        ]
        plans.append({
            'seed': seed,
            'status': plan.status,
            'search_iterations': plan.iterations,
            'accepted_edges': len(checks),
            'sampled_configurations_including_shared_endpoints': sum(c.samples for c in checks),
            'minimum_sampled_separation_m': min((c.min_separation_m for c in checks), default=None),
            'joint_path_length_rad': float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum()),
            'waypoints_rad': path.tolist(),
        })
    invalid_goal_q = (DEMO_START + DEMO_GOAL) / 2
    outside_q = DEMO_START.copy()
    outside_q[4] = scene.upper[4] + 0.1
    invalid_goal = plan_path(scene, DEMO_START, invalid_goal_q)
    invalid_start = plan_path(scene, outside_q, DEMO_GOAL)
    exhausted = plan_path(scene, DEMO_START, DEMO_GOAL, max_iterations=0)
    clear_scene = Arm6Scene(with_fixture=False)
    clear = plan_path(clear_scene, DEMO_START, DEMO_GOAL)
    return {
        'engine': 'MuJoCo',
        'mujoco_version': mujoco.__version__,
        'numpy_version': np.__version__,
        'planner': 'bidirectional RRT-Connect',
        'joint_names': [scene.model.joint(i).name for i in range(scene.model.njnt)],
        'actuators': scene.model.nu,
        'joint_limits_rad': scene.model.jnt_range.tolist(),
        'collision_pairs': [pair for pair, _, _ in scene.collision_pairs],
        'start_rad': DEMO_START.tolist(),
        'goal_rad': DEMO_GOAL.tolist(),
        'required_discrete_clearance_m': CLEARANCE_M,
        'search_extension_joint_space_norm_rad': EXTENSION_RAD,
        'planning_edge_max_joint_step_rad': PLANNING_STEP_RAD,
        'validation_edge_max_joint_step_rad': VALIDATION_STEP_RAD,
        'direct_path_with_fixture': {
            'valid': blocked.valid,
            'samples_until_rejection': blocked.samples,
            'first_rejected_pair': blocked.blocking_pair,
            'first_rejected_q_rad': blocked.blocking_q_rad,
            'first_rejected_distance_m': blocked.min_separation_m,
            'midpoint_signed_distance_m': scene.configuration(invalid_goal_q).separation_m,
        },
        'direct_path_without_fixture': {
            'status': clear.status,
            'samples': clear.direct.samples if clear.direct is not None else 0,
            'minimum_sampled_separation_m': clear.direct.min_separation_m if clear.direct else None,
        },
        'invalid_goal': {'status': invalid_goal.status, 'detail': invalid_goal.detail,
                         'configuration_rad': invalid_goal_q.tolist()},
        'invalid_start': {'status': invalid_start.status, 'detail': invalid_start.detail,
                          'configuration_rad': outside_q.tolist()},
        'zero_search_budget': {'status': exhausted.status, 'iterations': exhausted.iterations},
        'detours': plans,
        'simulation_only_torque_probe': simulated_torque_probe(scene),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Write the JSON evidence to this file')
    args = parser.parse_args()
    report = json.dumps(run_demo(), indent=2, allow_nan=False) + '\n'
    if args.output is None:
        print(report, end='')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding='utf-8')


if __name__ == '__main__':
    main()
