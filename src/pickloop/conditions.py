"""Prespecified synthetic condition families, independent of policies and retries.

All values are SI except explicitly named pixels/kPa. Development and held-out
families have disjoint layout/yaw/noise/seal-parameter subranges. This is a
controlled synthetic distribution shift, not a claim about any real domain.
"""
import json
import hashlib
import numpy as np

SCHEMA = 'pickloop-condition-v1'
FAULTS = ('normal', 'occlusion', 'depth_missing', 'calibration_error', 'suction_once',
          'communication_delay', 'drop', 'path_blocked', 'suction_permanent',
          'unknown', 'stale_observation', 'connection_loss')
# Bounds are frozen before held-out outcomes are generated. Layout order A/B/U.
CONDITION_BOUNDS = {
    'development': {
        'xy_m': [((.300, .350), (-.225, -.185)), ((.450, .490), (-.180, -.130)), ((.180, .220), (-.135, -.090))],
        'abs_yaw_rad': (0., .32), 'depth_noise_std_m': (.00008, .00025),
        'persistent_bias_norm_m': (.0002, .0010), 'transient_bias_norm_m': (.018, .027),
        'sensor_release_s': (.80, 1.45), 'suction_release_s': (2.5, 4.5),
        'drop_start_s': (4.5, 6.0), 'drop_duration_s': (.25, .55),
        'sealed_pressure_abs_kpa': (52., 58.), 'seal_x_m': (.0185, .020),
        'seal_y_m': (.0125, .014), 'seal_z_m': (.0042, .0049),
        'wrench_limit_n': (23., 27.), 'blocker_top_m': (.265, .300),
        'mass_kg': (.075, .085), 'friction': (.75, .90), 'roi_halfwidth_px': (17, 23),
        'rpc_release_s': (3.5, 5.5), 'stale_age_s': (.50, .75),
    },
    'heldout': {
        'xy_m': [((.365, .405), (-.180, -.135)), ((.495, .520), (-.240, -.200)), ((.225, .260), (-.245, -.205))],
        'abs_yaw_rad': (.40, .80), 'depth_noise_std_m': (.00030, .00060),
        'persistent_bias_norm_m': (.0012, .0030), 'transient_bias_norm_m': (.028, .038),
        'sensor_release_s': (1.55, 2.65), 'suction_release_s': (4.6, 7.5),
        'drop_start_s': (6.2, 8.8), 'drop_duration_s': (.60, .95),
        'sealed_pressure_abs_kpa': (45., 51.), 'seal_x_m': (.015, .018),
        'seal_y_m': (.010, .012), 'seal_z_m': (.0030, .0040),
        'wrench_limit_n': (19., 22.), 'blocker_top_m': (.310, .365),
        'mass_kg': (.090, .105), 'friction': (.55, .70), 'roi_halfwidth_px': (24, 29),
        'rpc_release_s': (5.6, 7.8), 'stale_age_s': (.80, 1.10),
    },
}


def in_window(sim_time, window):
    """Half-open interval on absolute simulator time, never an attempt counter."""
    return float(window[0]) <= sim_time < float(window[1])



def condition_id(condition):
    """Stable identity over the complete canonical JSON value except its own ID."""
    payload={key:value for key,value in condition.items() if key!='condition_id'}
    canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
    digest=hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]
    return f"{condition['split']}-{condition['seed']}-{condition['fault']}-{digest}"


def make_condition(seed, fault, split='development'):
    if split not in CONDITION_BOUNDS:
        raise ValueError('split must be development or heldout')
    if fault not in FAULTS:
        raise ValueError('unsupported fault')
    if not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    bounds = CONDITION_BOUNDS[split]
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 73191, int(split == 'heldout')]))
    def sample(key):
        return float(rng.uniform(*bounds[key]))
    objects = []
    for name, xy in zip(('a', 'b', 'u'), bounds['xy_m']):
        objects.append({'name': name, 'xy_m': [float(rng.uniform(*axis)) for axis in xy],
                        'yaw_rad': sample('abs_yaw_rad') * int(rng.choice([-1, 1])),
                        'mass_kg': sample('mass_kg'), 'friction': sample('friction')})
    # Conservative circumscribed radii guarantee no initial package intersection.
    for i, obj in enumerate(objects):
        for other in objects[:i]:
            if np.linalg.norm(np.array(obj['xy_m']) - other['xy_m']) <= .086:
                raise ValueError('condition layout overlaps package clearance')
    bias_angle = float(rng.uniform(-np.pi, np.pi))
    bias_size = sample('persistent_bias_norm_m')
    transient_size = sample('transient_bias_norm_m')
    # Static image-region disturbance, derived once from configured initial layout
    # and nominal camera, never from a controller target or simulator segmentation.
    x, y = objects[0]['xy_m']
    focal = 480 / (2 * np.tan(np.pi / 8))
    center = [int(round(240 + focal * (x - .33) / 1.238)), int(round(240 - focal * y / 1.238))]
    half = int(rng.integers(bounds['roi_halfwidth_px'][0], bounds['roi_halfwidth_px'][1] + 1))
    roi = [max(0, center[0] - half), max(0, center[1] - half), min(480, center[0] + half), min(480, center[1] + half)]
    sensor = {'depth_noise_std_m': sample('depth_noise_std_m'), 'noise_quantum_s': .02,
              'noise_seed': int(rng.integers(1, 2**31)),
              'persistent_bias_xyz_m': [bias_size * float(np.cos(bias_angle)), bias_size * float(np.sin(bias_angle)), 0.],
              'transient_bias_xyz_m': [transient_size * int(rng.choice([-1, 1])), 0., 0.],
              'region_xyxy_px': roi, 'release_s': sample('sensor_release_s'),
              'stale_age_s': sample('stale_age_s')}
    suction_release = sample('suction_release_s')
    drop_start, drop_duration = sample('drop_start_s'), sample('drop_duration_s')
    suction = {'outage_windows_s': [[0., suction_release]] if fault == 'suction_once' else [[drop_start, drop_start + drop_duration]] if fault == 'drop' else [],
               'permanent_outage': fault == 'suction_permanent',
               'sealed_pressure_kpa': -sample('sealed_pressure_abs_kpa'),
               'seal_halfwidth_m': [sample('seal_x_m'), sample('seal_y_m')],
               'seal_z_tolerance_m': sample('seal_z_m'), 'wrench_limit_n': sample('wrench_limit_n')}
    result = {'schema': SCHEMA, 'seed': int(seed), 'fault': fault, 'split': split,
            'objects': objects, 'sensor': sensor, 'suction': suction,
            'blocker_top_m': sample('blocker_top_m'), 'communication_window_s': [0., sample('rpc_release_s')],
            'history_basis': 'absolute simulator time; fixed condition; no policy, attempt, or observation-count dependence'}
    result['condition_id']=condition_id(result)
    return result


def copy_condition(condition, seed, fault=None):
    """Snapshot the caller's JSON value; reject mismatched condition identities."""
    result = json.loads(json.dumps(condition, allow_nan=False))
    if result.get('schema') != SCHEMA:
        raise ValueError('unsupported condition schema')
    if result.get('seed') != seed:
        raise ValueError('condition seed mismatch')
    if fault is not None and result.get('fault') != fault:
        raise ValueError('condition fault mismatch')
    expected_id=condition_id(result)
    if result.get('condition_id',expected_id)!=expected_id:
        raise ValueError('condition_id does not match condition parameters')
    result['condition_id']=expected_id
    return result
