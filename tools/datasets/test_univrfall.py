"""Dataset contracts: no temporal/subject leakage or invented annotations."""
import sys
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import univrfall_core as core


class DatasetContracts(unittest.TestCase):
    def annotation(self, code='F01 (22)', onset=120, impact=160):
        return pd.DataFrame([[code, 'Forward fall', 1, onset, impact]], columns=[
            'Task Code (Task ID)', 'Description', 'Trial ID',
            'Fall_onset_frame', 'Fall_impact_frame'])

    def test_subject_specific_mapping_and_missing_is_not_normal(self):
        labels = core.parse_annotations(self.annotation())
        self.assertEqual(labels[(22, 1)]['fall_code'], 'F01')
        self.assertEqual(core.resolve_label(22, 1, labels)['label'], 1)
        self.assertEqual(core.resolve_label(14, 1, labels)['label'], 0)
        with self.assertRaises(ValueError):
            core.resolve_label(20, 1, labels)

    def test_annotations_reject_duplicate_missing_or_noninteger_event(self):
        for table in [pd.concat([self.annotation(), self.annotation()]),
                      self.annotation(onset=np.nan), self.annotation(impact=160.5),
                      self.annotation(onset=170), self.annotation(code='garbage')]:
            with self.assertRaises(ValueError):
                core.parse_annotations(table)

    def test_unit_and_frame_validation(self):
        values = core.physical_units(np.array([[1000, 0, -1000, 180000, 0, -180000]]))
        np.testing.assert_allclose(values, [[9.80665, 0, -9.80665, np.pi, 0, -np.pi]])
        for frames, values in [([0, 2], np.zeros((2, 6))),
                               ([0, 0], np.zeros((2, 6))),
                               ([0, 1.5], np.zeros((2, 6))),
                               ([0, 1], np.full((2, 6), np.nan))]:
            with self.assertRaises(ValueError):
                core.validate_trial(np.array(frames), values, None)
        with self.assertRaises(ValueError):
            core.validate_trial(np.arange(200), np.zeros((200, 6)), {'onset': 120, 'impact': 201})

    def test_window_boundary_policy_and_no_padding(self):
        event = {'onset': 236, 'impact': 319}
        self.assertEqual(core.window_label(200, 399, event), 1)
        self.assertEqual(core.window_label(220, 419, event), 1)
        self.assertEqual(core.window_label(221, 420, event), -1)
        self.assertEqual(core.window_label(320, 519, event), -1)
        self.assertEqual(core.window_label(0, 185, event), 0)
        self.assertEqual(core.window_label(0, 186, event), -1)
        self.assertEqual(core.window_label(0, 318, event), -1)
        self.assertEqual(core.window_label(0, 999, None), 0)
        self.assertEqual(list(core.window_bounds(199, 200, 50)), [])
        self.assertEqual(list(core.window_bounds(250, 200, 50)), [(0, 199), (50, 249)])

    def test_splits_repeatable_disjoint_balanced(self):
        rows = [{'subject_id': f'S{i:02}', 'activity_key': a,
                 'label': int(a == 'F01'), 'rows': 500} for i in range(29)
                for a in ['F01', 'ADL14']]
        split = core.subject_split(rows)
        self.assertEqual(split, core.subject_split(rows[::-1]))
        self.assertEqual(sum(v == 'test' for v in split.values()), 6)
        self.assertEqual(set(split.values()), {'test', 'fold0', 'fold1', 'fold2', 'fold3', 'fold4'})

    def test_normalization_uses_only_training_unwindowed_rows(self):
        train = [np.zeros((3, 6)), np.full((1, 6), 4)]
        stats = core.fit_normalizer(train)
        np.testing.assert_allclose(stats['mean'], np.ones(6))
        np.testing.assert_allclose(stats['std'], np.full(6, np.sqrt(3)))
        normalized = core.apply_normalizer(np.full((2, 6), 1000), stats)
        self.assertTrue((normalized > 500).all())
        np.testing.assert_array_equal(core.apply_normalizer(np.ones((2, 6)), stats), 0)

    def test_event_evaluation_counts_alarm_runs_not_windows(self):
        result = core.evaluate_sequence([249, 299, 349, 399, 449, 499],
                                        [False, False, True, True, False, True],
                                        {'onset': 236, 'impact': 319})
        self.assertEqual(result['detected'], 1)
        self.assertEqual(result['delay_frames'], 30)
        self.assertEqual(result['repeat_alarms'], 1)
        normal = core.evaluate_sequence([199, 249, 299, 349], [True, True, False, True], None)
        self.assertEqual(normal['false_alarms'], 2)
        # An alarm already active before onset is not a new event detection.
        result = core.evaluate_sequence([199, 249, 299, 349], [True]*4,
                                        {'onset': 236, 'impact': 319})
        self.assertEqual(result['detected'], 0)

    def test_full_pipeline_reproducible_fixture(self):
        from build_univrfall import build
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            raw = root / 'raw'
            raw.mkdir()
            manifest = {}
            for i in range(11):
                for task in [14, 22]:
                    name = f'UniVrFall_Dataset/laboratory/sensors_data/SA{i:02}/S{i:02}T{task:02}R01.csv'
                    path = raw / Path(name).name
                    frame = np.arange(400)
                    pd.DataFrame(np.column_stack([frame*10, frame, np.full((400, 6), i+1),
                                                  np.zeros((400, 3))]), columns=[
                        'Unnamed: 0' if i == 0 else 'TimeStamp(s)', 'FrameCounter', 'AccX', 'AccY', 'AccZ',
                        'GyrX', 'GyrY', 'GyrZ', 'EulerX', 'EulerY', 'EulerZ']).to_csv(path, index=False)
                    manifest[name] = dict(file=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                name = f'UniVrFall_Dataset/laboratory/labels_data/SA{i:02}_label.xlsx'
                path = raw / f'SA{i:02}_label.xlsx'
                self.annotation(code='F03 (22)', onset=200, impact=250).to_excel(path, index=False)
                manifest[name] = dict(file=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            (raw/'full_download_manifest.json').write_text(json.dumps(manifest))
            build(raw, root/'a', expected_csv=22)
            build(raw, root/'b', expected_csv=22)
            self.assertEqual((root/'a/splits.json').read_bytes(), (root/'b/splits.json').read_bytes())
            self.assertEqual((root/'a/tensor_hashes.json').read_bytes(),
                             (root/'b/tensor_hashes.json').read_bytes())
            report = json.loads((root/'a/audit.json').read_text())
            self.assertEqual(report['accepted_trials'], 22)
            for record in json.loads((root/'a/recording_manifest.json').read_text()):
                self.assertTrue(record['source_member'].endswith('.csv'))
            for length in [100, 200, 300]:
                with np.load(root/f'a/windows_{length}.npz') as shard:
                    self.assertEqual(shard['X'].shape[1:], (length, 6))
                    self.assertEqual(shard['X'].dtype, np.float32)
                    self.assertTrue(np.isfinite(shard['X']).all())
            # Poison only held-out test features: selection must remain unchanged.
            from benchmark_univrfall import benchmark
            benchmark(root/'a')
            for length in [100,200,300]:
                test=pd.read_csv(root/f'b/window_index_{length}.csv').partition.eq('test').to_numpy()
                with np.load(root/f'b/windows_{length}.npz') as shard:
                    x,y=shard['X'].copy(),shard['y'].copy()
                x[test]=100000
                np.savez_compressed(root/f'b/windows_{length}.npz',X=x,y=y)
            benchmark(root/'b')
            self.assertEqual((root/'a/selection_lock.json').read_bytes(),
                             (root/'b/selection_lock.json').read_bytes())

    def test_benchmark_metrics_match_independent_event_contract(self):
        from benchmark_univrfall import event_metrics, features
        x = np.zeros((1,100,6));x[:,:,0]=3;x[:,:,1]=4
        f = features(x)
        self.assertEqual(f.shape,(1,40))
        self.assertEqual(f[0,6],5)
        index=pd.DataFrame({'recording_id':[0]*4+[1]*4,
                            'end_frame':[199,249,299,349]*2})
        recordings=[dict(trial_id='a',subject_id='s',activity_key='ADL14',event=None,rows=400),
                    dict(trial_id='b',subject_id='s',activity_key='F01',
                         event={'onset':236,'impact':319},rows=400)]
        metrics=event_metrics(index,[1,1,0,1,0,0,0,1],.5,recordings,200,details=True)
        self.assertEqual(metrics['false_alarms'],2)
        self.assertEqual(metrics['detected'],1)
        self.assertAlmostEqual(metrics['median_delay_nominal_s'],.3)


if __name__ == '__main__':
    unittest.main()
