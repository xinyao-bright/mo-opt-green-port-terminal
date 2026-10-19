"""Reproducible BACAP baselines, ablations and parameter sensitivity.

Example: python run_experiments.py --csv "ship_data(S1).csv" --budget 12000 --seeds 20
Only one objective model is compared within a run. Legacy objectives can be
selected separately; legacy/new absolute objective values must not be pooled.
"""
from pathlib import Path
import argparse
import ast
import csv
import hashlib
import json
import platform
import re
import time
import numpy as np
import pandas as pd
import kernel as K
from scheduling_objectives import validate_parameters

METHODS = ['NSGA2-Repair', 'NSGA2-NoRepair', 'NSGA2-NoAnchor', 'NSGA2-None', 'WeightedGA', 'RandomSearch', 'FCFS']


def load_vessels(path):
    try:
        df = pd.read_csv(path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding='gbk')
    df.columns = df.columns.str.strip()
    df = df.fillna('')
    def col(pattern, fallback=None):
        return next((c for c in df.columns if re.search(pattern, c, re.I)), fallback)
    name = col('id|name', df.columns[0]); eta = col('time|reachport')
    volume = col('volume|teu'); length = col('length|长')
    def number(row, key, default):
        try: return float(row[key]) if key is not None and row[key] != '' else default
        except (ValueError, TypeError): return default
    rows = []
    for i, r in df.iterrows():
        raw = str(r[eta]).strip(); match = re.search(r'(\d{1,2})\s*:\s*(\d{1,2})', raw)
        arrival = (int(match[1])*60 + int(match[2]))/60 if match else max(0, float(raw or 0))
        fuel = number(r, col('auxfuelcons'), 220)
        fuel = fuel/1000 if fuel > 10 else fuel
        power, load = number(r, col('auxratedpow'), 520), number(r, col('auxlf'), .55)
        if power < 1 and load > 1: power, load = load, power
        rows.append(dict(id=i+1, name=str(r[name]), eta=arrival,
                         workload=number(r, volume, 0), len=number(r, length, 0),
                         auv1=fuel, auv2=power, auv3=load))
    if not rows or any(v['workload'] <= 0 or not all(np.isfinite(v[k]) for k in ('eta','workload','auv1','auv2','auv3')) for v in rows):
        raise ValueError('实验数据必须非空，货量为正，数值有限')
    return rows


