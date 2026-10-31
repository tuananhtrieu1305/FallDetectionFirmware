"""Development-only label sensitivity study; never replace the locked v1 model.

The final laboratory test and all OnField scores remain external to this study.
Operational detection interval is fixed across training-label alternatives.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from benchmark_univrfall import features,choose_threshold
from build_univrfall import dump


def policy_labels(index,recordings,policy):
    labels=[]
    for w in index.itertuples(index=False):
        event=recordings[w.recording_id]['event']
        if event is None:
            labels.append(0);continue
        horizon=50 if policy=='recent_impact_50' else 100
        positive=(w.start_frame<=event['impact']<=w.end_frame<=event['impact']+horizon)
        if policy=='fall_phase_and_recent_impact':
            positive=(w.start_frame<=event['impact'] and event['onset']<=w.end_frame<=event['impact']+100)
        labels.append(1 if positive else 0 if w.end_frame<event['onset']-50 else -1)
    return np.array(labels,dtype=np.int8)


def study(root):
    index=pd.read_csv(root/'window_index_100.csv')
    dev=index.partition.ne('test').to_numpy()
    with np.load(root/'windows_100.npz') as shard:
        f=features(shard['X'][dev])
    index=index.loc[dev].reset_index(drop=True)
    recordings=json.loads((root/'recording_manifest.json').read_text())
    reports={}
    for policy in ['recent_impact_50','recent_impact_100','fall_phase_and_recent_impact']:
        y=policy_labels(index,recordings,policy)
        scores=np.full(len(index),np.nan)
        for fold in range(5):
            valid=index.partition.eq(f'fold{fold}').to_numpy()
            train=~valid & (y>=0)
            model=make_pipeline(StandardScaler(),LogisticRegression(class_weight='balanced',
                         max_iter=2000,random_state=42,C=1.0))
            model.fit(f[train],y[train]);scores[valid]=model.predict_proba(f[valid])[:,1]
        operating,_=choose_threshold(index,scores,recordings,100)
        counts={str(v):int((y==v).sum()) for v in [-1,0,1]}
        positive_ids=set(index.loc[y==1,'recording_id'])
        event_ids={int(i) for i in index.recording_id.unique() if recordings[int(i)]['event']}
        reports[policy]=dict(window_counts=counts,event_coverage=len(positive_ids),events=len(event_ids),
                             events_without_positive=[recordings[i]['trial_id'] for i in sorted(event_ids-positive_ids)],
                             operating_points=operating)
        print(json.dumps(dict(policy=policy,counts=counts,development=operating['1.0'])),flush=True)
    output=dict(scope='development only; 23 subjects, five-fold OOF, 100 samples/stride50; no test/OnField used',
                impact_evaluation_horizon_frames=100,policies=reports,
                release_policy='recent_impact_100',release_changed=False,
                reason='Sensitivity audit only; original v1 test already opened, so alternatives cannot replace its locked configuration.')
    dump(root/'label_policy_study.json',output)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    study(parser.parse_args().dataset)
