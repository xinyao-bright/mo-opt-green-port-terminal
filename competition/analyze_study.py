"""Analyze all recorded runs, retain failures, and make Chinese report figures."""
from pathlib import Path
import argparse,json,math,csv
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties,fontManager
from plot_results import nondominated,igd,hypervolume

LABELS={'NSGA2-Repair':'完整方法','NSGA2-NoRepair':'去修复','NSGA2-NoAnchor':'去锚点','NSGA2-None':'双重消融','WeightedGA':'加权GA','RandomSearch':'随机搜索','FCFS':'串行FCFS'}
COLORS={'NSGA2-Repair':'#147D92','NSGA2-NoRepair':'#D99B45','NSGA2-NoAnchor':'#86729E','NSGA2-None':'#627782','WeightedGA':'#A66885','RandomSearch':'#91A58E','FCFS':'#AAB6BE'}
ABL=list(LABELS)[:4]

def hv3(points,ref=np.full(3,1.1)):
    p=np.asarray(points,float).reshape(-1,3);p=p[np.all(p<ref,axis=1)]
    if not len(p):return 0.
    p=p[np.argsort(p[:,0])];xs=np.unique(p[:,0]);value=0.
    for x,right in zip(xs,np.r_[xs[1:],ref[0]]):
        yz=p[p[:,0]<=x,1:];yz=yz[np.argsort(yz[:,0])]
        area=np.sum(np.diff(np.r_[yz[:,0],ref[1]])*(ref[2]-np.minimum.accumulate(yz[:,1])))
        value+=(right-x)*area
    return float(value)

def bootstrap(values,seed=20261019):
    a=np.asarray(values,float);rng=np.random.default_rng(seed)
    samples=rng.choice(a,(10000,len(a)),replace=True).mean(axis=1)
    return [float(a.mean()),*np.quantile(samples,[.025,.975]).tolist()]

