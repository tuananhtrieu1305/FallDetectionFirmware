"""Independent acceptance checks for the frozen result-analysis handoff."""
import ast
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from run_metrics_v11 import sha, dump


def verify(out=Path('reports/baseline_analysis'), baseline=Path('reports/baseline_selection')):
    load = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    v = load(out/'verification.json')
    assert v['status']=='PASS' and all(r['status']=='PASS' for r in v['requirements'])
    assert v['source_code_sha256']==sha('tools/datasets/analyze_baseline_results.py')
    for path,digest in v['input_hashes'].items(): assert sha(path)==digest, path
    for path,digest in v['output_hashes'].items(): assert sha(out/path)==digest, path
    source = Path(load('data/processed/univrfall_v1/manifest.json')['source'])
    records = load(source/'recording_manifest.json')
    index = pd.read_csv(baseline/'oof_predictions.csv',float_precision='round_trip')
    threshold = load(baseline/'selection_lock.json')['threshold']
    errors = pd.read_csv(out/'error_cases.csv',float_precision='round_trip')
    assert len(errors)==8
    assert set(errors.trial_id)==set(pd.read_csv(baseline/'selected_oof_errors.csv').trial_id)
    independent = {}
    for row in errors.itertuples():
        windows = index[index.trial_id.eq(row.trial_id)]
        record = records[int(windows.recording_id.iloc[0])]
        positive = windows['lr_C0.1'].to_numpy()>=threshold
        starts = [int(windows.end_frame.iloc[k]) for k in range(len(windows))
                  if positive[k] and (k==0 or not positive[k-1])]
        assert starts==ast.literal_eval(row.alarm_frames)
        assert np.isclose(windows['lr_C0.1'].max(),row.max_score_all,rtol=0,atol=1e-15)
        if record['event']:
            event = record['event']
            interval = windows.end_frame.between(event['onset'],event['impact']+100)
            assert interval.any()
            maximum = float(windows.loc[interval,'lr_C0.1'].max())
            assert maximum<threshold
            assert np.isclose(maximum,row.max_score_detection_interval,atol=1e-15,rtol=0)
        else:
            assert starts==[949]
        comparator = records[int(index.loc[index.trial_id.eq(row.comparator_trial),'recording_id'].iloc[0])]
        assert record['subject_id']!=comparator['subject_id']
        assert record['activity_key']==comparator['activity_key']
        independent[row.trial_id] = dict(alarm_frames=starts,max_score=float(windows['lr_C0.1'].max()),status='PASS')
    selected = load(baseline/'cache/lr_C0.1_metrics.json')
    full = load(baseline/'cache/lr_C1.0_metrics.json')
    ablation = load(baseline/'sensor_ablation.json')
    outcomes = load(out/'sensor_comparison.json')
    for sensor,m in ablation.items():
        for name,ref in [('vs_full_C1',full),('vs_selected_C01',selected)]:
            reference_hit = {t['trial_id'] for t in ref['per_trial'] if t['events'] and t['detected']}
            other_hit = {t['trial_id'] for t in m['per_trial'] if t['events'] and t['detected']}
            assert set(outcomes[sensor][name]['rescued_trials'])==other_hit-reference_hit
            assert set(outcomes[sensor][name]['lost_trials'])==reference_hit-other_hit
    metrics = selected['window_metrics']
    tn,fp = metrics['confusion_matrix'][0]; fn,tp = metrics['confusion_matrix'][1]
    assert np.isclose(metrics['precision'],tp/(tp+fp))
    assert np.isclose(metrics['recall'],tp/(tp+fn))
    assert np.isclose(metrics['f1'],2*tp/(2*tp+fp+fn))
    trade = pd.read_csv(out/'threshold_tradeoff.csv',float_precision='round_trip')
    assert float(trade.loc[trade.budget.eq(1),'threshold'].iloc[0])==threshold
    field = load(baseline/'onfield/summary.json')
    files = pd.read_csv(out/'onfield_by_file.csv',float_precision='round_trip')
    assert len(files)==18 and files.alarms.sum()==30
    assert np.isclose(files.hours.sum(),field['hours'])
    assert int(files.loc[files.source_member.str.endswith('20241106_1000.csv'),'alarms'].iloc[0])==22
    assert not list(Path('data').rglob('nga_*.csv'))
    for doc in [out/'REPORT.md',out/'README.md']:
        text = doc.read_text(encoding='utf-8')
        assert all(line.rstrip()==line for line in text.splitlines())
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if not link.startswith(('http','#')): assert (doc.parent/link).is_file(),link
    test_log = (out/'tests.txt').read_text()
    assert 'Ran 45 tests' in test_log and '\nOK' in test_log
    coverage = load(out/'test_coverage.json'); assert coverage['totals']['percent_covered']>=80
    assert all(not d['vulns'] for d in load(out/'dependency_audit.json')['dependencies'])
    v.update(independent_checks=dict(error_case_scores_and_alarm_edges=independent,
        ablation_rescue_loss_sets='PASS',precision_recall_F1_recomputed_from_confusion_matrix='PASS',
        unchanged_selected_threshold='PASS',onfield_all18_counts_exposure_concentration='PASS',
        local_report_links='PASS',labeled_hardware_fall_clips_found=0),
        tests=dict(count=45,status='PASS',coverage_percent=coverage['totals']['percent_covered'],
                   no_fit_guard='Real-result integration patches all three estimator fit methods and select_threshold',
                   test_log_sha256=sha(out/'tests.txt'),coverage_sha256=sha(out/'test_coverage.json')),
        verifier_code_sha256=sha(__file__),dependency_audit_sha256=sha(out/'dependency_audit.json'))
    v['output_hashes'] = {str(p.relative_to(out)):sha(p) for p in out.rglob('*')
                          if p.is_file() and p.name!='verification.json'}
    dump(out/'verification.json',v)
    return v


if __name__=='__main__':
    result = verify()
    print('PASS: full plan, all8 cases, sensor pairing, metrics, all18 field files, links, frozen inputs and45 tests.')
    print('Coverage:',result['tests']['coverage_percent'])
