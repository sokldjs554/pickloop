"""Preregistered four-policy ablation with immutable, policy-independent conditions."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .engine import run_job, FAULTS, POLICIES
from .evaluation import summarize
from .journal import source_provenance
from .simulation import ROOT

POLICY_SPEC = {
    'baseline': {'max_attempts': 1, 'target': 'fresh', 'retry_clearance_m': .30},
    'naive': {'max_attempts': 3, 'target': 'reuse last valid grasp target; reacquire only if never acquired', 'retry_clearance_m': .30},
    'reobserve': {'max_attempts': 3, 'target': 'fresh every attempt', 'retry_clearance_m': .30},
    'recovery': {'max_attempts': 3, 'target': 'fresh every attempt', 'retry_clearance_m': .40},
}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def fingerprint(provenance):
    return (provenance['source_sha256'],provenance['model_sha256'])

def paired_rows(rows, policies=POLICIES):
    pairs=defaultdict(dict)
    for row in rows:
        key=(row['seed'],row['fault'])
        if row['policy'] in pairs[key]:raise ValueError('DUPLICATE_PAIR')
        pairs[key][row['policy']]=row
    for key,pair in pairs.items():
        if set(pair)!=set(policies):raise ValueError(f'INCOMPLETE_PAIR:{key}')
        first=pair[policies[0]]
        for row in pair.values():
            if row['initial_truth']!=first['initial_truth']:raise ValueError('INITIAL_STATE_MISMATCH')
            if row['condition']!=first['condition']:raise ValueError('CONDITION_MISMATCH')
            if fingerprint(row['provenance'])!=fingerprint(first['provenance']):raise ValueError('SOURCE_OR_MODEL_MISMATCH')
    return pairs

def contrast(pairs, before, after):
    differences=defaultdict(list);wins=losses=ties=0
    for (seed,fault),p in pairs.items():
        d=int(p[after]['success'])-int(p[before]['success'])
        differences[seed].append(d)
        wins+=d>0;losses+=d<0;ties+=d==0
    # Conditions sharing a seed are clustered, not counted as independent seed replicates.
    clusters=np.array([np.mean(v) for _,v in sorted(differences.items())])
    rng=np.random.default_rng(81419)
    boot=clusters[rng.integers(0,len(clusters),(10000,len(clusters)))].mean(axis=1)
    return dict(before=before,after=after,n_pairs=wins+losses+ties,after_only=wins,before_only=losses,tied=ties,
                completion_delta=float(clusters.mean()),seed_cluster_bootstrap95=np.quantile(boot,[.025,.975]).tolist(),
                seed_clusters=len(clusters),bootstrap_replicates=10000)

def aggregate_experiment(directory):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    paths=sorted(directory.glob('*/result.json'));rows=[json.loads(p.read_text()) for p in paths]
    pairs=paired_rows(rows)
    expected={(c['seed'],c['fault']):c for c in manifest['cases']}
    if set(pairs)!=set(expected):raise ValueError('CASE_SET_MISMATCH')
    for key,p in pairs.items():
        for row in p.values():
            if row['condition']!=expected[key]['condition']:raise ValueError('FROZEN_CONDITION_MISMATCH')
            if fingerprint(row['provenance'])!=fingerprint(manifest['provenance']):raise ValueError('FROZEN_SOURCE_OR_MODEL_MISMATCH')
    groups=defaultdict(list)
    for r in rows:groups[r['fault'],r['policy']].append(r)
    seeds=sorted({r['seed'] for r in rows})
    by_seed=[dict(seed=s,policy=p,**summarize([r for r in rows if r['seed']==s and r['policy']==p])) for s in seeds for p in POLICIES]
    pair_entries=[]
    for (s,f),p in sorted(pairs.items()):
        entry=dict(seed=s,fault=f,condition_id=p['baseline'].get('condition_id'))
        for policy,row in p.items():entry.update({policy+'_run':row['run_id'],policy+'_success':row['success']})
        pair_entries.append(entry)
    metrics=dict(schema_version=2,experiment='heldout-four-policy-ablation',split=manifest['split'],generated_at=datetime.now(timezone.utc).isoformat(),
        protocol=manifest,aggregate={p:summarize([r for r in rows if r['policy']==p]) for p in POLICIES},
        conditions=[dict(fault=f,policy=p,**summarize(rs)) for (f,p),rs in sorted(groups.items())],seeds=by_seed,pairs=pair_entries,
        contrasts=[contrast(pairs,a,b) for a,b in [('naive','recovery'),('naive','reobserve'),('reobserve','recovery')]],
        raw_files=[dict(path=str(p.relative_to(directory)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])
    for p,m in metrics['aggregate'].items():
        rates=np.array([s['completion_rate'] for s in by_seed if s['policy']==p])
        m['completion_rate_seed_std']=float(np.std(rates,ddof=1)) if len(seeds)>1 else 0.
        rng=np.random.default_rng(81419)
        m['completion_seed_cluster95']=np.quantile(rates[rng.integers(0,len(rates),(10000,len(rates)))].mean(axis=1),[.025,.975]).tolist()
        m.pop('completion_wilson95',None)
    for entry in metrics['conditions']+metrics['seeds']:entry.pop('completion_wilson95',None)
    (directory/'metrics.json').write_text(json.dumps(metrics,indent=2,ensure_ascii=False))
    with (directory/'trials.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,['seed','fault','policy','condition_id','run_id','status','success','sim_duration_s','wall_duration_s','retries','reason'],extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    lines=['# 같은 예산의 복구 정책 분해 실험','',f"{len(seeds)} seeds × {len(manifest['faults'])} conditions × 4 policies = {len(rows)} runs. Split: {manifest['split']}.",'',
        '| 정책 | 완료 | 완료율 | 평균 시뮬레이션 s | 재시도 | 낙하 | 충돌 |','|---|---:|---:|---:|---:|---:|---:|']
    for p,m in metrics['aggregate'].items():lines.append(f"| {p} | {m['completed']}/{m['n']} | {m['completion_rate']:.1%} | {m['mean_sim_s']:.2f} | {m['retries']} | {m['drops']} | {m['collisions']} |")
    lines+=['','동일 조건·초기 물리 상태, 최대 3회 / 시뮬레이션 60초 / wall 90초. baseline만 1회이며 인과적 우위의 주 비교에 사용하지 않는다.',
        'naive는 마지막 유효 파지 좌표와 원래 경로를 반복한다. 최초 목표를 얻지 못한 경우에는 관측을 재시도한다. 신선도·압력·충돌 안전 검사는 모든 정책에서 유지한다.',
        'reobserve는 매번 RGB-D로 목표를 다시 계산한다. recovery는 여기에 재시도 운반/복귀 높이 0.40m를 추가한다. 해당 정책 묶음에 대한 절제 실험이며 보편적 최적 정책 주장이 아니다.',
        '난수는 seed와 절대 시뮬레이션 시각으로 결정된다. 시도 번호나 정책 이름으로 장애가 해제되지 않는다. 정책이 다른 시각에 센서를 읽는 효과는 실제 정책-환경 상호작용에 포함된다.',
        '시간 초과는 다음 물리 스텝/상태 검사에서 감지하며 안전 감속·정지·밸브 확인은 예산 이후에도 끝까지 수행하고 총 시간에 포함한다.',
        '완료율 차이의 구간은 seed 단위 군집 부트스트랩 10,000회다. 합성 표본이 작고 조건 구성이 임의이므로 현장 일반화나 생산 처리량으로 해석할 수 없다.','',
        '| 비교 | 완료율 차이 | seed 군집 95% 구간 | 후 정책만 성공 | 전 정책만 성공 |','|---|---:|---:|---:|---:|']
    for c in metrics['contrasts']:lines.append(f"| {c['before']} → {c['after']} | {c['completion_delta']:+.1%}p | {c['seed_cluster_bootstrap95'][0]:+.1%} ~ {c['seed_cluster_bootstrap95'][1]:+.1%} | {c['after_only']} | {c['before_only']} |")
    (directory/'summary.md').write_text('\n'.join(lines)+'\n')
    return metrics

def evaluate_experiment(directory,seeds,split='heldout',faults=FAULTS):
    from .conditions import make_condition
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if any(directory.iterdir()):raise ValueError('Experiment directory must be empty; never overwrite or resume a partial batch silently')
    cases=[dict(seed=s,fault=f,condition=make_condition(s,f,split)) for s in seeds for f in faults]
    manifest=dict(schema_version=2,frozen_at=datetime.now(timezone.utc).isoformat(),split=split,seeds=list(seeds),faults=list(faults),
        policies=POLICY_SPEC,cases=cases,cases_sha256=digest(cases),sim_deadline_s=60,wall_deadline_s=90,
        stop_time_included=True,record_frames=False,development_seeds='200..209',heldout_seeds='3000..3011',
        success_criterion='visual registered SKU settled in bin twice, released vacuum, independent physical truth correct SKU and no wrong placements',
        provenance=source_provenance(ROOT),claim_scope='synthetic frozen-condition ablation; not hardware validation',
        no_holdout_tuning=True)
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2))
    for i,case in enumerate(cases):
        rotation=(i//len(faults)+i%len(faults))%len(POLICIES)
        order=POLICIES[rotation:]+POLICIES[:rotation]
        for p in order:
            if fingerprint(source_provenance(ROOT))!=fingerprint(manifest['provenance']):raise RuntimeError('Source or model changed during frozen experiment')
            r=run_job(seed=case['seed'],fault=case['fault'],condition=case['condition'],policy=p,out_dir=directory,record=False)
            print(f"{case['seed']} {case['fault']:20} {p:10} {r['status']:10} {r['reason'] or '-'}",flush=True)
    return aggregate_experiment(directory)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);parser.add_argument('--split',choices=['development','heldout'],default='heldout');parser.add_argument('--seeds',type=int,nargs='+',default=list(range(3000,3012)));parser.add_argument('--faults',nargs='+',default=list(FAULTS));parser.add_argument('--aggregate',action='store_true');args=parser.parse_args()
    result=aggregate_experiment(args.out) if args.aggregate else evaluate_experiment(args.out,args.seeds,args.split,args.faults)
    print(json.dumps(result['aggregate'],indent=2))
