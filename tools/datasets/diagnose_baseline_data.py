"""Diagnostic plots and fixed LR sensor-group ablations, development only."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from select_baseline import oof
from benchmark_univrfall import features
from metrics_v11 import select_threshold,evaluate
from run_metrics_v11 import dump
from analyze_baseline_data import NAMES


def run(source,out):
    records=[dict(r,recording_id=j) for j,r in enumerate(json.loads((source/'recording_manifest.json').read_text())) if r['partition']!='test']
    index=pd.read_csv(source/'window_index_100.csv');mask=index.partition.ne('test').to_numpy();index=index[mask].reset_index(drop=True)
    with np.load(source/'windows_100.npz') as d:x=features(d['X'][mask])
    chosen=['F01','F03','F14','ADL14','ADL19','ADL10','ADL44']
    for activity in chosen:
        r=next(r for r in records if r['activity_key']==activity)
        with np.load(source/r['recording']) as d:v=d['values'];frame=d['frame']
        t=(frame-frame[0])/100;fig,axs=plt.subplots(6,1,figsize=(12,10),sharex=True)
        for k,ax in enumerate(axs):
            ax.plot(t,v[:,k],lw=.8);ax.set_ylabel(['ax','ay','az','gx','gy','gz'][k]+(' m/s2' if k<3 else ' rad/s'))
            if r['event']:
                ax.axvline((r['event']['onset']-frame[0])/100,c='orange');ax.axvline((r['event']['impact']-frame[0])/100,c='r')
        axs[0].set_title(r['trial_id']+' '+activity);axs[-1].set_xlabel('nominal seconds');fig.tight_layout();fig.savefig(out/'plots'/f'six_channels_{activity}.png',dpi=120);plt.close(fig)
    trials=pd.read_csv(out/'feature_medians_by_trial.csv');metadata=pd.read_csv(out/'development_trials.csv')[['recording_id','subject_id']]
    trials=trials.merge(metadata,on='recording_id')
    person=trials.groupby('subject_id')[NAMES].median();person.to_csv(out/'features_by_subject.csv')
    display=(person-person.mean())/person.std().replace(0,1)
    fig,ax=plt.subplots(figsize=(16,8));im=ax.imshow(display,cmap='coolwarm',vmin=-3,vmax=3);ax.set_yticks(range(len(person)),person.index);ax.set_xticks(range(40),NAMES,rotation=90,fontsize=7);fig.colorbar(im);fig.tight_layout();fig.savefig(out/'plots'/'subject_feature_shift.png',dpi=120);plt.close(fig)
    from scipy.stats import mannwhitneyu
    overlap=[]
    for name in NAMES:
        a=trials.loc[trials.y.eq(1),name];b=trials.loc[trials.y.eq(0),name]
        # Descriptive rank separation only; no p-values/independence claim.
        auc=mannwhitneyu(a,b).statistic/(len(a)*len(b))
        overlap.append(dict(feature=name,fall_median=float(a.median()),nonfall_median=float(b.median()),rank_separation=float(max(auc,1-auc))))
    pd.DataFrame(overlap).to_csv(out/'feature_overlap_descriptive.csv',index=False)
    results={}
    for name,channels in [('acc_only',[0,1,2,6]),('gyro_only',[3,4,5,7])]:
        cols=[block*8+c for block in range(5) for c in channels]
        score,folds=oof(dict(id=name,family='lr',C=1.),x[:,cols],index,42)
        best,_=select_threshold(records,index,score)
        results[name]=evaluate(records,index,score,best['threshold']) if best else {'eligible':False}
        dump(out/'sensor_ablation.json',results);print(name,results[name].get('recall'),flush=True)
    return results

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('reports/baseline_selection'));a=p.parse_args();run(a.source,a.out)
