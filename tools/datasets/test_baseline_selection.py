import unittest
import numpy as np
import pandas as pd
from unittest.mock import patch

class BaselineSelection(unittest.TestCase):
    def test_configs_and_feature_input(self):
        from select_baseline import configurations,make_model
        configs=configurations()
        self.assertEqual(len(configs),13)
        self.assertEqual(len({c['id'] for c in configs}),13)
        for c in configs:
            m=make_model(c,42);m.fit(np.r_[np.zeros((20,40)),np.ones((20,40))],[0]*20+[1]*20)
            self.assertEqual(m.predict_proba(np.zeros((2,40))).shape,(2,2))

    def test_oof_train_subjects_and_ignore_exclusion(self):
        from select_baseline import oof,configurations
        index=pd.DataFrame(dict(partition=np.repeat(['fold0','fold1','fold2','fold3','fold4'],3),subject_id=np.repeat(list('abcde'),3),y=[0,1,-1]*5))
        x=np.zeros((15,40));x[:,0]=index.y
        scores,folds=oof(configurations()[0],x,index,42)
        self.assertTrue(np.isfinite(scores).all())
        for f in folds:
            self.assertFalse(set(f['train_subjects'])&set(f['validation_subjects']))
            self.assertEqual(f['train_windows'],8)
        index.loc[0,'partition']='test'
        with self.assertRaises(ValueError):oof(configurations()[0],x,index,42)

    def test_model_ranking_complexity_before_threshold(self):
        from select_baseline import ranking
        a=dict(recall=.9,macro_recall=.9,false_alarms_per_nominal_hour=.5,p95_delay_nominal_s=.4,alarm_active_fraction=.01,parameters=41,threshold=.2,id='a')
        b=dict(a,parameters=100,threshold=.9,id='b')
        self.assertGreater(ranking(a),ranking(b))

    def test_portable_models_match_sklearn(self):
        from select_baseline import configurations,make_model,tree_export,portable_predict
        rng=np.random.default_rng(42);x=rng.normal(size=(100,40));y=(x[:,0]*x[:,1]>0).astype(int)
        for c in [configurations()[0],configurations()[3],configurations()[-1]]:
            m=make_model(c,42);m.fit(x,y);p=dict(family=c['family'])
            if c['family']=='lr':p.update(mean=m[0].mean_.tolist(),scale=m[0].scale_.tolist(),coef=m[-1].coef_[0].tolist(),intercept=float(m[-1].intercept_[0]))
            else:p['trees']=tree_export(m)
            np.testing.assert_allclose(portable_predict(p,x),m.predict_proba(x)[:,1],atol=1e-12)

    def test_onfield_accepts_generic_scorer(self):
        import tempfile
        from pathlib import Path
        from onfield_metrics_v11 import evaluate_file
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/'field.csv'
            pd.DataFrame(dict(timestamp=np.arange(200)*10,type=1,accX=1000,accY=0,accZ=0,gyrX=0,gyrY=0,gyrZ=0)).to_csv(path,index=False)
            m=evaluate_file(path,dict(length=100,threshold=.5),predictor=lambda f:np.ones(len(f)))
            self.assertEqual(m['false_alarms'],1)
            self.assertAlmostEqual(m['alarm_active_fraction'],1)

    def test_complete_comparison_fixture(self):
        import json,tempfile
        from pathlib import Path
        from select_baseline import run,portable_predict
        from benchmark_univrfall import features
        from univrfall_core import window_label
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root=Path(tmp);source=root/'source';out=root/'out';source.mkdir();out.mkdir()
            (out/'EDA.md').write_text('Synthetic development EDA fixture')
            (source/'splits.json').write_text('{}')
            records=[];rows=[];tensors=[];labels=[]
            for j in range(12):
                event=dict(onset=200,impact=249) if j%2 else None
                part=f'fold{j//2}' if j<10 else 'test'
                records.append(dict(subject_id='SA'+str(j),trial_id='R'+str(j),activity_key='F01' if event else 'ADL',rows=500,frame_first=0,partition=part,event=event))
                v=np.zeros((500,6),np.float32);v[:,0]=9.8
                if event:v[249,:3]=50
                for start in range(0,401,50):
                    y=window_label(start,start+99,event)
                    rows.append(dict(recording_id=j,subject_id='SA'+str(j),trial_id='R'+str(j),activity_key=records[-1]['activity_key'],partition=part,start_frame=start,end_frame=start+99,y=y))
                    tensors.append(v[start:start+100]);labels.append(y)
            (source/'recording_manifest.json').write_text(json.dumps(records))
            pd.DataFrame(rows).to_csv(source/'window_index_100.csv',index=False)
            np.savez_compressed(source/'windows_100.npz',X=np.array(tensors),y=labels)
            result=run(source,out)
            self.assertTrue(result['eligible'])
            self.assertEqual(len(json.loads((out/'development_results.json').read_text())),14)
            self.assertFalse(json.loads((out/'selection_lock.json').read_text())['test_used_for_selection'])
            self.assertEqual(len(pd.read_csv(out/'seed_stability.csv')),9)
            model=json.loads((out/'selected_model.json').read_text())
            score=portable_predict(model,features(np.array(tensors)[-18:]))
            np.testing.assert_allclose(score,pd.read_csv(out/'test_predictions.csv').score,atol=1e-12)

    def test_acc_reference_uses_max_not_min(self):
        from benchmark_univrfall import features
        from select_baseline import portable_predict
        v=np.zeros((1,100,6));v[0,50,0]=20
        self.assertEqual(portable_predict(dict(family='acc_threshold'),features(v))[0],20)

if __name__=='__main__':unittest.main()
