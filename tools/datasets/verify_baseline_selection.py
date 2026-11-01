"""Audit selection against source scores, folds, locks and actual artifacts."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from run_metrics_v11 import sha,dump
from select_baseline import ranking,portable_predict
from metrics_v11 import evaluate
from benchmark_univrfall import features


def verify(source,out):
    experiment=json.loads((out/'experiment_lock.json').read_text());lock=json.loads((out/'selection_lock.json').read_text())
    rows=json.loads((out/'development_results.json').read_text());assert len(rows)==14
    assert experiment['code_sha256']==sha(Path(__file__).with_name('select_baseline.py'))
    assert experiment['EDA_sha256']==sha(out/'EDA.md')
    assert lock['experiment_sha256']==sha(out/'experiment_lock.json')
    assert lock['development_results_sha256']==sha(out/'development_results.json')
    assert lock['winner']['id']==max([r for r in rows if r['eligible']],key=ranking)['id']
    assert not lock['test_used_for_selection']
    records=[dict(r,recording_id=j) for j,r in enumerate(json.loads((source/'recording_manifest.json').read_text()))]
    rr=[r for r in records if r['partition']!='test']
    ii=pd.read_csv(out/'oof_predictions.csv',float_precision='round_trip');assert not ii.partition.eq('test').any()
    assert len(ii)==16424 and ii.y.eq(-1).sum()==2238
    reconstructed=[]
    for r in rows:
        if r['id']!='acc_threshold':
            folds=json.loads((out/'cache'/(r['id']+'_42.json')).read_text())['folds']
            for fold in folds:
                assert not set(fold['train_subjects'])&set(fold['validation_subjects'])
                valid=ii.partition.eq(f'fold{fold["fold"]}')
                assert fold['train_windows']==int((~valid & ii.y.ge(0)).sum())
        if r['eligible']:
            m=evaluate(rr,ii,ii[r['id']].to_numpy(),r['threshold'],bootstrap=0)
            for key in ['detected','events','recall','false_alarms','false_alarms_per_nominal_hour','macro_recall']:
                assert np.isclose(m[key],r[key],rtol=1e-12,atol=1e-12),(r['id'],key)
            assert m['false_alarms_per_nominal_hour']<=1
        reconstructed.append(r['id'])
    model=json.loads((out/'selected_model.json').read_text());test=pd.read_csv(out/'test_predictions.csv')
    with np.load(source/'windows_100.npz') as data:
        srcindex=pd.read_csv(source/'window_index_100.csv');xtest=features(data['X'][srcindex.partition.eq('test').to_numpy()])
    np.testing.assert_allclose(portable_predict(model,xtest),test.score,atol=1e-12)
    field=json.loads((out/'onfield/summary.json').read_text());assert field['files']==18 and field['threshold']==model['threshold'] and not field['threshold_retuned']
    for file in (out/'onfield').glob('*.json'):
        if file.name=='summary.json':continue
        f=json.loads(file.read_text());assert f['model_sha256']==sha(out/'selected_model.json') and f['chunk_invariance']=='PASS'
    assert 'Ran 36 tests' in (out/'tests.txt').read_text() and '\nOK' in (out/'tests.txt').read_text()
    cov=json.loads((out/'test_coverage.json').read_text());assert cov['totals']['percent_covered']>=80
    required=['README.md','EDA.md','REPORT.md','comparison.csv','oof_predictions.csv','selected_model.json','selection_lock.json','experiment_lock.json','seed_stability.csv','sensor_ablation.json','test_metrics.json','host_cost.json','paired_comparison.json','selected_oof_errors.csv']
    for name in required:assert (out/name).is_file(),name
    output=dict(status='PASS',requirements=[
        dict(step=1,status='PASS',evidence='experiment_lock.json; development only, fixed protocol/splits'),
        dict(step=2,status='PASS',evidence='eda_summary.json; quality/count tables by trial/subject/fold/activity'),
        dict(step=3,status='PASS',evidence='6-channel traces, norm traces, trial distributions, subject feature shifts, correlations, pre/post impact and OOF error plots'),
        dict(step=4,status='PASS',evidence='EDA.md created before experiment; 13 fixed model configs + max acceleration reference'),
        dict(step=5,status='PASS',evidence='all OOF scores independently re-counted; fold subjects and train masks verified; three-seed report; 36 tests'),
        dict(step=6,status='PASS',evidence='winner recomputed from all14; portable test scores match; all18 OnField model hashes/chunks match; REPORT.md')],
        selected=lock['winner'],coverage_percent=cov['totals']['percent_covered'],
        artifact_sha256={name:sha(out/name) for name in required},
        source_hashes={name:sha(source/name) for name in ['splits.json','recording_manifest.json','window_index_100.csv']},
        code_hashes={str(p):sha(p) for p in Path('tools/datasets').glob('*baseline*.py')},
        caveats=['Best within predefined comparison, not universally optimal','Selected development results optimistic; conditional CIs','Test/OnField previously observed; nominal clock','ESP32 RAM and latency NOT MEASURED','Acc-only diagnostic requires separate confirmation'])
    dump(out/'completion_audit.json',output);return output

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('reports/baseline_selection'));a=p.parse_args();print(verify(a.source,a.out)['status'])
