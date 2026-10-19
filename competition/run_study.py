"""Pre-specified complete factorial ablation with resumable independent processes."""
from pathlib import Path
import argparse, concurrent.futures, csv, hashlib, json, os, platform, sys, time
import numpy as np
import kernel as K
from run_experiments import METHODS, solve, load_vessels
from scheduling_objectives import validate_parameters

def job(data):
    vessels,method,seed,budget,pop,qcs=data
    K.PortConfig.TOTAL_QCS=qcs
    K.PortConfig.OBJECTIVE_PARAMETERS=validate_parameters()
    result=solve(vessels,method,seed,budget,pop,K.calculate_objectives)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--csv',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--budget',type=int,default=12000);p.add_argument('--population',type=int,default=40)
    p.add_argument('--seeds',type=int,default=20);p.add_argument('--seed-start',type=int,default=42)
    p.add_argument('--workers',type=int,default=4);p.add_argument('--qcs',type=int,default=15)
    p.add_argument('--methods',nargs='+',choices=METHODS,default=METHODS);a=p.parse_args()
    assert a.budget>=2*a.population+2 and a.population>=4 and a.qcs>=3
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'runs').mkdir(exist_ok=True)
    vessels=load_vessels(a.csv)
    manifest={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}
    manifest.update(dataSha256=hashlib.sha256(a.csv.read_bytes()).hexdigest(),shipCount=len(vessels),
        objectiveOrder=['carbon','stay','cost'],accounting=validate_parameters(),python=platform.python_version(),
        numpy=np.__version__,platform=platform.platform(),processor=platform.processor(),cpuCount=os.cpu_count(),
        timingNote='Four worker processes share the host; time is descriptive, not a standalone speed ranking.',
        resource={'berths':10,'qcs':a.qcs,'maxQcs':3,'efficiency':48,'waitingCost':1,'operatingCost':3},
        budgetDefinition='All objective calls, including repaired candidates and 2 common scale anchors. FCFS deterministic once.',
        sourceHashes={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ['kernel.py','scheduling_objectives.py','run_experiments.py','run_study.py']})
    meta=a.out/'metadata.json'
    if meta.exists():assert json.loads(meta.read_text(encoding='utf-8'))==manifest,'Study changed: use a new directory'
    else:meta.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    jobs=[]
    for m in a.methods:
        for seed in ([a.seed_start] if m=='FCFS' else range(a.seed_start,a.seed_start+a.seeds)):
            if not (a.out/'runs'/f'{m}_{seed}.json').exists():jobs.append((vessels,m,seed,a.budget,a.population,a.qcs))
    print(f'Start {len(jobs)} jobs with {a.workers} workers',flush=True)
    with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(job,j) for j in jobs]):
            r=future.result();(a.out/'runs'/f'{r["method"]}_{r["seed"]}.json').write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8')
            print(f'{r["method"]} seed={r["seed"]} eval={r["evaluations"]} front={len(r["front"])} sec={r["seconds"]:.2f}',flush=True)
    records=[json.loads(f.read_text(encoding='utf-8')) for f in (a.out/'runs').glob('*.json')]
    records.sort(key=lambda r:(a.methods.index(r['method']),r['seed']))
    (a.out/'runs.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
    with (a.out/'solutions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['method','seed','solution','carbon','stay','cost'])
        for r in records:
            for i,v in enumerate(r['front']):w.writerow([r['method'],r['seed'],i,*v])
    print('STUDY COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