def initial_population(vessels, size, rng, anchors=True):
    n=len(vessels); p=np.zeros((size, 4*n)); eta=np.array([v['eta'] for v in vessels])
    for i in range(size):
        p[i,:n]=rng.uniform(1,K.PortConfig.TOTAL_BERTHS,n)
        p[i,n:2*n]=eta+rng.uniform(0,2,n)
        p[i,2*n:3*n]=rng.uniform(1,K.PortConfig.MAX_QC_PER_VESSEL,n)
        order=np.argsort(p[i,:n],kind='stable'); p[i,3*n+order]=np.linspace(1,K.PortConfig.TOTAL_QCS,n)
    if anchors:
        for i,q in enumerate((K.PortConfig.MAX_QC_PER_VESSEL,1)):
            if i>=size: break
            b=np.arange(n)%min(K.PortConfig.TOTAL_BERTHS,K.PortConfig.TOTAL_QCS//q)
            p[i]=np.concatenate([b,eta,np.full(n,q),b*q+1])
    return p


def ranks_and_crowding(objs, penalties):
    fronts=K.fast_non_dominated_sort_cdp(objs,penalties)
    ranks=np.zeros(len(objs),int); crowd=np.zeros(len(objs))
    for r,front in enumerate(fronts):
        ranks[front]=r; crowd[front]=K.crowding_distance(objs,front)
    return ranks,crowd,fronts


def front_indices(objs, penalties):
    indices=np.where(penalties==0)[0]
    if not len(indices): return np.array([],int)
    f=K.fast_non_dominated_sort_cdp(objs[indices],np.zeros(len(indices)))[0]
    selected=indices[f]
    _,unique=np.unique(np.round(objs[selected],8),axis=0,return_index=True)
    return selected[unique]


class Evaluator:
    def __init__(self,vessels,budget,objective):
        self.vessels=vessels; self.budget=budget; self.count=0
        self.feasible=0; self.repair_calls=0; self.repair_success=0; self.repair_seconds=0
        self.evaluate=objective
    def one(self,p):
        if self.count>=self.budget: return None
        obj,pen=self.evaluate(p,self.vessels)
        self.count+=1; self.feasible+=int(pen==0)
        return obj,pen
    def repair(self,p):
        if self.count>=self.budget: return None
        t=time.perf_counter(); r,_=K.repair_qc_conflict(p,self.vessels)
        self.repair_seconds+=time.perf_counter()-t; self.repair_calls+=1
        result=self.one(r); self.repair_success+=int(result[1]==0)
        return r,result[0],result[1]


def solve(vessels,method,seed,budget,pop_size,objective):
    rng=np.random.default_rng(seed); start=time.perf_counter(); ev=Evaluator(vessels,budget,objective)
    p=initial_population(vessels,pop_size,rng,anchors=method not in ('NSGA2-NoAnchor','NSGA2-None'))
    if method=='FCFS':
        # Deterministic arrival order; every vessel at berth 1, identical max-QC segment.
        # It is deliberately a simple operational baseline, not an exact solver.
        n=len(vessels); p=p[:1];p[0,:n]=0;p[0,2*n:3*n]=K.PortConfig.MAX_QC_PER_VESSEL;p[0,3*n:]=1
    values=[ev.one(x) for x in p]; o=np.array([x[0] for x in values]); penalties=np.array([x[1] for x in values])
    repair=method in ('NSGA2-Repair','NSGA2-NoAnchor','WeightedGA')
    if repair:
        for i in range(len(p)):
            if penalties[i]>0:
                result=ev.repair(p[i])
                if result is not None: p[i],o[i],penalties[i]=result
    trace=[]; generation=0
    # Fixed scales from common data-derived anchors, shared across seeds/methods.
    anchors=initial_population(vessels,2,np.random.default_rng(0),True)
    # These diagnostic evaluations count against the budget as well.
    scale_values=[]
    for x in anchors:
        result=ev.one(x)
        if result is not None: scale_values.append(result[0])
    scales=np.maximum(np.max(scale_values,axis=0),1) if scale_values else np.maximum(o.max(axis=0),1)
    def order_for(objs,pens):
        if method=='WeightedGA':
            scalar=(objs/scales*np.array([.4,.3,.3])).sum(axis=1)
            return sorted(range(len(objs)),key=lambda i:(pens[i]>0,pens[i] if pens[i]>0 else scalar[i]))
        ranks,crowd,_=ranks_and_crowding(objs,pens)
        return sorted(range(len(objs)),key=lambda i:(ranks[i],-crowd[i]))
    def record():
        f=front_indices(o,penalties)
        trace.append({'evaluations':ev.count,'generation':generation,'feasiblePopulation':float(np.mean(penalties==0)),
                      'front':o[f].tolist()})
    record()
    while ev.count<budget and method!='FCFS':
        order=order_for(o,penalties); priority={idx:rank for rank,idx in enumerate(order)}
        def tournament():
            a,b=rng.choice(len(p),2,replace=False); return p[a if priority[a]<priority[b] else b]
        children=[]
        while len(children)<pop_size:
            if method=='RandomSearch':
                children.append(initial_population(vessels,1,rng,False)[0]);continue
            a,b=tournament(),tournament(); c,d=a.copy(),b.copy()
            if rng.random()<.7:
                alpha=rng.random(len(a));c=alpha*a+(1-alpha)*b;d=alpha*b+(1-alpha)*a
            for child in (c,d):
                for j in range(len(child)):
                    if rng.random()<1/len(child):
                        if j<len(vessels):
                            child[j]=rng.uniform(1,K.PortConfig.TOTAL_BERTHS) if rng.random()<.3 else child[j]+rng.normal(0,5)
                        else: child[j]+=rng.normal(0,2)
                children.append(child)
                if len(children)>=pop_size:break
        child_values=[]; evaluated=[]
        for child in children:
            result=ev.one(child)
            if result is None:break
            evaluated.append(child);child_values.append(result)
        if not evaluated:break
        cp=np.vstack([p,evaluated]);co=np.vstack([o,[x[0] for x in child_values]]);cv=np.r_[penalties,[x[1] for x in child_values]]
        if repair:
            ranks,_,_=ranks_and_crowding(co,cv)
            candidates=sorted(np.where(cv>0)[0],key=lambda i:ranks[i])[:30]
            for i in candidates:
                result=ev.repair(cp[i])
                if result is None:break
                cp[i],co[i],cv[i]=result
        keep=order_for(co,cv)[:pop_size];p,o,penalties=cp[keep],co[keep],cv[keep]
        generation+=1;record()
    f=front_indices(o,penalties)
    return {'method':method,'seed':seed,'seconds':time.perf_counter()-start,'evaluations':ev.count,
            'feasibleEvaluationRate':ev.feasible/ev.count,'repairCalls':ev.repair_calls,
            'repairSuccessRate':ev.repair_success/ev.repair_calls if ev.repair_calls else None,
            'repairSeconds':ev.repair_seconds,'front':o[f].tolist(),'positions':p[f].tolist(),'trace':trace}


def legacy_objective():
    # Load only the baseline objective function, not the Flask application.
    text=(Path(__file__).parent/'baseline/app_before_objective_v2.py').read_text(encoding='utf-8')
    tree=ast.parse(text);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='calculate_objectives')
    env=dict(np=np,PortConfig=K.PortConfig,decode_solution=K.decode_solution,calculate_penalty=K.calculate_penalty)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<legacy objective>','exec'),env)
    return env['calculate_objectives']


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv',required=True,type=Path);ap.add_argument('--out',type=Path,default=Path('results'))
    ap.add_argument('--budget',type=int,default=12000);ap.add_argument('--population',type=int,default=60)
    ap.add_argument('--seeds',type=int,default=20);ap.add_argument('--seed-start',type=int,default=42)
    ap.add_argument('--methods',nargs='+',choices=METHODS,default=METHODS)
    ap.add_argument('--objective',choices=['v2','legacy'],default='v2')
    ap.add_argument('--grid-factor',type=float,default=.5306);ap.add_argument('--coordination-cost',type=float,default=20)
    ap.add_argument('--electricity-price',type=float,default=.8);ap.add_argument('--service-aux-ratio',type=float,default=1)
    ap.add_argument('--berths',type=int,default=10);ap.add_argument('--qcs',type=int,default=15)
    ap.add_argument('--max-qcs',type=int,default=3)
    args=ap.parse_args()
    if args.population<4 or args.budget<2*args.population+2 or args.seeds<1:ap.error('population >=4; budget >=2*population+2; seeds >=1')
    if min(args.berths,args.qcs,args.max_qcs)<1 or args.max_qcs>args.qcs:ap.error('invalid resource counts')
    K.PortConfig.TOTAL_BERTHS=args.berths;K.PortConfig.TOTAL_QCS=args.qcs;K.PortConfig.MAX_QC_PER_VESSEL=args.max_qcs
    K.PortConfig.OBJECTIVE_PARAMETERS=validate_parameters(dict(gridEmissionFactor=args.grid_factor,
        electricityPrice=args.electricity_price,qcCoordinationCost=args.coordination_cost,serviceAuxRatio=args.service_aux_ratio))
    objective=K.calculate_objectives if args.objective=='v2' else legacy_objective()
    vessels=load_vessels(args.csv);args.out.mkdir(parents=True,exist_ok=True)
    if (args.out/'runs.json').exists():ap.error('输出目录已有 runs.json，请使用新的 --out 避免混合实验')
    meta={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
    meta.update(dataSha256=hashlib.sha256(args.csv.read_bytes()).hexdigest(),python=platform.python_version(),
        numpy=np.__version__,platform=platform.platform(),shipCount=len(vessels),
        accounting=K.PortConfig.OBJECTIVE_PARAMETERS,objectiveOrder=['carbon','stay','cost'],
        budgetDefinition='Every objective call including repaired/anchor candidates; repair-only work also timed.',
        referenceSet='Empirical nondominated union of final feasible fronts within this run, not a true Pareto front.')
    (args.out/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    runs=[]
    for method in args.methods:
        seeds=[args.seed_start] if method=='FCFS' else range(args.seed_start,args.seed_start+args.seeds)
        for seed in seeds:
            r=solve(vessels,method,seed,args.budget,args.population,objective);runs.append(r)
            print(f'{method} seed={seed} nfe={r["evaluations"]} front={len(r["front"])} seconds={r["seconds"]:.2f}',flush=True)
            (args.out/'runs.json').write_text(json.dumps(runs,ensure_ascii=False,indent=2),encoding='utf-8')
    with (args.out/'solutions.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['method','seed','solution','carbon','stay','cost'])
        for r in runs:
            for i,obj in enumerate(r['front']):writer.writerow([r['method'],r['seed'],i,*obj])
    print('Complete. Next: python plot_results.py --results',args.out)


if __name__=='__main__':main()
