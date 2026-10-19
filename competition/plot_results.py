"""Publication-ready figures from actual runs; never supplies invented outcomes."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS=['#147D92','#D99B45','#6875A8','#A66885','#617886','#91A58E','#B0B8BD']


def nondominated(a):
    a=np.unique(np.asarray(a,float),axis=0)
    return a[[not np.any(np.all(a<=p,axis=1)&np.any(a<p,axis=1)) for p in a]]


def hypervolume(points,reference):
    """Exact union of minimization boxes, recursive axis slicing (3 objectives)."""
    reference=np.asarray(reference,float);p=np.asarray(points,float)
    if p.size==0:return 0.0
    p=p[np.all(p<reference,axis=1)]
    if not len(p):return 0.0
    if len(reference)==1:return max(0.0,float(reference[0]-p[:,0].min()))
    xs=np.unique(p[:,0]);volume=0.0
    for i,x in enumerate(xs):
        right=xs[i+1] if i+1<len(xs) else reference[0]
        volume+=(right-x)*hypervolume(p[p[:,0]<=x,1:],reference[1:])
    return float(volume)


def igd(front,reference):
    if len(front)==0:return float('nan')
    return float(np.sqrt(((reference[:,None,:]-front[None,:,:])**2).sum(axis=2)).min(axis=1).mean())


def create_plots(folder):
    folder=Path(folder);runs=json.loads((folder/'runs.json').read_text(encoding='utf-8'))
    meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    valid=[np.array(r['front']) for r in runs if r['front']]
    if not valid:raise ValueError('所有实验均无可行解，不绘制伪造的 Pareto 或 IGD 结果')
    all_points=np.vstack(valid);low=all_points.min(axis=0);span=np.ptp(all_points,axis=0);span[span<1e-12]=1
    norm=lambda a:(np.asarray(a).reshape(-1,3)-low)/span
    reference=nondominated(norm(all_points));hv_ref=np.full(3,1.1)
    methods=list(dict.fromkeys(r['method'] for r in runs));color=dict(zip(methods,COLORS))
    out=folder/'figures';out.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.labelcolor':'#243D4D','xtick.color':'#526773','ytick.color':'#526773',
                         'axes.edgecolor':'#C9D4D9','axes.grid':True,'grid.color':'#E6ECEF','grid.alpha':.75,
                         'figure.facecolor':'white','savefig.facecolor':'white','svg.fonttype':'none',
                         'pdf.fonttype':42,'axes.titleweight':'bold','axes.titlepad':13})
    def save(fig,name):
        fig.tight_layout()
        for ext in ['pdf','svg','png']:fig.savefig(out/(name+'.'+ext),dpi=300,bbox_inches='tight')
        plt.close(fig)
    rows=[]
    for r in runs:
        f=norm(r['front']);rows.append({k:r[k] for k in ['method','seed','seconds','evaluations','feasibleEvaluationRate','repairCalls','repairSuccessRate','repairSeconds']}|
            {'HV':hypervolume(f,hv_ref),'IGD_empirical':igd(f,reference),'frontSize':len(f)})
    scores=pd.DataFrame(rows);scores.to_csv(folder/'metrics.csv',index=False,encoding='utf-8-sig')
    (folder/'metric_definition.json').write_text(json.dumps({'lower':low.tolist(),'range':span.tolist(),
        'hvReference':hv_ref.tolist(),'empiricalReference':reference.tolist(),
        'warning':'Reference is an empirical union, not the true Pareto front. Undefined IGD remains NaN. FCFS is a single deterministic baseline.'},indent=2),encoding='utf-8')
    labels=['Carbon emissions / kg CO$_2$','Total port stay / vessel h','Modeled cost / CNY']
    fig,axes=plt.subplots(1,3,figsize=(15,4.2))
    for ax,(a,b) in zip(axes,[(0,1),(0,2),(1,2)]):
        for method in methods:
            pts=[np.array(r['front']) for r in runs if r['method']==method and r['front']]
            if pts:
                pts=np.vstack(pts);ax.scatter(pts[:,a],pts[:,b],s=22,alpha=.7,color=color[method],label=method,edgecolors='white',linewidths=.3)
        ax.set(xlabel=labels[a],ylabel=labels[b]);ax.ticklabel_format(style='sci',scilimits=(-3,4),axis='both')
    axes[0].legend(fontsize=8,frameon=False);save(fig,'01_pareto_projections')
    fig,axes=plt.subplots(1,2,figsize=(13,4.6))
    for ax,metric,title in [(axes[0],'HV','Hypervolume  |  higher is better'),(axes[1],'IGD_empirical','Empirical IGD  |  lower is better')]:
        data=[scores.loc[scores.method==m,metric].dropna().to_numpy() for m in methods]
        boxes=ax.boxplot(data,patch_artist=True,tick_labels=methods,showmeans=True,medianprops={'color':'#243D4D'})
        for patch,c in zip(boxes['boxes'],COLORS):patch.set_facecolor(c);patch.set_alpha(.65)
        ax.set_title(title);ax.tick_params(axis='x',rotation=25)
    save(fig,'02_quality_distribution')
    fig,axes=plt.subplots(1,2,figsize=(13,4.5))
    summary=scores.groupby('method').mean(numeric_only=True).reindex(methods)
    axes[0].bar(methods,summary.seconds,color=[color[m] for m in methods]);axes[0].set_ylabel('Wall-clock time / s')
    axes[1].bar(methods,summary.feasibleEvaluationRate,color=[color[m] for m in methods]);axes[1].set_ylabel('Feasible objective evaluations / all evaluations');axes[1].set_ylim(0,1)
    for ax in axes:ax.tick_params(axis='x',rotation=25)
    save(fig,'03_time_and_feasibility')
    fig,ax=plt.subplots(figsize=(8.5,4.8))
    for method in methods:
        selected=[r for r in runs if r['method']==method]
        if method=='FCFS':continue
        grid=np.linspace(max(r['trace'][0]['evaluations'] for r in selected),meta['budget'],80)
        trajectories=[]
        for r in selected:
            xs=np.array([t['evaluations'] for t in r['trace']]);ys=np.array([hypervolume(norm(t['front']),hv_ref) for t in r['trace']])
            trajectories.append(ys[np.maximum(0,np.searchsorted(xs,grid,side='right')-1)])
        tr=np.array(trajectories);ax.plot(grid,np.median(tr,axis=0),label=method,color=color[method],lw=2)
        ax.fill_between(grid,np.percentile(tr,25,axis=0),np.percentile(tr,75,axis=0),color=color[method],alpha=.12)
    ax.set(xlabel='Objective evaluations including repair',ylabel='Hypervolume',title='Convergence with equal evaluation budgets');ax.legend(frameon=False,fontsize=8)
    save(fig,'04_convergence')
    repair=scores[scores.repairCalls>0]
    if not repair.empty:
        means=repair.groupby('method')[['repairSuccessRate','repairSeconds']].mean()
        fig,axes=plt.subplots(1,2,figsize=(10,4))
        for ax,column,label in [(axes[0],'repairSuccessRate','Feasible after repair / repair calls'),(axes[1],'repairSeconds','Time inside repair / s')]:
            ax.bar(means.index,means[column],color=[color[m] for m in means.index]);ax.set_ylabel(label);ax.tick_params(axis='x',rotation=20)
        save(fig,'05_repair_ablation')
    # Paired bootstrap of HV differences. No unpaired FCFS pseudo-repetitions.
    stats=[];base=scores[scores.method=='NSGA2-Repair'][['seed','HV']]
    for method in methods:
        if method in ('NSGA2-Repair','FCFS'):continue
        pair=base.merge(scores[scores.method==method][['seed','HV']],on='seed',suffixes=('_proposed','_baseline'))
        diff=(pair.HV_proposed-pair.HV_baseline).to_numpy()
        if len(diff)<5:stats.append({'baseline':method,'n':len(diff),'note':'At least 5 paired seeds required; recommend >=20.'});continue
        rng=np.random.default_rng(2026);means=rng.choice(diff,(10000,len(diff)),replace=True).mean(axis=1)
        stats.append({'baseline':method,'n':len(diff),'meanHVdifference':float(diff.mean()),'bootstrap95CI':np.quantile(means,[.025,.975]).tolist()})
    (folder/'paired_statistics.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print('Saved figures and metrics to',folder)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--results',required=True,type=Path);create_plots(ap.parse_args().results)
