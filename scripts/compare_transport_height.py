#!/usr/bin/env python3
"""Paired height-rule experiment on an archived, identical physical model.

No production source is edited. Run from the repository root; only the Python
environment must be installed. The default revision deliberately stays pinned.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_REVISION = '5643fd6'
VARIANTS = ('before', 'after')
SCENARIOS = ('normal', 'path_blocked', 'suction_once', 'suction_permanent', 'mixed')
DEFAULT_SEEDS = (64000, 64001, 64002, 64003)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def validate_seeds(seeds):
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or s < 0 for s in seeds):
        raise ValueError('Use distinct nonnegative integer seeds')


def new_output(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    return path


def make_cases(seeds, make_condition, condition_id):
    validate_seeds(seeds)
    cases = []
    for seed in seeds:
        for scenario in SCENARIOS:
            fault = 'path_blocked' if scenario == 'mixed' else scenario
            condition = make_condition(seed, fault, 'heldout')
            if scenario == 'mixed':
                # Same sampled outage as the suction-only case, with the same
                # sampled layout and blocker as the path-only case. No outcome tuning.
                condition['suction']['outage_windows_s'] = make_condition(
                    seed, 'suction_once', 'heldout')['suction']['outage_windows_s']
                condition['condition_id'] = condition_id(condition)
            cases.append(dict(case_id=f'{scenario}-{seed}', scenario=scenario,
                              seed=seed, fault=fault, condition=condition))
    return cases


@contextmanager
def height_override(controller_class, variant, trace):
    if variant not in VARIANTS:
        raise ValueError('Unknown height variant')
    original = controller_class.transport_height

    def measured(controller):
        if variant == 'before':
            height = .40 if controller.policy == 'recovery' and controller.attempt > 1 else .30
        else:
            height = original.__get__(controller, controller_class)
        trace.append(dict(sim_time=controller.cell.sim_time, state=controller.state,
                          attempt=controller.attempt, policy=controller.policy,
                          last_error=None if controller.last_error is None else controller.last_error.code,
                          height_m=height))
        return height

    controller_class.transport_height = property(measured)
    try:
        yield
    finally:
        controller_class.transport_height = original


def fingerprint(provenance):
    return provenance['source_sha256'], provenance['model_sha256']


def summarize_records(records):
    pairs = defaultdict(dict)
    for row in records:
        if row['variant'] in pairs[row['case_id']]:
            raise ValueError('DUPLICATE_PAIR')
        pairs[row['case_id']][row['variant']] = row
    output_pairs = []
    outcomes = dict(both_completed=0, before_only=0, after_only=0, neither_completed=0)
    for case_id, pair in sorted(pairs.items()):
        if set(pair) != set(VARIANTS):
            raise ValueError('INCOMPLETE_PAIR')
        before, after = (pair[v]['result'] for v in VARIANTS)
        for field in ('condition', 'initial_truth', 'seed', 'fault', 'policy'):
            if before[field] != after[field]:
                raise ValueError(f'{field.upper()}_MISMATCH')
        if fingerprint(before['provenance']) != fingerprint(after['provenance']):
            raise ValueError('SOURCE_OR_MODEL_MISMATCH')
        key = ('both_completed' if before['success'] and after['success'] else
               'before_only' if before['success'] else 'after_only' if after['success'] else 'neither_completed')
        outcomes[key] += 1
        entry = dict(case_id=case_id, scenario=pair['before']['scenario'], seed=before['seed'],
                     condition_id=before['condition']['condition_id'], same_initial_truth=True,
                     delta_sim_s=after['metrics']['sim_duration_s'] - before['metrics']['sim_duration_s'],
                     delta_wall_s=after['metrics']['wall_duration_s'] - before['metrics']['wall_duration_s'])
        for variant in VARIANTS:
            r = pair[variant]['result']
            entry[variant] = dict(run_id=r['run_id'], job_id=r['job_id'], status=r['status'],
                                 success=r['success'], reason=r['reason'], result_path=pair[variant]['result_path'],
                                 **{k: r['metrics'][k] for k in ('sim_duration_s', 'wall_duration_s',
                                     'retries', 'drops', 'collisions', 'wrong_placements', 'timeout')})
        output_pairs.append(entry)

    def aggregate(rows):
        n = len(rows)
        results = [row['result'] for row in rows]
        completed = sum(bool(r['success']) for r in results)
        total_sim = sum(r['metrics']['sim_duration_s'] for r in results)
        total_wall = sum(r['metrics']['wall_duration_s'] for r in results)
        return dict(n=n, completed=completed, held=sum(r['status'] == 'HELD' for r in results),
                    completion_rate=completed/n, total_sim_s=total_sim, mean_sim_s=total_sim/n,
                    total_wall_s=total_wall, mean_wall_s=total_wall/n,
                    throughput_per_sim_hour=3600*completed/total_sim if total_sim else None,
                    **{key: sum(r['metrics'][key] for r in results)
                       for key in ('retries', 'drops', 'collisions', 'wrong_placements', 'timeout')})

    if not records:
        raise ValueError('INCOMPLETE_BATCH')
    return dict(aggregate={v: aggregate([r for r in records if r['variant'] == v]) for v in VARIANTS},
                by_condition=[dict(scenario=s, variant=v,
                                   **aggregate([r for r in records if r['scenario'] == s and r['variant'] == v]))
                              for s in sorted({r['scenario'] for r in records}) for v in VARIANTS],
                paired_outcomes=outcomes, pairs=output_pairs)


def audit(directory):
    """Recompute only from saved files; never execute physics or change results."""
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if digest(manifest['cases']) != manifest['cases_sha256']:
        raise ValueError('MANIFEST_CASES_MISMATCH')
    records, raw_files = [], []
    expected_paths = set()
    for case in manifest['cases']:
        for variant in VARIANTS:
            folder = directory/'raw'/case['case_id']/variant
            result_path = folder/'result.json'
            expected_paths.add(result_path)
            r = json.loads(result_path.read_text())
            if (r['condition'] != case['condition'] or r['seed'] != case['seed'] or
                    r['fault'] != case['fault'] or r['policy'] != 'recovery'):
                raise ValueError('FROZEN_CONDITION_MISMATCH')
            if fingerprint(r['provenance']) != fingerprint(manifest['runtime_provenance']):
                raise ValueError('FROZEN_SOURCE_OR_MODEL_MISMATCH')
            events = [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
            if [e['event_id'] for e in events] != list(range(len(events))):
                raise ValueError('EVENT_SEQUENCE_MISMATCH')
            terminals = [e for e in events if e['event'] == 'TERMINAL']
            if len(terminals) != 1 or any(terminals[0]['data'][k] != r[k]
                                         for k in ('status', 'success', 'reason', 'metrics')):
                raise ValueError('TERMINAL_RESULT_MISMATCH')
            if r['success'] and not (r['metrics']['verified_by_vision'] and
                                     r['metrics']['verified_by_truth'] and not r['metrics']['wrong_placements']):
                raise ValueError('UNVERIFIED_COMPLETION')
            trace = json.loads((folder/'height-trace.json').read_text())
            for decision in trace:
                high = decision['attempt'] > 1 and (variant == 'before' or decision['last_error'] == 'PATH_BLOCKED')
                if decision['policy'] != 'recovery' or decision['height_m'] != (.40 if high else .30):
                    raise ValueError('HEIGHT_INTERVENTION_MISMATCH')
            records.append(dict(case_id=case['case_id'], scenario=case['scenario'], variant=variant,
                                result_path=str(result_path.relative_to(directory)), result=r))
            for path in (result_path, folder/'events.jsonl', folder/'height-trace.json'):
                raw_files.append(dict(path=str(path.relative_to(directory)), sha256=file_hash(path)))
    if set(directory.glob('raw/*/*/result.json')) != expected_paths:
        raise ValueError('UNEXPECTED_CASE_FILES')
    summary = dict(schema_version=1, experiment='current-model-transport-height',
                   executor=manifest['executor'], snapshot_commit=manifest['snapshot_commit'],
                   cases_sha256=manifest['cases_sha256'],
                   provenance=manifest['runtime_provenance'], harness_sha256=manifest['harness_sha256'],
                   **summarize_records(records), raw_files=raw_files,
                   audit=dict(complete_pairs=len(manifest['cases']), raw_results=len(records),
                              identical_conditions=True, identical_initial_truth=True,
                              source_and_model_frozen=True, terminal_events_match=True,
                              height_decisions_checked=True),
                   scope='Small descriptive synthetic comparison; no hardware or population-level claim. '
                         'All failed-run times included. Wall time is shared-environment timing, not a speedup claim.')
    existing = directory/'summary.json'
    if existing.exists() and json.loads(existing.read_text()) != summary:
        raise ValueError('PUBLISHED_SUMMARY_OR_RAW_HASH_MISMATCH')
    return summary


def save_summary(directory, summary):
    write_json(directory/'summary.json', summary)
    fields = ['case_id', 'scenario', 'seed', 'condition_id', 'before_status', 'after_status',
              'before_sim_s', 'after_sim_s', 'delta_sim_s', 'before_wall_s', 'after_wall_s', 'delta_wall_s',
              'before_drops', 'after_drops', 'before_collisions', 'after_collisions']
    with (directory/'pairs.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for pair in summary['pairs']:
            row = {k: pair[k] for k in ('case_id', 'scenario', 'seed', 'condition_id', 'delta_sim_s', 'delta_wall_s')}
            for variant in VARIANTS:
                for short, original in [('status', 'status'), ('sim_s', 'sim_duration_s'),
                                        ('wall_s', 'wall_duration_s'), ('drops', 'drops'), ('collisions', 'collisions')]:
                    row[f'{variant}_{short}'] = pair[variant][original]
            writer.writerow(row)
    lines = ['# Current-model transport-height comparison', '',
             f"Executor label: {summary['executor']}. Snapshot: `{summary['snapshot_commit']}`.", '',
             'Before: 0.40 m after any failure. After: 0.40 m only after PATH_BLOCKED. Both use the same archived physical model, recovery policy and three-attempt budget.', '',
             '| Rule | Completed | Mean simulated s | Mean wall s | Drops | Collisions | Wrong placements |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for variant, a in summary['aggregate'].items():
        lines.append(f"| {variant} | {a['completed']}/{a['n']} | {a['mean_sim_s']:.3f} | {a['mean_wall_s']:.3f} | {a['drops']} | {a['collisions']} | {a['wrong_placements']} |")
    lines += ['', 'All failures remain in time denominators. Wall time is environment-specific; no wall-speedup claim.', '',
              '| Case | Before | After | Before sim s | After sim s | After − before s |',
              '|---|---|---|---:|---:|---:|']
    for pair in summary['pairs']:
        b, a = pair['before'], pair['after']
        lines.append(f"| {pair['case_id']} | {b['status']} | {a['status']} | {b['sim_duration_s']:.3f} | {a['sim_duration_s']:.3f} | {pair['delta_sim_s']:+.3f} |")
    lines += ['', 'See `manifest.json`, `summary.json`, `pairs.csv` and `raw/` for frozen inputs, identities, decision traces and native evidence.',
              'This small fixed scenario mixture supports descriptive comparison only; it does not establish a generally optimal rule or hardware safety.']
    (directory/'summary.md').write_text('\n'.join(lines)+'\n')


def run(directory, seeds, revision, executor):
    validate_seeds(seeds)
    if any(name == 'pickloop' or name.startswith('pickloop.') for name in sys.modules):
        raise RuntimeError('Run in a fresh Python process so the archived runtime is authoritative')
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ.setdefault('MUJOCO_GL', 'egl')
    commit = subprocess.check_output(['git', 'rev-parse', revision+'^{commit}'], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', '--format=tar', commit,
                                       'src', 'cpp', 'assets', 'configs', 'models'], cwd=ROOT)
    directory = new_output(Path(directory).resolve())
    # Outside any checkout: native provenance honestly says uncommitted, while
    # manifest.snapshot_commit + content hashes identify the archived Git source.
    scratch_parent = Path(tempfile.gettempdir())/'work'
    scratch_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pickloop-height-', dir=scratch_parent) as temporary:
        snapshot = Path(temporary)/'snapshot'
        snapshot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                relative = Path(member.name)
                if relative.is_absolute() or '..' in relative.parts or not (member.isdir() or member.isfile()):
                    raise ValueError('Unsupported archive member')
                target = snapshot/relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
        sys.path.insert(0, str(snapshot/'src'))
        from pickloop.conditions import make_condition, condition_id
        from pickloop.journal import source_provenance
        cases = make_cases(seeds, make_condition, condition_id)
        manifest = dict(schema_version=1, frozen_at=datetime.now(timezone.utc).isoformat(),
                        snapshot_commit=commit, archive_sha256=hashlib.sha256(archive).hexdigest(),
                        harness_sha256=file_hash(__file__), runtime_provenance=source_provenance(snapshot),
                        executor=executor, seeds=seeds, scenarios=list(SCENARIOS), cases=cases,
                        cases_sha256=digest(cases), model_family='current guided-lift MuJoCo cell',
                        variants={'before': '0.40m iff recovery and attempt>1',
                                  'after': 'unmodified current property: 0.40m iff recovery, attempt>1, last error PATH_BLOCKED'},
                        fixed=dict(policy='recovery', sku='SKU-RED-A', max_attempts=3,
                                   sim_budget_s=60, wall_budget_s=90, record=False, bin_layout=None),
                        success_criterion='Native visual placement verification AND independent correct-SKU settled/released truth; failures kept.',
                        condition_family='Existing heldout parameter ranges; new seeds, not a new distribution claim.',
                        order='alternate before/after first by seed index + scenario index',
                        scope='Codex and personal runs must retain separate executor labels and output directories.',
                        environment=dict(python=sys.version, platform=platform.platform(),
                                         packages={p: importlib.metadata.version(p) for p in ('mujoco', 'numpy', 'torch', 'py-trees')},
                                         requested_threads=1, legacy_model_torch_threads=2,
                                         wall_time_shared_environment=True))
        write_json(directory/'manifest.json', manifest)  # Must exist before the first engine invocation.
        print(f'FROZEN {len(cases)} pairs / {2*len(cases)} trials: {directory / "manifest.json"}', flush=True)
        from pickloop import engine
        if Path(engine.__file__).resolve().parent != snapshot/'src'/'pickloop':
            raise RuntimeError('Runtime import did not resolve to the isolated archive')
        # The legacy appearance model sets torch to two CPU threads when loaded;
        # retain that identical existing behavior in both arms and record it.
        for index, case in enumerate(cases):
            order = VARIANTS if (index//len(SCENARIOS)+index%len(SCENARIOS)) % 2 == 0 else VARIANTS[::-1]
            for variant in order:
                if (fingerprint(source_provenance(snapshot)) != fingerprint(manifest['runtime_provenance']) or
                        file_hash(__file__) != manifest['harness_sha256']):
                    raise RuntimeError('Frozen source, model or harness changed')
                trace = []
                folder = directory/'raw'/case['case_id']/variant
                folder.mkdir(parents=True)
                try:
                    with height_override(engine.Controller, variant, trace):
                        result = engine.run_job(seed=case['seed'], fault=case['fault'], policy='recovery',
                                                condition=case['condition'], record=False,
                                                job_id=f"height-{case['case_id']}-{variant}",
                                                out_dir=Path(temporary)/'native-runs')
                    native = Path(temporary)/'native-runs'/result['run_id']
                    for name in ('result.json', 'events.jsonl'):
                        shutil.copyfile(native/name, folder/name)
                except Exception as error:
                    write_json(folder/'interrupted.json', dict(type=type(error).__name__, error=str(error)))
                    for event_file in (Path(temporary)/'native-runs').glob('*/events.jsonl'):
                        lines = event_file.read_text().splitlines()
                        if lines and json.loads(lines[0]).get('job_id') == f"height-{case['case_id']}-{variant}":
                            shutil.copyfile(event_file, folder/'events.jsonl')
                    raise  # Never publish a partial batch as a successful comparison.
                finally:
                    write_json(folder/'height-trace.json', trace)
                print(f"{case['case_id']:25} {variant:6} {result['status']:10} "
                      f"sim={result['sim_duration_s']:.3f}s reason={result['reason']}", flush=True)
        summary = audit(directory)
        save_summary(directory, summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    execute = commands.add_parser('run', help='freeze and execute both rules into a NEW output directory')
    execute.add_argument('--out', type=Path, required=True)
    execute.add_argument('--seed', type=int, nargs='+', default=list(DEFAULT_SEEDS))
    execute.add_argument('--revision', default=REFERENCE_REVISION)
    execute.add_argument('--executor', default='unrecorded', help='Honest operator label; does not verify personal authorship')
    verify = commands.add_parser('audit', help='verify saved results and recompute summary without physics')
    verify.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out, args.seed, args.revision, args.executor) if args.command == 'run' else audit(args.out)
    print(json.dumps(dict(audit=result['audit'], aggregate=result['aggregate'],
                         paired_outcomes=result['paired_outcomes']), indent=2))


if __name__ == '__main__':
    main()