def analyze(folder,figures):
    folder=Path(folder);figures=Path(figures);figures.mkdir(parents=True,exist_ok=True)
    runs=json.loads((folder/'runs.json').read_text(encoding='utf-8'));meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    all_points=np.vstack([np.asarray(r['front']) for r in runs if r['front']]);low=all_points.min(axis=0);span=np.ptp(all_points,axis=0);span[span<1e-12]=1
    norm=lambda x:(np.asarray(x,float).reshape(-1,3)-low)/span
    reference=nondominated(norm(all_points));rows=[]
    for r in runs:
        front=norm(r['front']);success=bool(len(front));hits=[t['evaluations'] for t in r['trace'] if t['front']]
        selected=np.asarray(r['front'])[np.argmin(np.sqrt((front**2*np.array([.4,.3,.3])).sum(axis=1)))] if success else [None]*3
        rows.append({k:r[k] for k in ('method','seed','seconds','evaluations','repairCalls','repairSeconds','repairSuccessRate','feasibleEvaluationRate')}|
            {'HV':hv3(front),'IGD':igd(front,reference),'frontSize':len(front),'success':int(success),'firstFeasibleObserved':min(hits) if hits else None,
             'carbon':selected[0],'stay':selected[1],'cost':selected[2]})
    scores=pd.DataFrame(rows);scores.to_csv(folder/'study_metrics.csv',index=False,encoding='utf-8-sig')
    summary={}
    for m,part in scores.groupby('method',sort=False):
        summary[m]={'n':len(part),'successful':int(part.success.sum()),'successRate':float(part.success.mean())}
        for col in ('HV','IGD','frontSize','firstFeasibleObserved','carbon','stay','cost','seconds','repairSuccessRate','repairSeconds','feasibleEvaluationRate'):
            a=part[col].dropna().to_numpy();summary[m][col]={'mean':float(a.mean()) if len(a) else None,'sd':float(a.std(ddof=1)) if len(a)>1 else 0,'median':float(np.median(a)) if len(a) else None}
    by=scores.pivot(index='seed',columns='method',values='HV');effects=[]
    for name,coeffs in [('修复效应｜有锚点',{'NSGA2-Repair':1,'NSGA2-NoRepair':-1}),('锚点效应｜有修复',{'NSGA2-Repair':1,'NSGA2-NoAnchor':-1}),('修复效应｜无锚点',{'NSGA2-NoAnchor':1,'NSGA2-None':-1}),('锚点效应｜无修复',{'NSGA2-NoRepair':1,'NSGA2-None':-1}),('交互效应',{'NSGA2-Repair':1,'NSGA2-NoRepair':-1,'NSGA2-NoAnchor':-1,'NSGA2-None':1})]:
        if not all(k in by for k in coeffs):continue
        difference=sum(by[k]*v for k,v in coeffs.items());difference=difference.dropna().to_numpy()
        mean,lower,upper=bootstrap(difference);effects.append({'name':name,'n':len(difference),'mean':mean,'ci95':[lower,upper],'positive':int((difference>0).sum()),'negative':int((difference<0).sum()),'zero':int((difference==0).sum()),'pairedValues':difference.tolist()})
    (folder/'study_analysis.json').write_text(json.dumps({'metadata':meta,'normalization':{'min':low.tolist(),'range':span.tolist(),'reference':[1.1]*3,'pool':'All final feasible solutions across every method, including FCFS'},'summary':summary,'effects':effects,'referenceSize':len(reference)},ensure_ascii=False,indent=2),encoding='utf-8')
    fonts=Path('C:/Windows/Fonts/msyh.ttc');fontManager.addfont(str(fonts));family=FontProperties(fname=str(fonts)).get_name()
    plt.rcParams.update({'font.family':family,'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,
        'axes.labelcolor':'#17384A','text.color':'#17384A','axes.edgecolor':'#CFDADF','xtick.color':'#526C7B','ytick.color':'#526C7B',
        'grid.color':'#E5ECEF','grid.alpha':.8,'axes.grid':True,'axes.axisbelow':True,'figure.facecolor':'white','savefig.facecolor':'white','pdf.fonttype':42})
    def save(fig,name):
        fig.tight_layout(pad=1.4)
        for ext in ('png','pdf','svg'):fig.savefig(figures/(name+'.'+ext),dpi=260,bbox_inches='tight')
        plt.close(fig)
    methods=[m for m in LABELS if m in summary]
    fig,axes=plt.subplots(1,2,figsize=(11.8,4.5))
    for ax,metric,title in [(axes[0],'HV','解集覆盖质量 HV（越大越好）'),(axes[1],'IGD','经验前沿距离 IGD（越小越好）')]:
        data=[scores.loc[scores.method==m,metric].dropna().to_numpy() for m in methods]
        b=ax.boxplot(data,patch_artist=True,tick_labels=[LABELS[m] for m in methods],showfliers=False,medianprops={'color':'#17384A','linewidth':1.8})
        for patch,m in zip(b['boxes'],methods):patch.set(facecolor=COLORS[m],alpha=.65)
        for i,(a,m) in enumerate(zip(data,methods),1):ax.scatter(i+np.linspace(-.16,.16,len(a)),a,s=12,alpha=.65,color=COLORS[m],zorder=3)
        ax.set_title(title,fontsize=13,pad=15);ax.tick_params(axis='x',rotation=25);ax.grid(axis='x',visible=False)
    save(fig,'exp01_quality')
    fig,axes=plt.subplots(1,2,figsize=(11.8,4.4))
    grid=np.linspace(2*meta['population']+2,meta['budget'],55,dtype=int);curves={}
    for m in ABL:
        selected=[r for r in runs if r['method']==m]
        if not selected:continue
        trajectories=[]
        for r in selected:
            xs=np.array([t['evaluations'] for t in r['trace']]);idx=np.maximum(0,np.searchsorted(xs,grid,side='right')-1)
            cache={i:hv3(norm(r['trace'][i]['front'])) for i in np.unique(idx)};trajectories.append([cache[i] for i in idx])
        tr=np.array(trajectories);med=np.median(tr,axis=0);curves[m]={'evaluations':grid.tolist(),'medianHV':med.tolist()}
        axes[0].plot(grid,med,color=COLORS[m],lw=2,label=LABELS[m]);axes[0].fill_between(grid,np.percentile(tr,25,axis=0),np.percentile(tr,75,axis=0),color=COLORS[m],alpha=.12)
        vals=scores.loc[scores.method==m,'firstFeasibleObserved'].dropna().to_numpy();ys=[np.mean(vals<=x)*len(vals)/len(selected) for x in grid]
        axes[1].step(grid,ys,where='post',color=COLORS[m],lw=2,label=LABELS[m])
    axes[0].set(xlabel='目标评价次数（含修复重评）',ylabel='HV 中位数与四分位区间',title='同预算下的收敛轨迹')
    axes[1].set(xlabel='目标评价次数',ylabel='已观测到可行种群的运行比例',ylim=(-.02,1.05),title='可行解的首次出现');axes[0].legend(frameon=False,fontsize=10);axes[1].legend(frameon=False,fontsize=10)
    save(fig,'exp02_convergence')
    (folder/'study_curves.json').write_text(json.dumps(curves,ensure_ascii=False),encoding='utf-8')
    if effects:
        fig,ax=plt.subplots(figsize=(9.5,4.8));ax.axvline(0,color='#AAB6BE',ls='--',lw=1.2)
        for i,e in enumerate(effects):
            lo,hi=e['ci95'];ax.errorbar(e['mean'],i,xerr=[[e['mean']-lo],[hi-e['mean']]],fmt='o',color=COLORS[ABL[i%4]],capsize=5,ms=7,lw=2)
        ax.set(yticks=range(len(effects)),yticklabels=[e['name'] for e in effects],xlabel='成对 HV 差值：均值与 95% bootstrap 区间',title='2×2 消融：条件效应与交互效应');ax.invert_yaxis();ax.grid(axis='y',visible=False)
        save(fig,'exp03_factorial_effects')
    fig,axes=plt.subplots(1,3,figsize=(13.8,4.2));units=['碳排放 / t CO$_2$','总在港时间 / h','模型成本 / 万元'];scales=[1000,1,10000]
    for ax,(a,b) in zip(axes,[(0,1),(0,2),(1,2)]):
        for m in ABL:
            points=[np.asarray(r['front']) for r in runs if r['method']==m and r['front']]
            if points:
                pts=np.vstack(points);ax.scatter(pts[:,a]/scales[a],pts[:,b]/scales[b],s=14,color=COLORS[m],alpha=.45,label=LABELS[m],edgecolors='none')
        ax.set(xlabel=units[a],ylabel=units[b])
    axes[0].legend(frameon=False,fontsize=9);save(fig,'exp04_pareto')
    fig,axes=plt.subplots(1,3,figsize=(13,4.2))
    for ax,col,lab,scale in zip(axes,['carbon','stay','cost'],units,scales):
        vals=[scores.loc[scores.method==m,col].dropna().to_numpy()/scale for m in methods]
        med=[np.mean(v) if len(v) else np.nan for v in vals];sd=[np.std(v,ddof=1) if len(v)>1 else 0 for v in vals]
        ax.bar(range(len(methods)),med,yerr=sd,color=[COLORS[m] for m in methods],capsize=3,width=.65)
        ax.set(xticks=range(len(methods)),xticklabels=[LABELS[m] for m in methods],ylabel=lab);ax.tick_params(axis='x',rotation=35);ax.grid(axis='x',visible=False)
    save(fig,'exp05_business_metrics')
    if all(m in summary for m in ABL):
        if meta.get('qcs',15)<15:
            fig,axes=plt.subplots(1,2,figsize=(11.5,4.3))
            rates=[summary[m]['successRate'] for m in ABL]
            axes[0].bar(range(4),rates,color=[COLORS[m] for m in ABL],width=.6)
            for i,m in enumerate(ABL):axes[0].text(i,rates[i]+.025,f"{summary[m]['successful']}/{summary[m]['n']}",ha='center',fontsize=12)
            axes[0].set(xticks=range(4),xticklabels=[LABELS[m] for m in ABL],ylim=(0,1.15),ylabel='可行解获取率',title=f"{meta['qcs']} 台岸桥：有限预算下的成功率")
            for i,m in enumerate(ABL):
                values=scores.loc[scores.method==m,'HV'].to_numpy()
                axes[1].scatter(i+np.linspace(-.15,.15,len(values)),values,color=COLORS[m],s=36,alpha=.8)
                axes[1].plot([i-.23,i+.23],[values.mean()]*2,color=COLORS[m],lw=2.5)
            axes[1].set(xticks=range(4),xticklabels=[LABELS[m] for m in ABL],ylim=(-.05,1.33),ylabel='HV（失败运行记 0）',title='全部运行的解集质量')
            for ax in axes:ax.grid(axis='x',visible=False)
            save(fig,'exp07_resource_stress')
        fig,axes=plt.subplots(1,2,figsize=(10.8,4.4))
        for ax,metric,lab in [(axes[0],'HV','HV（越大越好，纵轴局部放大）'),(axes[1],'IGD','IGD（越小越好，纵轴局部放大）')]:
            pair=scores[scores.method=='NSGA2-Repair'][['seed',metric]].merge(scores[scores.method=='NSGA2-NoRepair'][['seed',metric]],on='seed',suffixes=('_full','_no'))
            for row in pair.itertuples(index=False,name=None):
                ax.plot([0,1],[row[1],row[2]],color='#AAB6BE',lw=.8,alpha=.6)
                ax.scatter([0,1],[row[1],row[2]],color=[COLORS[ABL[0]],COLORS[ABL[1]]],s=27,zorder=3)
            ax.set(xticks=[0,1],xticklabels=['完整方法','去修复'],xlim=(-.35,1.35),ylabel=lab);ax.grid(axis='x',visible=False)
        save(fig,'exp06_paired_repair')
    print(json.dumps({'summary':summary,'effects':effects},ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--results',type=Path,required=True);ap.add_argument('--figures',type=Path,required=True);a=ap.parse_args()
    # Validate fast exact HV against the independent recursive implementation.
    for seed in range(5):
        p=np.random.default_rng(seed).uniform(0,1,(7,3));assert math.isclose(hv3(p),hypervolume(p,[1.1]*3),abs_tol=1e-10)
    analyze(a.results,a.figures)
