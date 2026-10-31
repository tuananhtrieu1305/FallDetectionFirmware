"""Fixed development-only comparison of 13 justified classical baselines."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from benchmark_univrfall import features
from metrics_v11 import select_threshold,evaluate
from run_metrics_v11 import dump,sha


def configurations():
    return ([dict(id=f'lr_C{c}',family='lr',C=c) for c in [.1,1.,10.]]+
            [dict(id=f'dt_d{d}_l{leaf}',family='dt',depth=d,leaf=leaf) for d in [3,5,8] for leaf in [10,30]]+
            [dict(id=f'rf_d{d}_l{leaf}',family='rf',depth=d,leaf=leaf) for d in [5,10] for leaf in [10,30]])


def make_model(c,seed):
    if c['family']=='lr':return make_pipeline(StandardScaler(),LogisticRegression(C=c['C'],class_weight='balanced',random_state=seed,max_iter=2000))
    if c['family']=='dt':return DecisionTreeClassifier(max_depth=c['depth'],min_samples_leaf=c['leaf'],class_weight='balanced',random_state=seed)
    if c['family']=='rf':return RandomForestClassifier(n_estimators=100,max_depth=c['depth'],min_samples_leaf=c['leaf'],class_weight='balanced',max_features='sqrt',random_state=seed,n_jobs=1)
    raise ValueError('Unknown model')


def parameter_count(m):
    if hasattr(m,'steps'):return int(m[-1].coef_.size+m[-1].intercept_.size)
    trees=m.estimators_ if hasattr(m,'estimators_') else [m]
    return int(sum(t.tree_.node_count*7 for t in trees))


def oof(config,x,index,seed):
    if set(index.partition)!=set(f'fold{k}' for k in range(5)):raise ValueError('Only all five development folds are permitted')
    people=index.groupby('subject_id').partition.nunique()
    if (people!=1).any():raise ValueError('Subject crosses fold boundary')
    scores=np.full(len(index),np.nan);logs=[]
    for k in range(5):
        valid=index.partition.eq(f'fold{k}').to_numpy();train=(~valid)&index.y.ge(0).to_numpy()
        m=make_model(config,seed);m.fit(x[train],index.y.to_numpy()[train]);scores[valid]=m.predict_proba(x[valid])[:,1]
        logs.append(dict(fold=k,train_windows=int(train.sum()),train_subjects=sorted(index.loc[train,'subject_id'].unique().tolist()),
            validation_subjects=sorted(index.loc[valid,'subject_id'].unique().tolist()),parameters=parameter_count(m)))
    if not np.isfinite(scores).all():raise ValueError('Incomplete OOF')
    return scores,logs


def ranking(m):
    return (m['recall'] if m['recall'] is not None else -1,m['macro_recall'] if m['macro_recall'] is not None else -1,
        -m['false_alarms_per_nominal_hour'],-(m['p95_delay_nominal_s'] if m['p95_delay_nominal_s'] is not None else np.inf),
        -m['alarm_active_fraction'],-m['parameters'],m['threshold'],tuple(-ord(c) for c in m['id']))


def brief(m):return {k:v for k,v in m.items() if k not in ['per_trial','alarms','by_subject_id','by_activity_key']}


def tree_export(m):
    trees=m.estimators_ if hasattr(m,'estimators_') else [m]
    return [dict(left=t.tree_.children_left.tolist(),right=t.tree_.children_right.tolist(),feature=t.tree_.feature.tolist(),
                 threshold=t.tree_.threshold.tolist(),value=t.tree_.value[:,0,:].tolist()) for t in trees]


def portable_predict(model,x):
    if model['family']=='lr':
        from scipy.special import expit
        return expit(((x-np.array(model['mean']))/np.array(model['scale']))@np.array(model['coef'])+model['intercept'])
    if model['family']=='acc_threshold':return x[:,22] # max acc_norm: block max offset16 + channel6
    total=np.zeros(len(x))
    for tree in model['trees']:
        node=np.zeros(len(x),int)
        while True:
            pending=np.array(tree['left'])[node]>=0
            if not pending.any():break
            ii=np.flatnonzero(pending);n=node[ii];feature=np.array(tree['feature'])[n]
            choose=x[ii,feature]<=np.array(tree['threshold'])[n]
            node[ii]=np.where(choose,np.array(tree['left'])[n],np.array(tree['right'])[n])
        v=np.array(tree['value'])[node];total+=v[:,1]/v.sum(axis=1)
    return total/len(model['trees'])


def run(source,out):
    source,out=Path(source),Path(out);out.mkdir(parents=True,exist_ok=True);cache=out/'cache';cache.mkdir(exist_ok=True)
    if not (out/'EDA.md').exists():raise ValueError('Run and review development EDA first')
    records=[dict(r,recording_id=j) for j,r in enumerate(json.loads((source/'recording_manifest.json').read_text()))]
    all_index=pd.read_csv(source/'window_index_100.csv');dev=all_index.partition.ne('test').to_numpy();index=all_index[dev].reset_index(drop=True)
    rr=[r for r in records if r['partition']!='test']
    with np.load(source/'windows_100.npz') as a: x=features(a['X'][dev])
    lock=dict(configurations=configurations(),window=100,stride=50,seed=42,features='fixed 40 historical statistics',
              EDA_sha256=sha(out/'EDA.md'),development_index_sha256=__import__('hashlib').sha256(index.to_csv(index=False).encode()).hexdigest(),
              split_sha256=sha(source/'splits.json'),selection_protocol='metrics v1.1, <=1FA/h; parameter proxy is max fold numeric model entries, tree=7 entries/node',
              test_used_for_selection=False,code_sha256=sha(__file__))
    dump(out/'experiment_lock.json',lock)
    key=__import__('hashlib').sha256(json.dumps(lock,sort_keys=True).encode()).hexdigest()
    rows=[];details={};configs=configurations()+[dict(id='acc_threshold',family='acc_threshold')];score_table=index.copy()
    for c in configs:
        path=cache/(c['id']+'_42.npz');logpath=cache/(c['id']+'_42.json')
        if path.exists() and logpath.exists() and json.loads(logpath.read_text())['key']==key:
            score=np.load(path)['score'];meta=json.loads(logpath.read_text());folds=meta['folds'];train_s=meta['train_seconds']
        else:
            t=time.perf_counter()
            if c['family']=='acc_threshold':score=x[:,22].copy();folds=[]
            else:score,folds=oof(c,x,index,42)
            train_s=time.perf_counter()-t;np.savez_compressed(path,score=score);dump(logpath,dict(key=key,folds=folds,train_seconds=train_s))
        score_table[c['id']]=score
        best,curve=select_threshold(rr,index,score)
        if best is None:rows.append(dict(id=c['id'],family=c['family'],eligible=False));continue
        m=evaluate(rr,index,score,best['threshold']);details[c['id']]=m
        row=dict(id=c['id'],family=c['family'],eligible=True,parameters=max([f['parameters'] for f in folds],default=1),train_seconds=train_s,**brief(m))
        rows.append(row);dump(cache/(c['id']+'_metrics.json'),m)
        pd.DataFrame(curve).to_csv(cache/(c['id']+'_threshold_curve.csv'),index=False)
        dump(out/'development_results.json',rows)
        print(json.dumps(dict(id=c['id'],recall=m['recall'],fa_h=m['false_alarms_per_nominal_hour'])),flush=True)
    dump(out/'development_results.json',rows)
    score_table.to_csv(out/'oof_predictions.csv',index=False)
    eligible=[r for r in rows if r['eligible']];winner=max(eligible,key=ranking)
    # Seed robustness is diagnostic; seed42 ranking remains locked.
    stability=[]
    for family in ['lr','dt','rf']:
        family_candidates=[r for r in eligible if r['family']==family]
        if not family_candidates:
            stability.extend(dict(id=family+'_NONE',seed=seed,recall=None,eligible=False) for seed in [42,43,44])
            continue
        family_best=max(family_candidates,key=ranking)
        c=next(c for c in configs if c['id']==family_best['id'])
        stability.append(dict(id=c['id'],seed=42,**{k:family_best[k] for k in ['recall','false_alarms_per_nominal_hour','threshold']}))
        for seed in [43,44]:
            score,folds=oof(c,x,index,seed);best,_=select_threshold(rr,index,score)
            stability.append(dict(id=c['id'],seed=seed,**(best or dict(recall=None,threshold=None,false_alarms_per_nominal_hour=None))))
            np.savez_compressed(cache/(c['id']+f'_{seed}.npz'),score=score);dump(cache/(c['id']+f'_{seed}.json'),dict(folds=folds))
            print(f'STABILITY {c["id"]} seed{seed}',flush=True)
    pd.DataFrame(stability).to_csv(out/'seed_stability.csv',index=False)
    c=next(c for c in configs if c['id']==winner['id'])
    dump(out/'selection_lock.json',dict(winner=c,threshold=winner['threshold'],seed=42,parameters=winner['parameters'],
        test_used_for_selection=False,experiment_sha256=sha(out/'experiment_lock.json'),development_results_sha256=sha(out/'development_results.json')))
    # Only after selection lock fit on all development, and read test tensors.
    supervised=index.y.ge(0).to_numpy();t=time.perf_counter()
    if c['family']=='acc_threshold':model=dict(family=c['family'])
    else:
        fitted=make_model(c,42);fitted.fit(x[supervised],index.y.to_numpy()[supervised]);model=dict(family=c['family'])
        if c['family']=='lr':model.update(mean=fitted[0].mean_.tolist(),scale=fitted[0].scale_.tolist(),coef=fitted[-1].coef_[0].tolist(),intercept=float(fitted[-1].intercept_[0]))
        else:model['trees']=tree_export(fitted)
        np.testing.assert_allclose(portable_predict(model,x),fitted.predict_proba(x)[:,1],atol=1e-12)
    model.update(threshold=winner['threshold'],length=100,features='40 statistics; physical units m/s2 and rad/s')
    dump(out/'selected_model.json',model)
    with np.load(source/'windows_100.npz') as a:xtest=features(a['X'][~dev])
    ti=all_index[~dev].copy();testscore=portable_predict(model,xtest)
    test=evaluate([r for r in records if r['partition']=='test'],ti,testscore,model['threshold'])
    ti['score']=testscore;ti.to_csv(out/'test_predictions.csv',index=False);dump(out/'test_metrics.json',test)
    selected=details[winner['id']]
    for name,m in [('development',selected),('test',test)]:
        pd.DataFrame(m['per_trial']).to_csv(out/(name+'_events.csv'),index=False);pd.DataFrame(m['alarms']).to_csv(out/(name+'_alarms.csv'),index=False)
        for field in ['subject_id','activity_key']:
            pd.DataFrame.from_dict(m['by_'+field],orient='index').to_csv(out/(name+'_by_'+field+'.csv'))
    pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in rows]).to_csv(out/'comparison.csv',index=False)
    # Host measurements include feature extraction + inference; not ESP32 performance.
    import statistics
    sample=np.zeros((1,100,6));timings=[]
    for k in range(110):
        t=time.perf_counter();portable_predict(model,features(sample));dt=(time.perf_counter()-t)*1000
        if k>=10:timings.append(dt)
    dump(out/'host_cost.json',dict(model_bytes=(out/'selected_model.json').stat().st_size,
        preprocessing_and_inference_ms_median=float(np.median(timings)),p95_ms=float(np.percentile(timings,95)),max_ms=max(timings),
        platform=__import__('platform').platform(),hardware_RAM='NOT MEASURED',ESP32_latency='NOT MEASURED'))
    return winner

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('reports/baseline_selection'));a=p.parse_args();print(json.dumps(run(a.source,a.out),indent=2))
