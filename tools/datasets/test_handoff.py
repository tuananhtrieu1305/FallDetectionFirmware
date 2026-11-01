"""Contracts for the standalone hardware CSV handoff."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'handoff/fall_detection_pc'


class HandoffTest(unittest.TestCase):
    def load(self):
        self.assertTrue((PACKAGE / 'predict.py').exists(), 'Standalone predictor must exist')
        spec = importlib.util.spec_from_file_location('handoff_predict', PACKAGE / 'predict.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_feature_score_parity(self):
        p = self.load()
        from benchmark_univrfall import features
        from select_baseline import portable_predict
        x = np.random.default_rng(4).normal(size=(12, 100, 6))
        model = json.loads((ROOT / 'reports/baseline_selection/selected_model.json').read_text())
        np.testing.assert_allclose(p.features(x), features(x), rtol=0, atol=1e-12)
        np.testing.assert_allclose(p.score(model, p.features(x)), portable_predict(model, features(x)), rtol=0, atol=1e-12)
        self.assertEqual(json.loads((PACKAGE / 'model.json').read_text()), model)
        self.assertEqual(p.sha(PACKAGE / 'model.json'), json.loads((PACKAGE / 'manifest.json').read_text())['model_sha256'])

    def test_alarm_edges(self):
        p = self.load()
        self.assertEqual(p.alarm_edges([.5, .5, .1, .5], .5).tolist(), [True, False, False, True])

    def test_sample_cli(self):
        self.load()
        with tempfile.TemporaryDirectory() as td:
            run = subprocess.run([sys.executable, str(PACKAGE / 'predict.py'), '--input', str(ROOT / 'docs/sensor_sample_4000.csv'), '--output', td], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            s = json.loads((Path(td) / 'summary.json').read_text())
            self.assertEqual(s['windows'], 79)
            self.assertNotIn('accuracy', s)
            for name in ['predictions.csv', 'alarms.csv', 'plot.png']:
                self.assertTrue((Path(td) / name).exists())

    def test_validation_and_gap(self):
        p = self.load()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'input.csv'
            def write(times, seq=None, bad=False):
                import csv
                with path.open('w', newline='') as f:
                    w = csv.writer(f)
                    w.writerow(['timestamp_us','ax','ay','az','gx','gy','gz'] + (['seq'] if seq is not None else []))
                    for i, t in enumerate(times):
                        w.writerow([t, 'nan' if bad else 0, 0, 9.8, 0, 0, 0] + ([seq[i]] if seq is not None else []))
            times = np.arange(200) * 10000
            write(times)
            self.assertEqual(len(p.read_input(path)[0]), 200)
            write(times[:99])
            result = p.run(path, Path(td) / 'short')
            self.assertEqual(result['windows'], 0)
            write(times, bad=True)
            with self.assertRaises(ValueError): p.read_input(path)

            write([0, 0])
            with self.assertRaises(ValueError): p.read_input(path)
            write(np.arange(200) * 20000)
            with self.assertRaises(ValueError): p.read_input(path)
            write(times, np.r_[np.arange(100), np.arange(101,201)])
            result = p.run(path, Path(td) / 'gap')
            self.assertEqual(result['windows'], 2)
            self.assertEqual(result['segments'], 2)
            times[100:] += 10000
            write(times)
            self.assertEqual(p.run(path, Path(td) / 'timegap')['segments'], 2)
            path.write_text('ax,ay\n1,2\n')
            with self.assertRaises(ValueError): p.read_input(path)

    def test_package_allowlist_and_integrity(self):
        p = self.load()
        spec = importlib.util.spec_from_file_location('handoff_package', PACKAGE / 'package.py')
        pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pack)
        import shutil
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in pack.FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PACKAGE / name, target)
            with patch.object(pack, 'HERE', root):
                archive = pack.build()
                with zipfile.ZipFile(archive) as z:
                    self.assertEqual(set(z.namelist()), {'fall_detection_pc/' + n for n in pack.FILES})
                (root / 'model.json').write_text('{}')
                with patch.object(p, 'HERE', root):
                    with self.assertRaisesRegex(ValueError, 'checksum'):
                        p.run(ROOT / 'docs/sensor_sample_4000.csv', root / 'out')
                (root / 'model.json').unlink()
                with self.assertRaises(FileNotFoundError): pack.build()

    def test_reset_and_cli_errors(self):
        p = self.load()
        with tempfile.TemporaryDirectory() as td:
            import csv
            root = Path(td)
            path = root / 'input.csv'
            with path.open('w', newline='') as stream:
                w = csv.writer(stream)
                w.writerow(['timestamp_us'] + p.CHANNELS + ['seq'])
                for i in range(250):
                    w.writerow([i*10000, 0,0,9.8,0,0,0, i if i < 150 else i+1])
            with patch.object(p, 'score', side_effect=lambda m, f: np.ones(len(f))):
                result = p.run(path, root / 'out')
                self.assertEqual(result['alarms'], 2)
                self.assertEqual(result['windows'], 3)
            with patch.object(sys, 'argv', ['predict.py','--input',str(path),'--output',str(root / 'cli')]):
                self.assertEqual(p.main(), 0)
            path.write_text('timestamp_us,ax,ay,az,gx,gy,gz\n')
            with self.assertRaisesRegex(ValueError, 'no samples'): p.read_input(path)
            path.write_text('timestamp_us,ax,ay,az,gx,gy,gz\n0,no,0,0,0,0,0\n')
            with self.assertRaisesRegex(ValueError, 'numeric'): p.read_input(path)
            path.write_text('timestamp_us,ax,ay,az,gx,gy,gz,ax\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate'): p.read_input(path)
            with patch.object(sys, 'argv', ['predict.py','--input',str(path),'--output',str(root)]):
                self.assertEqual(p.main(), 2)
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                p.run(root / 'predictions.csv', root)



if __name__ == '__main__':
    unittest.main()
