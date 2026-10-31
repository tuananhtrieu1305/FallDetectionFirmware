"""A human-readable CSV must preserve sensor windows, labels and held-out people."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd


class ExportContracts(unittest.TestCase):
    def test_csv_npz_alignment_ignore_filter_and_split_identity(self):
        from export_dataset import export_dataset
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root=Path(temporary);source=root/'source';source.mkdir();out=root/'output'
            x=np.random.default_rng(42).normal(size=(4,100,6)).astype(np.float32)
            y=np.array([0,-1,1,0],dtype=np.int8)
            np.savez_compressed(source/'windows_100.npz',X=x,y=y)
            pd.DataFrame({'subject_id':['a','a','b','c'], 'trial_id':['t1','t1','t2','t3'],
                          'activity_key':['ADL01','ADL01','F01','ADL14'],
                          'partition':['fold1','fold1','fold0','test'],
                          'start_frame':[0,50,0,0],'end_frame':[99,149,99,99],
                          'y':y}).to_csv(source/'window_index_100.csv',index=False)
            for name in ['normalizers.json','splits.json']:
                (source/name).write_text('{}')
            export_dataset(source,out)
            frame=pd.read_csv(out/'dataset.csv',float_precision='round_trip')
            columns=[f'{channel}_{step:03}' for step in range(100)
                     for channel in ['ax','ay','az','gx','gy','gz']]
            np.testing.assert_array_equal(frame[columns].to_numpy(np.float32).reshape(-1,100,6),x[y>=0])
            np.testing.assert_array_equal(frame.y.to_numpy(),y[y>=0])
            self.assertEqual(frame.split.tolist(),['train','validation','test'])
            self.assertEqual(frame.source_window_row.tolist(),[0,2,3])
            with np.load(out/'dataset.npz') as shard:
                np.testing.assert_array_equal(shard['X'],x[y>=0])
                np.testing.assert_array_equal(shard['y'],y[y>=0])
            example=pd.read_csv(out/'examples/fall_window.csv',float_precision='round_trip')
            np.testing.assert_array_equal(example[['ax','ay','az','gx','gy','gz']].to_numpy(np.float32),x[2])
            self.assertEqual(json.loads((out/'manifest.json').read_text())['excluded_ignore_windows'],1)

    def test_reject_index_label_mismatch(self):
        from export_dataset import export_dataset
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root=Path(temporary);source=root/'source';source.mkdir()
            np.savez_compressed(source/'windows_100.npz',X=np.zeros((1,100,6),np.float32),y=np.array([1]))
            pd.DataFrame({'y':[0],'partition':['test']}).to_csv(source/'window_index_100.csv',index=False)
            with self.assertRaises(ValueError):export_dataset(source,root/'output')


if __name__=='__main__':
    unittest.main()
