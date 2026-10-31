"""Streaming baseline adapter for the shared v1.1 evaluator, source-negative only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from benchmark_univrfall import features
from univrfall_core import physical_units
from metrics_v11 import evaluate
from run_metrics_v11 import sha, dump


def evaluate_file(path,model,chunksize=100000):
    length=model['length'];pending=np.empty((0,6));pending_rows=np.empty(0,dtype=np.int64)
    previous=None;row_count=0;segment_start=0;segment_rows=0;segments=[];scores=[];ends=[];gap_ms=0.;clock_resets=0
    if length!=100:raise ValueError('v1.1 requires length100')
    for chunk in pd.read_csv(path,chunksize=chunksize):
        imu=chunk[chunk['type']==1]
        if imu.empty:continue
        times=imu.timestamp.to_numpy(float)
        if not np.isfinite(times).all():raise ValueError('Invalid timestamp')
        deltas=np.diff(np.r_[previous,times]) if previous is not None else np.diff(times)
        gap_ms+=float(np.maximum(deltas-10,0).sum())
        clock_resets+=int((deltas<0).sum())
        values=physical_units(imu[['accX','accY','accZ','gyrX','gyrY','gyrZ']].to_numpy(float))
        boundaries=np.r_[0,np.flatnonzero(np.diff(times)!=10)+1,len(times)]
        for start,end in zip(boundaries[:-1],boundaries[1:]):
            if previous is None or times[start]-previous!=10:
                if segment_rows:segments.append(dict(first_frame=segment_start,rows=segment_rows))
                segment_start=row_count+start;segment_rows=0
                pending=np.empty((0,6));pending_rows=np.empty(0,dtype=np.int64)
            segment_rows+=end-start
            x=np.concatenate([pending,values[start:end]])
            ids=np.r_[pending_rows,np.arange(row_count+start,row_count+end)]
            offsets=np.arange(0,len(x)-length+1,50)
            if len(offsets):
                tensor=np.stack([x[s:s+length] for s in offsets]);f=features(tensor)
                z=(f-np.array(model['feature_scaler_mean']))/np.array(model['feature_scaler_scale'])
                scores.extend(expit(z@np.array(model['coefficients'])[0]+model['intercept'][0]).tolist())
                ends.extend(ids[offsets+length-1].tolist())
                used=int(offsets[-1])+50;pending=x[used:];pending_rows=ids[used:]
            else:pending=x;pending_rows=ids
            previous=times[end-1]
        row_count+=len(imu)
    if segment_rows:segments.append(dict(first_frame=segment_start,rows=segment_rows))
    record=dict(recording_id=0,trial_id=Path(path).name,subject_id='unverified_file_identity',activity_key='source_negative',
                partition='onfield',rows=row_count,event=None,segments=segments,excluded_gap_seconds=gap_ms/1000)
    index=pd.DataFrame(dict(recording_id=np.zeros(len(ends),int),end_frame=ends,y=np.zeros(len(ends),int)))
    m=evaluate([record],index,scores,model['threshold'],bootstrap=0)
    m.update(sensor_rows=row_count,segments=len(segments),windows=len(ends),timestamp_clock_resets=clock_resets,label_status='Source-negative; not independently validated',
             identity_status='Filename is not validated participant identity; no person-level bootstrap',
             alarms_per_source_negative_nominal_hour=m['false_alarms_per_nominal_hour'])
    m.pop('window_metrics',None)
    m.pop('bootstrap_95',None)
    return m


def run(raw,source,out):
    raw,source,out=Path(raw),Path(source),Path(out);destination=out/'onfield';destination.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((raw/'full_download_manifest.json').read_text())
    files={n:p for n,p in manifest.items() if '/OnField/' in n and n.endswith('.csv')}
    if len(files)!=18:raise ValueError('Require all 18 OnField files')
    model=json.loads((source/'baseline_model.json').read_text());lock=json.loads((out/'selection_lock.json').read_text())
    model['threshold']=lock['threshold']
    fingerprint=sha(Path(__file__))+sha(Path(__file__).with_name('metrics_v11.py'))+sha(Path(__file__).with_name('benchmark_univrfall.py'))
    results=[]
    for member,entry in sorted(files.items()):
        if sha(entry['file'])!=entry['sha256']:raise ValueError('Raw hash mismatch')
        key=dict(raw_sha256=entry['sha256'],model_sha256=sha(source/'baseline_model.json'),threshold=model['threshold'],code_sha256=fingerprint)
        output=destination/(Path(member).stem+'.json')
        cached=json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
        if cached.get('cache_key')==key:m=cached
        else:
            m=evaluate_file(entry['file'],model);m.update(cache_key=key,source_member=member)
            dump(output,m)
        results.append(m)
        print(json.dumps(dict(file=Path(member).name,alarms=m['false_alarms'],hours=m['adl_monitored_nominal_hours'])),flush=True)
    hours=sum(m['adl_monitored_nominal_hours'] for m in results);alarms=sum(m['false_alarms'] for m in results)
    active=sum(m['alarm_active_fraction']*m['adl_monitored_nominal_hours'] for m in results)
    from scipy.stats import chi2
    summary=dict(protocol='1.1',files=len(results),threshold=model['threshold'],threshold_retuned=False,
        alarms=alarms,monitored_nominal_hours=hours,alarms_per_source_negative_nominal_hour=alarms/hours,
        alarm_active_fraction=active/hours,longest_positive_run_nominal_s=max(m['longest_positive_run_nominal_s'] for m in results),
        poisson_one_sided_95_upper_per_hour=float(chi2.ppf(.95,2*(alarms+1))/2/hours),
        sensor_rows=sum(m['sensor_rows'] for m in results),windows=sum(m['windows'] for m in results),
        person_bootstrap='NOT APPLICABLE: filename IDs unverified',recall=None,
        label_status='Source-negative assertion, not independently validated; nominal time; do not merge with laboratory FA/h',
        per_file=[dict(source_member=m['source_member'],alarms=m['false_alarms'],hours=m['adl_monitored_nominal_hours'],
                       alarm_active_fraction=m['alarm_active_fraction']) for m in results])
    dump(destination/'summary.json',summary)
    pd.DataFrame(summary['per_file']).to_csv(destination/'by_file.csv',index=False)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('reports/metrics_v1_1'));a=p.parse_args();print(json.dumps(run(a.raw,a.source,a.out),indent=2))
