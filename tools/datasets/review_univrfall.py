"""Generate deterministic sensor/annotation review sheets and timing summaries."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def review(root):
    rows=json.loads((root/'recording_manifest.json').read_text())
    destination=root/'review';destination.mkdir(exist_ok=True)
    selected=set()
    for key in ['subject_id','activity_key']:
        for value in sorted({r[key] for r in rows}):
            for label in ([0,1] if key=='subject_id' else [None]):
                choices=[r for r in rows if r[key]==value and (label is None or r['label']==label)]
                if choices:selected.add(choices[0]['trial_id'])
    selected.update(r['trial_id'] for r in rows if 'gyro_above_published_range' in r['flags'])
    chosen=[r for r in rows if r['trial_id'] in selected]
    index=[]
    for page in range((len(chosen)+7)//8):
        fig,axes=plt.subplots(4,2,figsize=(16,13),layout='constrained')
        for ax,r in zip(axes.flat,chosen[page*8:(page+1)*8]):
            with np.load(root/r['recording']) as d:
                t=d['time_s'];x=d['values']
            ax.plot(t,np.linalg.norm(x[:,:3],axis=1)/9.80665,label='|a| (g)',lw=.7)
            ax.plot(t,np.linalg.norm(x[:,3:],axis=1),label='|gyro| (rad/s)',lw=.7,alpha=.8)
            if r['event']:
                a=(r['event']['onset']-r['frame_first'])/100
                b=(r['event']['impact']-r['frame_first'])/100
                ax.axvspan(a,b,color='red',alpha=.15)
                ax.axvline(b,color='red',lw=.6)
            ax.set_title(f"{r['trial_id']} | {r['activity_key']} | {r['partition']}",fontsize=10)
            ax.set_xlabel('Nominal seconds (source clock unverified)')
            ax.legend(fontsize=7);ax.grid(alpha=.2)
            index.append(dict(trial_id=r['trial_id'],activity=r['activity'],subject_id=r['subject_id'],
                              page=f'review_{page+1:02}.png',flags='|'.join(r['flags']),
                              review_limit='Signal/annotation alignment only; no video/semantic confirmation'))
        for ax in list(axes.flat)[len(chosen[page*8:(page+1)*8]):]:ax.set_visible(False)
        fig.savefig(destination/f'review_{page+1:02}.png',dpi=110);plt.close(fig)
    pd.DataFrame(index).to_csv(destination/'review_index.csv',index=False)
    fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
    axes[0].hist([r['host_effective_hz'] for r in rows],bins=30)
    axes[0].axvline(100,color='red');axes[0].set(xlabel='Host-derived effective Hz',ylabel='Trials')
    axes[1].hist([r['accel_max_g'] for r in rows if r['label']==0],bins=30,alpha=.6,label='ADL')
    axes[1].hist([r['accel_max_g'] for r in rows if r['label']==1],bins=30,alpha=.6,label='Fall')
    axes[1].set(xlabel='Maximum absolute acceleration axis (g)');axes[1].legend()
    axes[2].hist([r['gyro_max_dps'] for r in rows],bins=30)
    axes[2].axvline(2000,color='red');axes[2].set(xlabel='Maximum absolute gyro axis (deg/s)')
    fig.savefig(destination/'quality_distributions.png',dpi=130);plt.close(fig)
    print(json.dumps(dict(selected_trials=len(chosen),pages=(len(chosen)+7)//8,review_index=str(destination/'review_index.csv'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    review(parser.parse_args().dataset)
