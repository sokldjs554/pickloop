"""Paired, frozen-condition evaluation. Metrics are reductions of saved raw results."""
import csv
import hashlib
import json
import platform
import statistics
import time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from .engine import run_job,FAULTS
from .journal import source_provenance
from .simulation import ROOT

FINAL_SEEDS=tuple(range(1000,1005))

def rate(n,d):return n/d if d else None

def wilson(k,n):
    if not n:return [None,None]
    z=1.96;p=k/n;den=1+z*z/n;c=(p+z*z/(2*n))/den;half=z*((p*(1-p)+z*z/(4*n))/n)**.5/den
    return [c-half,c+half]

def summarize(rows):
    n=len(rows);m=[r['metrics'] for r in rows];complete=sum(bool(r['success']) for r in rows)
    first=sum(bool(v['first_attempt_success']) for v in m);failed=n-first
    recovered=sum(bool(r['success'] and not r['metrics']['first_attempt_success']) for r in rows)
    simulated=sum(v['sim_duration_s'] for v in m);wall=sum(v['wall_duration_s'] for v in m)
    position=[v['position_error_m'] for v in m if v.get('position_error_m') is not None]
    recover_t=[v['recovery_sim_s'] for v in m if v.get('recovery_sim_s') is not None]
    selected=[v for v in m if v.get('selection_attempted')]
    known=[r for r in rows if r['sku']!='UNREGISTERED']
    mean=lambda x:statistics.mean(x) if x else None
    return dict(n=n,completed=complete,completion_rate=rate(complete,n),completion_wilson95=wilson(complete,n),first_attempt_success_rate=rate(first,n),first_attempt_pick_success_rate=rate(sum(v.get('first_attempt_pick_success',False) for v in m),n),first_attempt_failures=failed,recovered=recovered,recovery_rate=rate(recovered,failed),wrong_placements=sum(v['wrong_placements'] for v in m),drops=sum(v['drops'] for v in m),collisions=sum(v['collisions'] for v in m),held=sum(r['status']=='HELD' for r in rows),retries=sum(v['retries'] for v in m),timeouts=sum(v.get('timeout',False) for v in m),selection_precision=rate(sum(v.get('selection_correct',False) for v in selected),len(selected)),known_task_selection_rate=rate(sum(r['metrics'].get('selection_correct',False) for r in known),len(known)),position_error_mean_m=mean(position),position_error_max_m=max(position) if position else None,mean_sim_s=rate(simulated,n),mean_wall_s=rate(wall,n),mean_recovery_sim_s=mean(recover_t),total_sim_s=simulated,total_wall_s=wall,throughput_per_sim_hour=rate(complete*3600,simulated),throughput_per_wall_hour=rate(complete*3600,wall))


def validate_pairs(rows):
    pairs=defaultdict(dict)
    for r in rows:
        key=(r['seed'],r['fault'])
        if r['policy'] in pairs[key]:raise ValueError('DUPLICATE_PAIR')
        pairs[key][r['policy']]=r
    if any(set(v)!={'baseline','recovery'} for v in pairs.values()):raise ValueError('INCOMPLETE_PAIR')
    for key,pair in pairs.items():
        if 'initial_truth' in pair['baseline'] and pair['baseline']['initial_truth']!=pair['recovery']['initial_truth']:
            raise ValueError(f'INITIAL_STATE_MISMATCH:{key}')
    return pairs


def aggregate(directory):
    directory=Path(directory);paths=sorted(directory.glob('*/result.json'))
    rows=[json.loads(p.read_text()) for p in paths]
    pairs=validate_pairs(rows)
    groups=defaultdict(list)
    for r in rows:groups[(r['fault'],r['policy'])].append(r)
    by_seed=[]
    for seed in sorted({r['seed'] for r in rows}):
        for policy in ('baseline','recovery'):
            by_seed.append(dict(seed=seed,policy=policy,**summarize([r for r in rows if r['seed']==seed and r['policy']==policy])))
    result=dict(schema_version=1,generated_at=datetime.now(timezone.utc).isoformat(),aggregate={p:summarize([r for r in rows if r['policy']==p]) for p in ('baseline','recovery')},conditions=[dict(fault=f,policy=p,**summarize(rs)) for (f,p),rs in sorted(groups.items())],seeds=by_seed,pairs=[dict(seed=s,fault=f,baseline_run=p['baseline']['run_id'],recovery_run=p['recovery']['run_id'],baseline_success=p['baseline']['success'],recovery_success=p['recovery']['success'],delta_sim_s=p['recovery']['metrics']['sim_duration_s']-p['baseline']['metrics']['sim_duration_s']) for (s,f),p in sorted(pairs.items())],raw_files=[{'path':str(p.relative_to(directory)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths])
    for policy,v in result['aggregate'].items():
        rates=[r['completion_rate'] for r in by_seed if r['policy']==policy]
        v['completion_rate_seed_std']=statistics.stdev(rates) if len(rates)>1 else 0.
    (directory/'metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    fields=['seed','fault','policy','run_id','status','success','sim_duration_s','wall_duration_s','retries','reason']
    with (directory/'trials.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    lines=['# 동결 조건 비교 평가','',f'원본 {len(rows)}개 실행, {len(pairs)}개 짝. 모든 수치는 result.json에서 생성.','', '| 조건 | 기준 완료 | 복구 완료 | 기준 평균 s | 복구 평균 s |','|---|---:|---:|---:|---:|']
    for fault in sorted({r['fault'] for r in rows}):
        b=summarize(groups[fault,'baseline']);r=summarize(groups[fault,'recovery'])
        lines.append(f"| {fault} | {b['completed']}/{b['n']} | {r['completed']}/{r['n']} | {b['mean_sim_s']:.2f} | {r['mean_sim_s']:.2f} |")
    lines+=['','시간 단위는 simulated seconds. 실패 작업도 실제 종료까지 분모에 포함. 현장 처리량/ROI가 아니다.','복구율 = 첫 시도 작업 미완료 중 재시도 후 최종 완료 / 첫 시도 작업 미완료. 영구 실패와 unknown 주문도 분모에 포함.','first_attempt_pick_success는 첫 시도 압력 유지 상태의 lift 확인이고, first_attempt_success는 첫 시도 최종 배치 완료다.','완료 비율 Wilson 95% 구간은 이 합성 조건 표본의 불확실성 설명이며 실물 일반화 근거가 아니다.']
    (directory/'summary.md').write_text('\n'.join(lines)+'\n')
    return result


def evaluate(directory,seeds=FINAL_SEEDS,faults=FAULTS):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if list(directory.glob('*/result.json')):raise ValueError('Evaluation output must be empty to prevent silent case selection')
    manifest=dict(schema_version=1,frozen_at=datetime.now(timezone.utc).isoformat(),seeds=list(seeds),faults=list(faults),policies=['baseline','recovery'],success_criterion='visual SKU in bin twice, released pressure, independent truth correct SKU settled in bin',max_attempts={'baseline':1,'recovery':3},sim_deadline_s=60,wall_deadline_s=90,stop_time_included=True,development_seeds='0..99',provenance=source_provenance(ROOT),platform=platform.platform(),record_frames=False)
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2))
    for seed in seeds:
        for fault in faults:
            # Alternate order by seed to avoid always warming the model for one policy.
            for policy in (('baseline','recovery') if seed%2==0 else ('recovery','baseline')):
                r=run_job(seed=seed,fault=fault,policy=policy,out_dir=directory,record=False)
                print(f"{seed} {fault:20s} {policy:8s} {r['status']:9s} {r['reason'] or '-'}",flush=True)
    result=aggregate(directory)
    return result
