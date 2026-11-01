"""Five-fold subject-independent development benchmark; locked final test.

Thresholds and window choice use development out-of-fold predictions only.
Reports use nominal source time, not validated physical seconds.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from build_univrfall import dump


def features(x):
    x = np.asarray(x, dtype=np.float64)
    x = np.concatenate([x, np.linalg.norm(x[:,:,:3],axis=2,keepdims=True),
                        np.linalg.norm(x[:,:,3:],axis=2,keepdims=True)],axis=2)
    return np.concatenate([x.mean(axis=1),x.std(axis=1),x.min(axis=1),x.max(axis=1),
                           np.sqrt((x*x).mean(axis=1))],axis=1)


def event_metrics(index, scores, threshold, recordings, length, details=False):
    rid = index.recording_id.to_numpy(int)
    ends = index.end_frame.to_numpy(int)
    positive = np.asarray(scores) >= threshold
    same = np.r_[False, rid[1:]==rid[:-1]]
    starts = positive & ~(np.r_[False,positive[:-1]] & same)
    starts_rid, starts_end = rid[starts], ends[starts]
    evaluated_ids = np.unique(rid)
    detected, total, delays, false, hours, repeats, early, late = 0,0,[],0,0.,0,0,0
    per_trial = []
    for i in evaluated_ids:
        r = recordings[int(i)]
        alarms = starts_end[starts_rid==i]
        event = r['event']
        row = dict(trial_id=r['trial_id'],subject_id=r['subject_id'],activity_key=r['activity_key'])
        if event:
            total += 1
            matched = alarms[(alarms >= event['onset']) & (alarms <= event['impact']+100)]
            got = bool(len(matched))
            detected += got
            delay = int(matched[0]-event['impact']) if got else None
            if got: delays.append(delay/100)
            early_count = int((alarms < event['onset']).sum())
            late_count = int((alarms > event['impact']+100).sum())
            early += early_count
            late += late_count
            repeats += max(0,len(matched)-1)
            row.update(detected=int(got),delay_nominal_s=None if delay is None else delay/100,
                       early_alarms=early_count,late_alarms=late_count)
        else:
            false += len(alarms)
            monitored_hours = max(0,r['rows']-length+1)/100/3600
            hours += monitored_hours
            row.update(false_alarms=len(alarms),monitored_nominal_hours=monitored_hours)
        per_trial.append(row)
    result = dict(events=total,detected=int(detected),recall=detected/total if total else None,
                  false_alarms=int(false),adl_monitored_nominal_hours=hours,
                  false_alarms_per_nominal_hour=false/hours if hours else None,
                  median_delay_nominal_s=float(np.median(delays)) if delays else None,
                  p95_delay_nominal_s=float(np.percentile(delays,95)) if delays else None,
                  extra_alarms_in_detection_interval=int(repeats),early_fall_trial_alarms=early,
                  late_fall_trial_alarms=late)
    if details:
        result['per_trial']=per_trial
        for key in ['subject_id','activity_key']:
            result['by_'+key] = {}
            for group in sorted({r[key] for r in per_trial}):
                subset = [r for r in per_trial if r[key]==group]
                events = [r for r in subset if 'detected' in r]
                adl = [r for r in subset if 'false_alarms' in r]
                duration = sum(r['monitored_nominal_hours'] for r in adl)
                result['by_'+key][group] = dict(events=len(events),detected=sum(r['detected'] for r in events),
                    false_alarms=sum(r['false_alarms'] for r in adl),adl_nominal_hours=duration)
    return result


def choose_threshold(index, scores, recordings, length):
    # Finite quantile grid plus all-negative setting, deterministic and auditable.
    thresholds = np.unique(np.r_[0.,np.quantile(scores,np.linspace(0,1,301)),np.nextafter(scores.max(),np.inf)])
    curve=[]
    for t in thresholds:
        curve.append(dict(threshold=float(t),**event_metrics(index,scores,t,recordings,length)))
    operating={}
    for limit in [.1,.25,.5,1.,2.]:
        eligible=[r for r in curve if r['false_alarms_per_nominal_hour'] is not None and
                  r['false_alarms_per_nominal_hour'] <= limit]
        best=max(eligible,key=lambda r:(r['recall'],
                    -(r['median_delay_nominal_s'] if r['median_delay_nominal_s'] is not None else 1e9),
                    -r['false_alarms_per_nominal_hour'],r['threshold']))
        operating[str(limit)]=best
    return operating,curve


def benchmark(root):
    recordings=json.loads((root/'recording_manifest.json').read_text())
    reports, predictions, feature_sets = {}, {}, {}
    for length in [100,200,300]:
        with np.load(root/f'windows_{length}.npz') as shard:
            f=features(shard['X']); y=shard['y'].copy()
        index=pd.read_csv(root/f'window_index_{length}.csv')
        dev=index.partition.ne('test').to_numpy()
        scores=np.full(len(index),np.nan)
        folds=[]
        for fold in range(5):
            valid=index.partition.eq(f'fold{fold}').to_numpy()
            train=dev & ~valid & (y>=0)
            model=make_pipeline(StandardScaler(),LogisticRegression(class_weight='balanced',
                                max_iter=2000,random_state=42,C=1.0))
            model.fit(f[train],y[train])
            scores[valid]=model.predict_proba(f[valid])[:,1]
            folds.append(dict(fold=fold,train_windows=int(train.sum()),
                              train_classes=dict(Counter(str(v) for v in y[train])),
                              validation_subjects=sorted(index.loc[valid,'subject_id'].unique().tolist())))
        if not np.isfinite(scores[dev]).all(): raise ValueError('Missing OOF predictions')
        operating,curve=choose_threshold(index[dev],scores[dev],recordings,length)
        reports[str(length)]=dict(folds=folds,operating_points=operating,threshold_curve=curve)
        predictions[length]=(index,y,scores)
        feature_sets[length]=f
        print(json.dumps(dict(length=length,development=operating['1.0'])),flush=True)
    # Declared selection rule: recall, delay, shorter window at <=1 FA/nominal h.
    selected=max([100,200,300],key=lambda l:(reports[str(l)]['operating_points']['1.0']['recall'],
                 -(reports[str(l)]['operating_points']['1.0']['median_delay_nominal_s']
                   if reports[str(l)]['operating_points']['1.0']['median_delay_nominal_s'] is not None else 1e9),-l))
    threshold=reports[str(selected)]['operating_points']['1.0']['threshold']
    dump(root/'selection_lock.json',dict(length=selected,stride=50,threshold=threshold,
                  rule='development OOF recall then median delay then shorter length at <=1 FA/nominal h',
                  test_used_for_selection=False,baseline='40 physical signal summary features; StandardScaler + balanced LogisticRegression(C=1)'))
    # Only now fit final model and score the held-out six people once.
    index,y,scores=predictions[selected]
    dev=index.partition.ne('test').to_numpy(); test=~dev
    f=feature_sets[selected]
    model=make_pipeline(StandardScaler(),LogisticRegression(class_weight='balanced',
                        max_iter=2000,random_state=42,C=1.0))
    model.fit(f[dev & (y>=0)],y[dev & (y>=0)])
    scores[test]=model.predict_proba(f[test])[:,1]
    final=event_metrics(index[test],scores[test],threshold,recordings,selected,details=True)
    valid=test & (y>=0)
    p,r,f1,_=precision_recall_fscore_support(y[valid],scores[valid]>=threshold,labels=[0,1],zero_division=0)
    final['window_metrics']=dict(confusion_matrix=confusion_matrix(y[valid],scores[valid]>=threshold,labels=[0,1]).tolist(),
                                 precision=p.tolist(),recall=r.tolist(),f1=f1.tolist())
    # Human-readable, non-executable model export; do not load downloaded pickle.
    dump(root/'baseline_model.json',dict(feature_order='mean,std,min,max,rms of ax,ay,az,gx,gy,gz,acc_norm,gyro_norm',
                    feature_scaler_mean=model[0].mean_.tolist(),feature_scaler_scale=model[0].scale_.tolist(),
                    coefficients=model[1].coef_.tolist(),intercept=model[1].intercept_.tolist(),
                    threshold=threshold,length=selected))
    report=dict(protocol='fixed six-subject test; five-fold development OOF; nominal time only',
                development=reports,selected_length=selected,threshold=threshold,test=final)
    dump(root/'benchmark.json',report)
    pd.DataFrame(final['per_trial']).to_csv(root/'test_trial_results.csv',index=False)
    index=index.copy();index['score']=scores
    index.to_csv(root/'selected_window_predictions.csv',index=False)
    print(json.dumps(dict(selected_length=selected,test={k:v for k,v in final.items() if not isinstance(v,(list,dict))})),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    args=parser.parse_args()
    benchmark(args.dataset)
