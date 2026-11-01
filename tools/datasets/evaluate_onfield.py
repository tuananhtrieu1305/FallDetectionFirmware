"""Evaluate a frozen laboratory model on source-negative OnField recordings.

Only type=1 is IMU. id also counts other message types, so id gaps are NOT used
as an IMU clock. Exact 10 ms timestamp continuity is required inside segments.
Source-negative labels are a source assertion, not independently reviewed truth.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit

from benchmark_univrfall import features
from build_univrfall import dump
from univrfall_core import physical_units


def evaluate_file(path,model,chunksize=100000):
    length=model['length']
    pending=np.empty((0,6),dtype=np.float64)
    pending_time=np.empty(0)
    pending_rows=np.empty(0,dtype=np.int64)
    previous_time=None
    previous_positive=False
    sensor_rows=segments=windows=alarms=segment_rows=monitored_samples=0
    first_time=last_time=None
    alarm_times=[]
    alarm_rows=[]
    message_types=Counter()
    max_acc=max_gyro=0.
    with pd.read_csv(path,chunksize=chunksize) as reader:
        for chunk in reader:
            if 'type' not in chunk:
                raise ValueError('Missing OnField type column')
            message_types.update(str(v) for v in chunk['type'])
            imu=chunk[chunk['type']==1]
            if imu.empty:continue
            time=imu.timestamp.to_numpy(dtype=float)
            values=physical_units(imu[['accX','accY','accZ','gyrX','gyrY','gyrZ']].to_numpy(float))
            if not np.isfinite(time).all():raise ValueError('Nonfinite OnField timestamp')
            if first_time is None:first_time=float(time[0])
            last_time=float(time[-1])
            max_acc=max(max_acc,float(np.abs(values[:,:3]).max()/9.80665))
            max_gyro=max(max_gyro,float(np.rad2deg(np.abs(values[:,3:]).max())))
            chunk_first_row=sensor_rows
            sensor_rows+=len(time)
            # Split at every anomalous timestamp; never interpolate across a gap/reset.
            boundaries=np.r_[0,np.flatnonzero(np.diff(time)!=10)+1,len(time)]
            for start,end in zip(boundaries[:-1],boundaries[1:]):
                if previous_time is None or time[start]-previous_time!=10:
                    monitored_samples+=max(0,segment_rows-length+1)
                    segment_rows=0;segments+=1
                    pending=np.empty((0,6));pending_time=np.empty(0);pending_rows=np.empty(0,dtype=np.int64);previous_positive=False
                segment_rows+=end-start
                combined=np.concatenate([pending,values[start:end]])
                combined_time=np.concatenate([pending_time,time[start:end]])
                combined_rows=np.concatenate([pending_rows,np.arange(chunk_first_row+start,chunk_first_row+end)])
                offsets=np.arange(0,len(combined)-length+1,50)
                if len(offsets):
                    # Chunk bounds keep memory finite for multi-hour source files.
                    tensor=np.stack([combined[s:s+length] for s in offsets])
                    f=features(tensor)
                    z=(f-np.asarray(model['feature_scaler_mean']))/np.asarray(model['feature_scaler_scale'])
                    score=expit(z@np.asarray(model['coefficients'])[0]+model['intercept'][0])
                    positive=score>=model['threshold']
                    starts=positive & ~np.r_[previous_positive,positive[:-1]]
                    times=combined_time[offsets+length-1]
                    alarm_times.extend(times[starts].tolist())
                    alarm_rows.extend(combined_rows[offsets+length-1][starts].tolist())
                    alarms+=int(starts.sum());windows+=len(offsets)
                    previous_positive=bool(positive[-1])
                    used=int(offsets[-1])+50
                    pending,pending_time=combined[used:],combined_time[used:]
                    pending_rows=combined_rows[used:]
                else:
                    pending,pending_time=combined,combined_time
                    pending_rows=combined_rows
                previous_time=float(time[end-1])
    monitored_samples+=max(0,segment_rows-length+1)
    hours=monitored_samples/100/3600
    return dict(sensor_rows=sensor_rows,message_types=dict(sorted(message_types.items())),
                segments=segments,windows=windows,alarms=alarms,
                monitored_nominal_hours=hours,
                alarms_per_source_negative_nominal_hour=alarms/hours if hours else None,
                first_timestamp_ms=first_time,last_timestamp_ms=last_time,
                alarm_timestamps_ms=alarm_times,alarm_sensor_rows=alarm_rows,
                accel_max_axis_g=max_acc,gyro_max_axis_dps=max_gyro)


def evaluate(raw,root,allow_partial=False):
    manifest=json.loads((raw/'full_download_manifest.json').read_text())
    selected={n:p for n,p in manifest.items() if '/OnField/' in n and n.endswith('.csv')}
    if len(selected)!=18 and not allow_partial:
        raise ValueError(f'OnField acquisition incomplete: {len(selected)}/18 files')
    model_path=root/'baseline_model.json'
    model=json.loads(model_path.read_text())
    model_hash=hashlib.sha256(model_path.read_bytes()).hexdigest()
    evaluator_hash=hashlib.sha256(Path(__file__).read_bytes()+
                                Path(__file__).with_name('benchmark_univrfall.py').read_bytes()).hexdigest()
    destination=root/'onfield';destination.mkdir(exist_ok=True)
    results=[]
    for member,p in sorted(selected.items()):
        file=Path(p['file'])
        if hashlib.sha256(file.read_bytes()).hexdigest()!=p['sha256']:
            raise ValueError(f'Changed source member {member}')
        path=destination/(Path(member).stem+'.json')
        cached=json.loads(path.read_text()) if path.exists() else {}
        if (cached.get('source_sha256')==p['sha256'] and cached.get('model_sha256')==model_hash
                and cached.get('evaluator_sha256')==evaluator_hash):
            result=cached
        else:
            try:
                result=evaluate_file(file,model)
                result.update(status='PASS',source_member=member,source_sha256=p['sha256'],
                              model_sha256=model_hash,evaluator_sha256=evaluator_hash,
                              source_id=Path(member).stem.split('_')[-1],
                              subject_identity_status='unverified filename token; not a validated participant identity',
                              session=Path(member).parent.name)
            except (ValueError,KeyError) as exc:
                result=dict(status='HOLD',reason=str(exc),source_member=member,
                            source_sha256=p['sha256'],model_sha256=model_hash,evaluator_sha256=evaluator_hash)
            dump(path,result)
        results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k!='alarm_timestamps_ms'}),flush=True)
    valid=[r for r in results if r['status']=='PASS']
    hours=sum(r['monitored_nominal_hours'] for r in valid)
    alarms=sum(r['alarms'] for r in valid)
    summary=dict(expected_files=18,available_files=len(selected),evaluated_files=len(valid),
                 complete=len(valid)==18,source_label='NON_FALL according to Zenodo; not independently verified',
                 model_sha256=model_hash,threshold_retuned=False,
                 units='mg/mdps interpreted from source technical metadata; converted identically to laboratory',
                 nominal_rate_hz=100,segmentation='split when consecutive IMU timestamps differ from 10ms',
                 monitored_nominal_hours=hours,alarms=alarms,
                 alarms_per_source_negative_nominal_hour=alarms/hours if hours else None,
                 distinct_filename_ids=sorted({r['source_id'] for r in valid}),
                 identity_note='Source reports 10 field participants; filename IDs are preserved without assuming one ID equals one person.',
                 files=results)
    dump(root/'onfield_evaluation.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    evaluate(args.raw,args.dataset,args.allow_partial)
