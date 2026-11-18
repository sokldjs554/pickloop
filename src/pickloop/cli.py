import argparse
import json
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(prog='pickloop')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run');run.add_argument('--seed',type=int,default=7);run.add_argument('--fault',default='normal');run.add_argument('--policy',choices=['baseline','naive','reobserve','recovery'],default='recovery');run.add_argument('--out',default='runs/local');run.add_argument('--no-record',action='store_true');run.add_argument('--job-id');run.add_argument('--condition-file')
    ev=sub.add_parser('evaluate');ev.add_argument('--out',default='runs/final');ev.add_argument('--seeds',nargs='+',type=int,default=list(range(1000,1005)))
    agg=sub.add_parser('aggregate');agg.add_argument('directory')
    server=sub.add_parser('serve');server.add_argument('--host',default='127.0.0.1');server.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if args.command=='run':
        from .engine import run_job
        print(json.dumps(run_job(seed=args.seed,fault=args.fault,policy=args.policy,out_dir=args.out,record=not args.no_record,job_id=args.job_id,condition=json.loads(Path(args.condition_file).read_text()) if args.condition_file else None),indent=2,ensure_ascii=False))
    elif args.command=='evaluate':
        from .evaluation import evaluate
        print(json.dumps(evaluate(args.out,args.seeds)['aggregate'],indent=2))
    elif args.command=='aggregate':
        from .evaluation import aggregate
        print(json.dumps(aggregate(args.directory)['aggregate'],indent=2))
    else:
        import uvicorn
        uvicorn.run('pickloop.server:app',host=args.host,port=args.port)

if __name__=='__main__':main()
