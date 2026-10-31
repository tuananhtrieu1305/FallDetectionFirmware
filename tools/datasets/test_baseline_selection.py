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

if __name__=='__main__':unittest.main()
