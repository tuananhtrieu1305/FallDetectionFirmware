"""Streaming evaluation must agree across chunks and never bridge sensor gaps."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd


class StreamingContracts(unittest.TestCase):
    def test_incomplete_source_rejected_and_partial_results_cached(self):
        from evaluate_onfield import evaluate
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root=Path(temporary);raw=root/'raw';raw.mkdir();dataset=root/'dataset';dataset.mkdir()
            csv=raw/'field.csv'
            pd.DataFrame({'timestamp':np.arange(200)*10,'type':1,'accX':1000,
                          'accY':0,'accZ':0,'gyrX':0,'gyrY':0,'gyrZ':0}).to_csv(csv,index=False)
            manifest={'UniVrFall_Dataset/OnField/20241106/20241106_1000.csv':
                      {'file':str(csv),'sha256':hashlib.sha256(csv.read_bytes()).hexdigest()}}
            (raw/'full_download_manifest.json').write_text(json.dumps(manifest))
            model=dict(length=100,threshold=.4,feature_scaler_mean=[0]*40,
                       feature_scaler_scale=[1]*40,coefficients=[[0]*40],intercept=[0])
            (dataset/'baseline_model.json').write_text(json.dumps(model))
            with self.assertRaises(ValueError):evaluate(raw,dataset)
            result=evaluate(raw,dataset,allow_partial=True)
            self.assertFalse(result['complete']);self.assertEqual(result['alarms'],1)
            with patch('evaluate_onfield.evaluate_file',side_effect=AssertionError('Should reuse verified cache')):
                self.assertEqual(evaluate(raw,dataset,allow_partial=True),result)

    def test_chunk_invariance_type_filter_gaps_and_warmup(self):
        from evaluate_onfield import evaluate_file
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root=Path(temporary)
            frame=pd.DataFrame({'id':np.arange(501), 'timestamp':np.arange(501)*10,
                                'type':1, 'accX':1000,'accY':0,'accZ':0,
                                'gyrX':0,'gyrY':0,'gyrZ':0})
            # Non-IMU message with an interleaved ID must not create an IMU gap.
            extra=frame.iloc[[10]].copy();extra['type']=2;extra['timestamp']=95
            frame=pd.concat([frame.iloc[:10],extra,frame.iloc[10:]],ignore_index=True)
            path=root/'field.csv';frame.to_csv(path,index=False)
            model=dict(length=100,threshold=.4,feature_scaler_mean=[0]*40,
                       feature_scaler_scale=[1]*40,coefficients=[[0]*40],intercept=[0])
            outputs=[evaluate_file(path,model,chunksize=n) for n in [1,37,1000]]
            self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[1],outputs[2])
            self.assertEqual(outputs[0]['alarms'],1)
            self.assertEqual(outputs[0]['alarm_sensor_rows'],[99])
            self.assertEqual(outputs[0]['windows'],9)
            self.assertEqual(outputs[0]['sensor_rows'],501)
            self.assertEqual(outputs[0]['segments'],1)
            frame.loc[frame['timestamp']>=2500,'timestamp']+=100
            frame.to_csv(path,index=False)
            gaps=evaluate_file(path,model,chunksize=37)
            self.assertEqual(gaps['segments'],2)
            self.assertEqual(gaps['alarms'],2)
            self.assertLess(gaps['monitored_nominal_hours'],outputs[0]['monitored_nominal_hours'])

    def test_missing_imu_is_not_zero_filled(self):
        from evaluate_onfield import evaluate_file
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            path=Path(temporary)/'invalid.csv'
            pd.DataFrame({'timestamp':[0,10], 'type':[1,1], 'accX':[1000,np.nan],
                          'accY':[0,0],'accZ':[0,0],'gyrX':[0,0],'gyrY':[0,0],'gyrZ':[0,0]}).to_csv(path,index=False)
            with self.assertRaises(ValueError):
                evaluate_file(path,dict(length=100),chunksize=10)


if __name__=='__main__':
    unittest.main()
