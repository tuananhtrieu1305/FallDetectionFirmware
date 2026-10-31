"""Extract auditable source-negative alarm context, without changing labels."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from univrfall_core import physical_units


def review(raw,dataset):
    manifest=json.loads((raw/'full_download_manifest.json').read_text())
    report=json.loads((dataset/'onfield_evaluation.json').read_text())
    destination=dataset/'onfield_review';destination.mkdir(exist_ok=True)
    windows=[]
    for record in report['files']:
        if record['status']!='PASS' or not record['alarms']:continue
        rows=record['alarm_sensor_rows']
        pieces={i:[] for i in range(len(rows))}
        offset=0
        with pd.read_csv(manifest[record['source_member']]['file'],chunksize=100000) as reader:
            for chunk in reader:
                imu=chunk[chunk['type']==1].copy()
                imu['sensor_row']=np.arange(offset,offset+len(imu));offset+=len(imu)
                for i,alarm in enumerate(rows):
                    chosen=imu[(imu.sensor_row>=alarm-200)&(imu.sensor_row<=alarm+200)]
                    if len(chosen):pieces[i].append(chosen)
        for i,parts in pieces.items():
            context=pd.concat(parts,ignore_index=True)
            values=physical_units(context[['accX','accY','accZ','gyrX','gyrY','gyrZ']].to_numpy())
            exported=pd.DataFrame(values,columns=['ax','ay','az','gx','gy','gz'])
            exported.insert(0,'timestamp_ms',context.timestamp.to_numpy())
            exported.insert(0,'sensor_row',context.sensor_row.to_numpy())
            name=f"{Path(record['source_member']).stem}_alarm_{i+1:03}"
            exported.to_csv(destination/f'{name}.csv',index=False)
            windows.append(dict(name=name,source_id=record['source_id'],session=record['session'],
                                source_member=record['source_member'],source_sha256=record['source_sha256'],
                                alarm_sensor_row=rows[i],alarm_timestamp_ms=record['alarm_timestamps_ms'][i],
                                context=exported))
    index=[]
    for page in range((len(windows)+7)//8):
        fig,axes=plt.subplots(4,2,figsize=(16,12),layout='constrained')
        for ax,w in zip(axes.flat,windows[page*8:(page+1)*8]):
            context=w['context'];t=(context.timestamp_ms.to_numpy()-w['alarm_timestamp_ms'])/1000
            x=context[['ax','ay','az','gx','gy','gz']].to_numpy()
            ax.plot(t,np.linalg.norm(x[:,:3],axis=1)/9.80665,label='|a| (g)',lw=.8)
            ax.plot(t,np.linalg.norm(x[:,3:],axis=1),label='|gyro| (rad/s)',lw=.8)
            ax.axvline(0,color='red',lw=.8)
            ax.set_title(w['name'],fontsize=9);ax.set_xlabel('Source timestamp seconds relative to alarm')
            ax.legend(fontsize=7);ax.grid(alpha=.2)
            index.append({**{k:v for k,v in w.items() if k!='context'},'plot_page':f'alarms_{page+1:02}.png',
                          'label':'source NON_FALL; not independently verified',
                          'usage':'external test inspection only; not used to retune v1'})
        for ax in list(axes.flat)[len(windows[page*8:(page+1)*8]):]:ax.set_visible(False)
        fig.savefig(destination/f'alarms_{page+1:02}.png',dpi=110);plt.close(fig)
    pd.DataFrame(index).to_csv(destination/'alarm_index.csv',index=False)
    print(json.dumps(dict(alarms_reviewable=len(windows),pages=(len(windows)+7)//8)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    args=parser.parse_args()
    review(args.raw,args.dataset)
