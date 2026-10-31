import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

class OnFieldV11(unittest.TestCase):
    def test_stream_chunks_gaps_active_and_tail(self):
        from onfield_metrics_v11 import evaluate_file
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            p=Path(tmp)/'field.csv'
            a=pd.DataFrame(dict(timestamp=np.arange(501)*10,type=1,accX=1000,accY=0,accZ=0,gyrX=0,gyrY=0,gyrZ=0))
            extra=a.iloc[[0]].copy();extra['type']=2;extra['timestamp']=5
            a=pd.concat([a.iloc[:1],extra,a.iloc[1:]],ignore_index=True)
            a.loc[a.timestamp>=2500,'timestamp']+=100
            a.to_csv(p,index=False)
            model=dict(length=100,threshold=.4,feature_scaler_mean=[0]*40,feature_scaler_scale=[1]*40,coefficients=[[0]*40],intercept=[0])
            results=[evaluate_file(p,model,chunksize=k) for k in [1,37,1000]]
            self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])
            m=results[0];self.assertEqual(m['false_alarms'],2)
            self.assertEqual(m['sensor_rows'],501)
            self.assertAlmostEqual(m['alarm_active_fraction'],1)
            self.assertAlmostEqual(m['adl_monitored_nominal_hours'],303/100/3600)
            self.assertAlmostEqual(m['longest_positive_run_nominal_s'],1.52)
            self.assertEqual(m['bootstrap_95']['subjects'],1) # internal file identity, not person-level CI

if __name__=='__main__':unittest.main()
