"""Explain frozen baseline results. Never fit models or update selection locks.

All development diagnostics use saved OOF scores, including IGNORE windows.
Test and field results are summarized only, never used for redesign/selection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import chi2

from metrics_v11 import evaluate, _rank
from run_metrics_v11 import dump, sha


def diagnose_trial(ends, scores, threshold, event):
    ends, scores = np.asarray(ends, dtype=int), np.asarray(scores, dtype=float)
    if scores.shape != ends.shape or not np.isfinite(scores).all():
        raise ValueError('Invalid scores')
    if len(ends) > 1 and not (np.diff(ends) > 0).all():
        raise ValueError('Unordered window ends')
    positive = scores >= threshold
    starts = ends[positive & ~np.r_[False, positive[:-1]]] if len(ends) else np.array([], int)
    result = dict(alarm_frames=starts.tolist(), max_score_all=float(scores.max()) if len(scores) else None,
                  first_matching_alarm_frame=None, delay_nominal_s=None)
    if event is None:
        result.update(diagnosis='adl_false_alarm' if len(starts) else 'adl_correct',
                      max_score_detection_interval=None, threshold_margin=None)
        return result
    onset, deadline = event['onset'], event['impact'] + 100
    interval = (ends >= onset) & (ends <= deadline)
    matching = starts[(starts >= onset) & (starts <= deadline)]
    maximum = float(scores[interval].max()) if interval.any() else None
    if len(matching):
        reason = 'detected'
        result.update(first_matching_alarm_frame=int(matching[0]),
                      delay_nominal_s=float((matching[0]-event['impact'])/100))
    elif not interval.any():
        reason = 'no_window_in_detection_interval'
    elif positive[interval].any():
        reason = 'already_positive_before_onset'
    elif (starts > deadline).any():
        reason = 'late_only'
    else:
        reason = 'no_crossing_in_detection_interval'
    result.update(diagnosis=reason, max_score_detection_interval=maximum,
                  threshold_margin=maximum-threshold if maximum is not None else None)
    return result


def paired_events(reference, challenger, resamples=10000):
    def keyed(rows):
        result = {}
        for row in rows:
            if not row['events']:
                continue
            if row['trial_id'] in result:
                raise ValueError('Duplicate event')
            result[row['trial_id']] = row
        return result
    ref, other = keyed(reference), keyed(challenger)
    if ref.keys() != other.keys() or any(ref[t]['subject_id'] != other[t]['subject_id'] for t in ref):
        raise ValueError('Different event population')
    rescued = sorted(t for t in ref if not ref[t]['detected'] and other[t]['detected'])
    lost = sorted(t for t in ref if ref[t]['detected'] and not other[t]['detected'])
    people = sorted({r['subject_id'] for r in ref.values()})
    counts = np.array([[sum(r['subject_id']==s for r in ref.values()),
                        sum(other[t]['detected']-ref[t]['detected'] for t in ref if ref[t]['subject_id']==s)]
                       for s in people])
    ci = None
    if people and resamples:
        rng = np.random.default_rng(42)
        total = counts[rng.integers(len(people), size=(resamples, len(people)))].sum(axis=1)
        ci = np.percentile(total[:, 1]/total[:, 0], [2.5, 97.5]).tolist()
    return dict(events=len(ref), rescued_trials=rescued, lost_trials=lost,
                delta_detected=len(rescued)-len(lost), delta_recall=(len(rescued)-len(lost))/len(ref) if ref else None,
                paired_subject_bootstrap_95=ci,
                limitation='Conditional OOF predictions; includes development selection optimism, not causal/independent confirmation')


def choose_comparator(record, records, correct):
    candidates = [r for r in records if r['subject_id'] != record['subject_id'] and
                  r['activity_key'] == record['activity_key'] and correct.get(r['trial_id'], 0)]
    return min(candidates, key=lambda r: r['trial_id']) if candidates else None


def metric_row(name, m):
    w = m.get('window_metrics', {})
    return dict(dataset=name, events=m.get('events'), detected=m.get('detected'), missed=m.get('missed'),
                event_recall=m.get('recall'), macro_recall=m.get('macro_recall'),
                window_precision=w.get('precision'), window_recall=w.get('recall'), window_f1=w.get('f1'),
                window_AP=w.get('average_precision'), window_fall_fraction=w.get('fall_fraction'),
                false_alarms=m.get('false_alarms'), adl_hours=m.get('adl_monitored_nominal_hours'),
                fa_per_hour=m.get('false_alarms_per_nominal_hour'),
                delay_median_nominal_s=m.get('median_delay_nominal_s'), delay_p95_nominal_s=m.get('p95_delay_nominal_s'),
                recall_at_0_5s=m.get('recall_at_0_5s'), alarm_active_fraction=m.get('alarm_active_fraction'),
                early=m.get('early_fall_trial_alarms'), late=m.get('late_fall_trial_alarms'),
                repeats=m.get('extra_alarms_in_detection_interval'),
                recall_bootstrap_95=m.get('bootstrap_95', {}).get('recall'),
                fa_bootstrap_95=m.get('bootstrap_95', {}).get('fa_per_hour'),
                event_binomial_95=m.get('event_binomial_95'), fa_poisson_upper95=m.get('poisson_upper_95_per_hour'))


def case_figure(record, comparator, source, index, threshold, destination):
    fig, axes = plt.subplots(8, 2, figsize=(15, 15), sharex='col')
    for col, r in enumerate([record, comparator]):
        if r is None:
            for ax in axes[:, col]: ax.set_visible(False)
            continue
        with np.load(source/r['recording']) as data:
            values, frames = data['values'], data['frame']
        wi = index[index.recording_id.eq(r['recording_id'])]
        for k in range(6):
            axes[k, col].plot(frames, values[:, k], lw=.7)
            axes[k, col].set_ylabel(['ax', 'ay', 'az', 'gx', 'gy', 'gz'][k]+(' m/s2' if k<3 else ' rad/s'))
        ax = axes[6, col]
        ax.plot(frames, np.linalg.norm(values[:, :3], axis=1), label='acc norm m/s2')
        ax.plot(frames, np.linalg.norm(values[:, 3:], axis=1), label='gyro norm rad/s')
        ax.legend(fontsize=6)
        ax = axes[7, col]
        ax.step(wi.end_frame, wi['lr_C0.1'], where='post', label='saved OOF score')
        ax.scatter(wi.loc[wi.y.eq(-1), 'end_frame'], wi.loc[wi.y.eq(-1), 'lr_C0.1'],
                   s=14, c='grey', marker='x', label='IGNORE')
        ax.axhline(threshold, c='purple', ls='--', label='frozen threshold')
        ax.set_ylim(-.03, 1.03); ax.set_xlabel('source frame (100 Hz nominal)'); ax.legend(fontsize=6)
        for axis in axes[:, col]:
            if r['event']:
                for frame, color in [(r['event']['onset'], 'orange'), (r['event']['impact'], 'red'),
                                     (r['event']['impact']+100, 'green')]:
                    axis.axvline(frame, c=color, lw=.8)
            else:
                diag = diagnose_trial(wi.end_frame, wi['lr_C0.1'], threshold, None)
                for frame in diag['alarm_frames']: axis.axvline(frame, c='purple', lw=.8)
        axes[0, col].set_title(('Error' if col==0 else 'Correct, other person')+' '+r['trial_id']+' '+r['activity_key'])
    fig.suptitle('Orange=onset, red=impact, green=deadline. Columns are separate trials; raw plots are not axis calibration.')
    fig.tight_layout(rect=[0, 0, 1, .97]); fig.savefig(destination, dpi=125); plt.close(fig)


def raw_case_summary(record, source):
    with np.load(source/record['recording']) as data:
        v, frames = data['values'], data['frame']
    event = record['event']
    if event:
        v = v[(frames >= event['onset']-100) & (frames <= event['impact']+100)]
    return dict(acc_norm_max_m_s2=float(np.linalg.norm(v[:, :3], axis=1).max()),
                gyro_norm_max_rad_s=float(np.linalg.norm(v[:, 3:], axis=1).max()))


def analyze(source, baseline, out):
    source, baseline, out = Path(source), Path(baseline), Path(out)
    out.mkdir(parents=True, exist_ok=True); figures = out/'figures'; figures.mkdir(exist_ok=True)
    # Snapshot every baseline artifact, including caches, to prove no writes/training.
    before = {str(p): sha(p) for p in baseline.rglob('*') if p.is_file()}
    source_inputs = [source/'recording_manifest.json', source/'splits.json',
                     Path('docs/sensor_sample_4000.csv'), Path('docs/sensor_sample_4000.metadata.json')]
    inputs = dict(before); inputs.update({str(p): sha(p) for p in source_inputs})
    load = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    lock = load(baseline/'selection_lock.json'); threshold = lock['threshold']
    if lock['winner']['id'] != 'lr_C0.1': raise ValueError('Expected the frozen LR C0.1 baseline')
    records = [dict(r, recording_id=j) for j, r in enumerate(load(source/'recording_manifest.json'))]
    devrecords = [r for r in records if r['partition'] != 'test']
    index = pd.read_csv(baseline/'oof_predictions.csv', float_precision='round_trip')
    if index.partition.eq('test').any(): raise ValueError('Test score in development diagnostics')
    configurations = load(baseline/'development_results.json')
    models = {}; counts_verified = []
    for config in configurations:
        name = config['id']
        cached = baseline/'cache'/f'{name}_42.npz'
        if cached.exists():
            with np.load(cached) as data: np.testing.assert_array_equal(data['score'], index[name].to_numpy())
        if not config['eligible']: continue
        # Re-count at the original frozen threshold only. No threshold search.
        m = evaluate(devrecords, index, index[name], config['threshold'])
        for k in ['events', 'detected', 'false_alarms', 'recall', 'macro_recall', 'p95_delay_nominal_s']:
            assert np.isclose(m[k], config[k], rtol=1e-12, atol=1e-12), (name, k)
        assert m['window_metrics'] == config['window_metrics'], name
        models[name] = m; counts_verified.append(name)
    selected = models['lr_C0.1']; trials = selected['per_trial']
    test = load(baseline/'test_metrics.json'); field = load(baseline/'onfield/summary.json')
    rows = [metric_row('development OOF', selected), metric_row('fixed test', test)]
    field_upper = float(chi2.ppf(.95, 2*(field['alarms']+1))/2/field['hours'])
    rows.append(dict(dataset='OnField source-negative', events=None, event_recall=None,
                     window_precision=None, false_alarms=field['alarms'], adl_hours=field['hours'],
                     fa_per_hour=field['alarms_per_source_negative_hour'], fa_poisson_upper95=field_upper,
                     alarm_active_fraction=field['active_fraction']))
    pd.DataFrame(rows).to_csv(out/'metric_summary.csv', index=False)
    dump(out/'metric_summary.json', rows)
    by_subject = pd.DataFrame.from_dict(selected['by_subject_id'], orient='index').rename_axis('subject_id').reset_index()
    by_subject['share_of_all_misses'] = by_subject.missed / selected['missed']
    by_subject.to_csv(out/'by_subject.csv', index=False)
    pd.DataFrame.from_dict(selected['by_activity_key'], orient='index').to_csv(out/'by_activity.csv')
    correct = {r['trial_id']: r['detected'] if r['events'] else int(r['false_alarms']==0) for r in trials}
    errorids = {r['recording_id'] for r in trials if (r['events'] and not r['detected']) or r['false_alarms']}
    cases = []; all_windows = []; case_comparisons = []
    for record in devrecords:
        if record['recording_id'] not in errorids: continue
        wi = index[index.recording_id.eq(record['recording_id'])].copy()
        diag = diagnose_trial(wi.end_frame, wi['lr_C0.1'], threshold, record['event'])
        comparator = choose_comparator(record, devrecords, correct)
        for r in [record, comparator]:
            if r is not None:
                path = source/r['recording']
                inputs[str(path)] = sha(path)
        figure = 'figures/'+record['trial_id']+'.png'
        row = dict(trial_id=record['trial_id'], subject_id=record['subject_id'], activity=record['activity'],
                   activity_key=record['activity_key'], fold=record['partition'],
                   error_type='missed_fall' if record['event'] else 'false_alarm',
                   onset=record['event']['onset'] if record['event'] else None,
                   impact=record['event']['impact'] if record['event'] else None,
                   threshold=threshold, **diag, **raw_case_summary(record, source),
                   comparator_trial=comparator['trial_id'] if comparator else None, figure=figure,
                   evidence_level='direct observation from frozen OOF predictions',
                   hypothesis='Check feature/sensor contribution and subject shift; cause unconfirmed' if record['event'] else
                   'Chair activity shares a high-motion pattern with falls; cause unconfirmed')
        cases.append(row)
        for kind, r in [('error', record), ('correct_other_person', comparator)]:
            if r is None: continue
            windows = index[index.recording_id.eq(r['recording_id'])].copy()
            windows['role'] = kind; windows['error_trial'] = record['trial_id']
            windows['above_threshold'] = windows['lr_C0.1'] >= threshold
            all_windows.append(windows)
            d = diagnose_trial(windows.end_frame, windows['lr_C0.1'], threshold, r['event'])
            case_comparisons.append(dict(error_trial=record['trial_id'], role=kind, trial_id=r['trial_id'],
                                         subject_id=r['subject_id'], **d, **raw_case_summary(r, source)))
        case_figure(record, comparator, source, index, threshold, out/figure)
    assert len(cases)==8 and sum(r['error_type']=='missed_fall' for r in cases)==7
    pd.DataFrame(cases).to_csv(out/'error_cases.csv', index=False)
    pd.concat(all_windows).to_csv(out/'case_windows.csv', index=False)
    pd.DataFrame(case_comparisons).to_csv(out/'case_comparisons.csv', index=False)
    pairs = {}; comparison = []
    for config in configurations:
        name = config['id']
        if name not in models:
            comparison.append(dict(model=name, eligible=False, reason='No detecting threshold meets original FA budget'))
            continue
        m = models[name]; pair = paired_events(trials, m['per_trial']); pairs[name] = pair
        comparison.append(dict(model=name, eligible=True, **metric_row('development OOF', m),
                               rescued_vs_selected=len(pair['rescued_trials']), lost_vs_selected=len(pair['lost_trials']),
                               delta_recall_vs_selected=pair['delta_recall'], paired_95=pair['paired_subject_bootstrap_95']))
    pd.DataFrame(comparison).to_csv(out/'model_comparison.csv', index=False); dump(out/'model_pairs.json', pairs)
    for seed in [42, 43, 44]:
        with np.load(baseline/'cache'/f'lr_C0.1_{seed}.npz') as data:
            np.testing.assert_array_equal(data['score'], index['lr_C0.1'].to_numpy())
    stability = pd.read_csv(baseline/'seed_stability.csv', float_precision='round_trip')
    stability.to_csv(out/'seed_stability.csv', index=False)
    # Sensor ablation has event outcomes only. Never recreate missing scores by fitting.
    ablation = load(baseline/'sensor_ablation.json'); ablation_pairs = {}
    for sensor, m in ablation.items():
        ablation_pairs[sensor] = dict(metrics=metric_row(sensor+' C=1 OOF', m),
            vs_full_C1=paired_events(models['lr_C1.0']['per_trial'], m['per_trial']),
            vs_selected_C01=paired_events(trials, m['per_trial']),
            score_and_fold_weights_status='NOT SAVED: per-window attribution is not possible without new training, outside this task')
    dump(out/'sensor_comparison.json', ablation_pairs)
    sensor_trial_rows = []
    lookups = {key: {r['trial_id']: r for r in m['per_trial']} for key, m in ablation.items()}
    for row in trials:
        if not row['events']: continue
        sensor_trial_rows.append(dict(trial_id=row['trial_id'], subject_id=row['subject_id'], activity_key=row['activity_key'],
            selected_C01=row['detected'], full_C1=next(r['detected'] for r in models['lr_C1.0']['per_trial'] if r['trial_id']==row['trial_id']),
            acc_C1=lookups['acc_only'][row['trial_id']]['detected'], gyro_C1=lookups['gyro_only'][row['trial_id']]['detected']))
    pd.DataFrame(sensor_trial_rows).to_csv(out/'sensor_event_outcomes.csv', index=False)
    tradeoff = []
    curve = pd.read_csv(baseline/'cache/lr_C0.1_threshold_curve.csv', float_precision='round_trip')
    for budget in [.1, .25, .5, 1., 2.]:
        candidates = curve[(curve.false_alarms_per_nominal_hour<=budget) & curve.recall.gt(0)]
        if candidates.empty: tradeoff.append(dict(budget=budget, available=False)); continue
        candidates = candidates.where(pd.notna(candidates), None).to_dict('records')
        best = max(candidates, key=_rank)
        tradeoff.append(dict(budget=budget, available=True, **best))
    pd.DataFrame(tradeoff).to_csv(out/'threshold_tradeoff.csv', index=False)
    field_rows = pd.DataFrame(field['per_file']); field_rows['rate'] = field_rows.alarms/field_rows.hours
    field_rows['alarm_share'] = field_rows.alarms/field['alarms']; field_rows.to_csv(out/'onfield_by_file.csv', index=False)
    # Inspect the available hardware sample; unknown truth is never inferred from trigger.
    hwpath = Path('docs/sensor_sample_4000.csv'); hw = pd.read_csv(hwpath)
    meta = load(Path('docs/sensor_sample_4000.metadata.json')); dt = np.diff(hw.timestamp_us)
    six = hw[['ax','ay','az','gx','gy','gz']].to_numpy(); acc = np.linalg.norm(six[:, :3], axis=1)
    hardware = dict(file=str(hwpath), rows=len(hw), finite=bool(np.isfinite(six).all()),
                    dt_min_us=int(dt.min()), dt_max_us=int(dt.max()), dt_mean_us=float(dt.mean()),
                    observed_host_hz=float(1e6/dt.mean()), nonmonotonic_timestamp_count=int((dt<=0).sum()),
                    seq_gap_count=int((np.diff(hw.seq)!=1).sum()), acc_norm_median_m_s2=float(np.median(acc)),
                    gyro_norm_median_rad_s=float(np.median(np.linalg.norm(six[:,3:],axis=1))),
                    metadata=meta, timing_and_columns='compatible for inspection',
                    ground_truth='UNKNOWN: synthetic trigger is not a fall label',
                    mount='metadata says abdomen_waist; hardcoded, actual wear not verified',
                    axes='sensor_frame_unmapped; no established source-to-prototype rotation',
                    readiness='Not sufficient for labeled event/false-alarm evaluation',
                    missing=['Real activity labels and onset/impact or synchronized reference',
                             'Actual mount/orientation evidence', 'New normal-activity and event clips requested from hardware member'])
    dump(out/'hardware_readiness.json', hardware)
    make_overview(figures, by_subject, comparison, curve, tradeoff, field_rows)
    write_report(out, selected, test, field, field_upper, cases, comparison, pairs, ablation_pairs, hardware, tradeoff)
    (out/'README.md').write_text('''# Phân tích kết quả baseline đã có

**Đọc [REPORT.md](REPORT.md) để xem kết luận và bước ưu tiên tiếp theo.**

- [Metric theo window/sự kiện/thời gian](metric_summary.csv)
- [8 ca lỗi](error_cases.csv), [các window liên quan](case_windows.csv), [trial đúng để đối chiếu](case_comparisons.csv)
- [Theo người](by_subject.csv), [theo hoạt động](by_activity.csv)
- [So sánh model](model_comparison.csv), [danh sách sự kiện cứu/mất](model_pairs.json)
- [Acc-only/gyro-only](sensor_comparison.json), [kết quả từng sự kiện](sensor_event_outcomes.csv)
- [Đánh đổi threshold cũ](threshold_tradeoff.csv), [OnField từng file](onfield_by_file.csv)
- [Mức sẵn sàng dữ liệu phần cứng](hardware_readiness.json), [đối chiếu/hash](verification.json)

Chạy lại từ root repo:

```powershell
python tools/datasets/analyze_baseline_results.py
python -m unittest discover -s tools/datasets -p 'test_analyze_baseline_results.py'
```

Script lấy đường dẫn nguồn từ manifest dataset và chỉ đọc report/prediction đã lưu.
Không train lại, không đổi model/threshold. Metric chưa xác định ghi N/A/null.
CSV score phải đọc với float_precision=round_trip để giữ nguyên quyết định ở threshold trùng score.
Kiểm tra tích hợp chặn estimator.fit và chọn threshold mới; không dùng model23người để giải thích score OOF.
Các hình mỗi ca lỗi nằm trong figures; thời gian là danh nghĩa của nguồn.
''', encoding='utf-8')
    # Verify the requested scope and invariant from authoritative artifacts.
    assert before == {str(p): sha(p) for p in baseline.rglob('*') if p.is_file()}, 'Frozen baseline modified'
    for p, digest in inputs.items(): assert sha(p)==digest, p
    expected = ['REPORT.md','error_cases.csv','case_windows.csv','case_comparisons.csv','metric_summary.json',
                'model_pairs.json','sensor_comparison.json','threshold_tradeoff.csv','hardware_readiness.json']
    for name in expected: assert (out/name).is_file(), name
    for r in cases:
        if r['error_type']=='missed_fall':
            original = next(t for t in trials if t['trial_id']==r['trial_id'])
            assert not original['detected'] and r['diagnosis'] != 'detected'
        assert (out/r['figure']).is_file()
    verification = dict(status='PASS',scope='Analysis of existing results only; no fitting, threshold updates or firmware changes',
        input_hashes=inputs,original_baseline_artifacts_unchanged=True,counts_recomputed_for_models=counts_verified,
        development_errors_reviewed=len(cases),misses_reviewed=7,adl_false_alarms_reviewed=1,
        deterministic_comparator='same activity; other person; correct result; smallest trial ID',
        ablation_all_456_events_aligned=True,LR_all_three_seed_score_arrays_identical=True,
        test_errors_used_for_design=False,onfield_used_for_tuning=False,
        output_hashes={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='verification.json'},
        source_code_sha256=sha(__file__),
        requirements=[dict(section='A', status='PASS', evidence='metric_summary; frozen development counts recomputed; test/field summaries and CI'),
                      dict(section='B', status='PASS', evidence='all8 error_cases; saved OOF score margins; eight paired figures; by_subject denominators'),
                      dict(section='C', status='PASS', evidence='model_pairs; all456 aligned sensor_event_outcomes; same-C comparison; frozen threshold curve'),
                      dict(section='D', status='PASS', evidence='all18 field file counts/rates; hardware metadata/timing inspected; missing labels/mount recorded'),
                      dict(section='Decision', status='PASS', evidence='REPORT: one priority, two later steps, hypotheses/tests/retain-or-reject criteria')],
        limitations=['Ablation window scores/fold weights were not saved','No labeled prototype fall test available',
                     'Development results selected/tuned; CI conditional on frozen predictions','OnField labels/participant IDs unverified'])
    dump(out/'verification.json', verification)
    return dict(selected='lr_C0.1', errors=cases, ablation=ablation_pairs, hardware=hardware, status='PASS')


def make_overview(figures, by_subject, comparison, curve, tradeoff, field_rows):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].bar(by_subject.subject_id, by_subject.recall*100); axes[0].tick_params(axis='x',rotation=90)
    axes[0].set_ylabel('Event recall %'); axes[0].set_title('Development per person (counts in by_subject.csv)')
    axes[1].bar(by_subject.subject_id, by_subject.missed); axes[1].tick_params(axis='x',rotation=90)
    axes[1].set_ylabel('Missed events'); fig.tight_layout(); fig.savefig(figures/'subject_errors.png',dpi=130); plt.close(fig)
    valid = [r for r in comparison if r['eligible']]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.scatter([r['window_precision']*100 for r in valid], [r['event_recall']*100 for r in valid])
    for r in valid: ax.annotate(r['model'],(r['window_precision']*100,r['event_recall']*100),fontsize=7)
    ax.set_xlabel('Window precision %'); ax.set_ylabel('Event recall % (different unit)')
    ax.set_title('Two evaluation levels; do not combine into one F1'); fig.tight_layout();fig.savefig(figures/'precision_and_event_recall.png',dpi=130);plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(curve.false_alarms_per_nominal_hour, curve.recall*100,s=4,alpha=.25)
    for row in tradeoff:
        if row['available']: ax.scatter(row['false_alarms_per_nominal_hour'],row['recall']*100,label=f'budget {row["budget"]}/h')
    ax.set_xlim(-.05,2.1);ax.set_xlabel('Observed ADL alarm starts / nominal hour');ax.set_ylabel('Development event recall %')
    ax.set_title('Frozen LR C0.1 curve; descriptive operating points, no lock update');ax.legend();fig.tight_layout();fig.savefig(figures/'threshold_tradeoff.png',dpi=130);plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(14, 8),sharex=True)
    labels = [Path(s).stem for s in field_rows.source_member]
    axes[0].bar(labels,field_rows.alarms);axes[0].set_ylabel('Alarm count')
    axes[1].bar(labels,field_rows.rate);axes[1].set_ylabel('Alarms / source-negative h');axes[1].tick_params(axis='x',rotation=90)
    fig.tight_layout();fig.savefig(figures/'onfield_concentration.png',dpi=130);plt.close(fig)


def pct(v): return 'N/A' if v is None else f'{v*100:.2f}%'


def write_report(out, selected, test, field, field_upper, cases, comparison, pairs, ablation, hardware, tradeoff):
    acc = ablation['acc_only']; gyro = ablation['gyro_only']
    sa36 = selected['by_subject_id']['SA36']
    full1pair = pairs['lr_C1.0']
    lines = ['# Phân tích baseline và bước cần làm tiếp theo', '',
        '**Ưu tiên tiếp theo: nhận bộ test phần cứng nhỏ có ghi nhãn, kiểm tra đơn vị/clock/hướng gắn rồi chạy baseline đã khóa.** Giữ LR C=0,1 +40 đặc trưng và ngưỡng hiện tại cho lần thử đầu. Chưa có dữ liệu đủ nhãn để xác nhận model hoạt động trên prototype; chưa có căn cứ bắt buộc chuyển sang CNN.', '',
        '## 1. Kết quả đủ tốt ở đâu, chưa chứng minh được gì?', '',
        '| Metric | Development OOF, 23 người | Test cố định, 6 người |',
        '|---|---:|---:|']
    for label,key in [('Event recall','recall'),('Macro event recall','macro_recall'),('Recall trước/đến impact+0,5s','recall_at_0_5s')]:
        lines.append(f'| {label} | {pct(selected[key])} | {pct(test[key])} |')
    for label,key in [('Window precision','precision'),('Window recall','recall'),('Window F1','f1'),('Window AP','average_precision')]:
        lines.append(f'| {label} | {pct(selected["window_metrics"][key])} | {pct(test["window_metrics"][key])} |')
    lines += [f'| Phát hiện / tổng ngã | {selected["detected"]}/{selected["events"]} | {test["detected"]}/{test["events"]} |',
              f'| Cảnh báo nhầm / giờ ADL theo dõi | {selected["false_alarms"]}/{selected["adl_monitored_nominal_hours"]:.4f} | {test["false_alarms"]}/{test["adl_monitored_nominal_hours"]:.4f} |',
              f'| FA/h | {selected["false_alarms_per_nominal_hour"]:.3f} | {test["false_alarms_per_nominal_hour"]:.3f} |',
              f'| Trễ median / P95, giây danh nghĩa | {selected["median_delay_nominal_s"]:.3f}/{selected["p95_delay_nominal_s"]:.3f} | {test["median_delay_nominal_s"]:.3f}/{test["p95_delay_nominal_s"]:.3f} |', '',
              'Metric window chỉ dùng nhãn0/1; window IGNORE vẫn được suy luận để đếm cảnh báo liên tục. Precision window cao không có nghĩa cùng tỷ lệ cảnh báo đúng ở đời thực; prevalence ngã và số giờ bình thường khác nhau. Không ghép window precision với event recall để tính F1.', '',
              f'Recall bootstrap theo người95% development: {selected["bootstrap_95"]["recall"]}; FA/h: {selected["bootstrap_95"]["fa_per_hour"]}. Cận trên Poisson một phía95%: development {selected["poisson_upper_95_per_hour"]:.3f}/h, test {test["poisson_upper_95_per_hour"]:.3f}/h. 0FA trong khoảng23,4 phút test chưa chứng minh rate≤1/h. Bootstrap test suy biến khi không có lỗi không chứng minh độ chắc chắn tuyệt đối.', '',
              'Chỉ có khoảng1,52 giờ ADL development nên bước nhảy một cảnh báo đã là0,658/h. Các điểm tại0,1/0,25/0,5/h có thể cùng cho0FA quan sát; không phải đã chứng minh đạt các mức đó. Các window chồng lấn không độc lập. Thời gian laboratory là clock100Hz danh nghĩa, chưa phải độ trễ thực trên thiết bị. Test đã từng được xem: đây là benchmark cố định, không phải xác nhận mới hoàn toàn.', '',
              '## 2. Rà toàn bộ 7 lần bỏ sót và 1 báo nhầm', '',
              '| Trial | Người / hoạt động | Chẩn đoán từ score OOF | Max score trong khoảng phát hiện | Chênh score−ngưỡng | Trial đúng đối chiếu |',
              '|---|---|---|---:|---:|---|']
    for c in cases:
        maximum = 'N/A' if c['max_score_detection_interval'] is None else f'{c["max_score_detection_interval"]:.6f}'
        margin = 'N/A' if c['threshold_margin'] is None else f'{c["threshold_margin"]:.6f}'
        lines.append(f'| [{c["trial_id"]}]({c["figure"]}) | {c["subject_id"]} / {c["activity_key"]} | {c["diagnosis"]} | {maximum} | {margin} | {c["comparator_trial"]} |')
    reasons = pd.Series([c['diagnosis'] for c in cases]).value_counts().to_dict()
    lines += ['',f'Ngưỡng giữ nguyên: {selected["threshold"]:.17g}. Đếm chẩn đoán: {reasons}. Max score tính trên tất cả window kết thúc trong [onset, impact+100], bao gồm IGNORE; không chỉ các window FALL dùng cho loss.',
        'Cả7 lần bỏ sót đều không có score vượt threshold trong khoảng hợp lệ, không phải lỗi cảnh báo trễ. S31T33R01 chỉ cách ngưỡng khoảng0,000795, S36T32R01 khoảng0,002682; S36T21R01 thấp hơn nhiều (max score≈0,249). Việc một số ca gần ngưỡng không đủ lý do hạ ngưỡng theo từng ca; phải xét đánh đổi báo nhầm trên toàn development. Score chưa phải xác suất đã hiệu chuẩn.',
        f'SA36: bỏ sót {sa36["missed"]}/{sa36["events"]} lần ngã, recall {pct(sa36["recall"])}; chiếm4/7 lỗi toàn bộ. Đây là tập trung lỗi theo người, chưa chứng minh do hướng gắn, nhãn hoặc gyro. Cần phân biệt tỷ lệ lỗi của người đó với số lỗi tuyệt đối. Xem [bảng theo người](by_subject.csv).',
        'Cảnh báo nhầm duy nhất: S22T15R01, ADL15 (collapse into chair), cạnh cảnh báo tại frame949, max score0,987973 so với threshold0,984773. Các lỗi và trial đúng được vẽ đủ sáu kênh, norm và score theo frame; trial đối chiếu là cùng hoạt động, người khác, kết quả đúng, chọn trial ID nhỏ nhất để tránh cherry-pick. Một trial đúng chỉ là minh họa, không đại diện mọi người.',
        'Đồ thị giải thích trực tiếp vị trí score dưới/vượt ngưỡng và thời điểm cảnh báo. Hai trial có thể thuộc hai fold với model train khác nhau; đối chiếu là mô tả, không phải kiểm chứng cô lập tác động của người. Khác biệt tín hiệu giữa hai người chỉ tạo giả thuyết. Không tự sửa annotation hoặc suy ra tư thế/chấn động cụ thể từ IMU; chưa có video để xác minh nguyên nhân. Không có trọng số model từng fold được lưu nên không thể phân rã đóng góp feature OOF; model fit23 người không được dùng thay model OOF để giải thích lỗi.', '',
        '## 3. Model phức tạp hơn và acc-only có giúp không?', '',
        '| Model, tại threshold đã khóa của nó | Event recall | Window P/R/F1 | Cứu / mất so với LR C0,1 |',
        '|---|---:|---|---:|']
    for row in comparison:
        if not row['eligible']:
            lines.append(f'| {row["model"]} | Không có điểm phát hiện ngã đạt ngân sách1FA/h | N/A tại điểm hợp lệ | N/A |')
        else:
            lines.append(f'| {row["model"]} | {pct(row["event_recall"])} | {pct(row["window_precision"])} / {pct(row["window_recall"])} / {pct(row["window_f1"])} | {row["rescued_vs_selected"]} / {row["lost_vs_selected"]} |')
    lines += ['',f'Chênh LR C0,1 so với C1: {-full1pair["delta_recall"]*100:.2f} điểm phần trăm. Khoảng chênh C1−C0,1 theo bootstrap người: {full1pair["paired_subject_bootstrap_95"]}. Khoảng còn chạm0 nên chưa khẳng định vượt trội chắc chắn. Đây là so sánh đã lựa chọn trên development, CI chỉ có điều kiện trên prediction cố định.',
        'Ví dụ trade-off giữa model: RF depth10/leaf10 cứu4 ca baseline bỏ sót nhưng mất14 ca baseline phát hiện được, nên net−10; cây depth8/leaf30 cứu4 nhưng mất25. Chỉ nhìn các ca được cứu sẽ đánh giá sai lợi ích. Danh sách ghép cặp đầy đủ nằm trong model_pairs.json.',
        'LR C0,1 có score OOF giống hệt ở seed42/43/44. Điều đó phù hợp độ xác định của solver/cấu hình; không chứng minh ổn định giữa người hoặc miền dữ liệu. Tree có seed không đạt điểm vận hành, forest có recall kém hơn trong grid hiện tại. Không kết luận mọi loại cây/forest hoặc model sâu đều kém.', '',
        '**Ablation phải so cùng C trước:**', '',
        '| Cấu hình chẩn đoán | Phát hiện /456 | Window P / R / F1 | FA / giờ ADL |',
        '|---|---:|---|---:|',
        f'| Acc-only C1 | {int(acc["metrics"]["detected"])}/456 | {pct(acc["metrics"]["window_precision"])} / {pct(acc["metrics"]["window_recall"])} / {pct(acc["metrics"]["window_f1"])} | {int(acc["metrics"]["false_alarms"])}/{acc["metrics"]["adl_hours"]:.4f} |',
        f'| Gyro-only C1 | {int(gyro["metrics"]["detected"])}/456 | {pct(gyro["metrics"]["window_precision"])} / {pct(gyro["metrics"]["window_recall"])} / {pct(gyro["metrics"]["window_f1"])} | {int(gyro["metrics"]["false_alarms"])}/{gyro["metrics"]["adl_hours"]:.4f} |', '',
        f'- Acc-only C1 vs full6channel C1: cứu {len(acc["vs_full_C1"]["rescued_trials"])} sự kiện, mất {len(acc["vs_full_C1"]["lost_trials"])} sự kiện, net {acc["vs_full_C1"]["delta_detected"]}; paired95% chênh recall {acc["vs_full_C1"]["paired_subject_bootstrap_95"]}.',
        f'- Acc-only C1 vs baseline C0,1: cứu {len(acc["vs_selected_C01"]["rescued_trials"])} sự kiện, mất {len(acc["vs_selected_C01"]["lost_trials"])} sự kiện, net {acc["vs_selected_C01"]["delta_detected"]}; đồng thời thay cả nhóm feature và C nên chưa tách được tác động.',
        f'- Gyro-only C1 recall {pct(gyro["metrics"]["event_recall"])}; kết quả hiện tại cho thấy gyro riêng yếu hơn trong bài toán/configuration này, không chứng minh gyro vô ích khi kết hợp hoặc trên phần cứng thật.',
        'Giữ nguyên cả hai cảm biến khi thu test phần cứng. Acc-only là hướng xác nhận đáng ưu tiên sau bước thử thiết bị; chưa được train lại/chọn lại baseline trong giai đoạn phân tích này. Danh sách từng sự kiện cứu/mất nằm trong [sensor_comparison.json](sensor_comparison.json) và [sensor_event_outcomes.csv](sensor_event_outcomes.csv). Không có score window ablation đã lưu để vẽ hoặc quy đóng góp gyro từng thời điểm; ghi thiếu thay vì train lại.', '',
        '## 4. OnField và phần cứng: bằng chứng/giới hạn', '',
        f'OnField: {field["alarms"]} cảnh báo /{field["hours"]:.2f} giờ, rate={field["alarms_per_source_negative_hour"]:.3f}/h, cận trên Poisson95%={field_upper:.3f}/h dưới giả định mô hình Poisson. Không có nhãn ngã để tính recall; không thể suy ra precision cảnh báo trong đời sống.',
        '22/30 cảnh báo (73,33%) thuộc file20241106_1000.csv trên11,45235giờ, xấp xỉ1,921/h. Giữ đủ18file và ghi count/rate riêng; không loại file1000 hoặc gọi đây là một người đã xác minh. Nhãn âm/ID của nguồn chưa được đối chiếu độc lập; mọi điều tra chỉ mô tả, không tuning theo OnField rồi gọi nó là test mới.',
        f'Phần cứng hiện có: {hardware["rows"]} mẫu, dt={hardware["dt_min_us"]}–{hardware["dt_max_us"]}µs, tần suất host trung bình {hardware["observed_host_hz"]:.3f}Hz, gap seq={hardware["seq_gap_count"]}, dữ liệu hữu hạn={hardware["finite"]}. Metadata ground_truth=unknown, trigger synthetic_test; không phải một lần ngã có nhãn. Vị trí abdomen_waist là metadata cố định; hướng sensor_frame_unmapped chưa có ánh xạ tin cậy sang nguồn lưng dưới.',
        'CSV và nhịp đo có thể kiểm tra sơ bộ; chưa đủ nhãn/hướng đeo để chấm recall hoặc FA/h phần cứng. Chưa có nga_01/nga_02 hay phiên hoạt động có nhãn trong data project. Chi phí host đã đo chỉ là số trên máy tính; RAM, inference latency và truyền tin ESP32 vẫn NOT MEASURED.', '',
        '## 5. Hướng làm tiếp theo, theo thứ tự', '',
        '**Ưu tiên1 — thử nhanh baseline đã khóa với dữ liệu phần cứng có nhãn.**',
        '- Bằng chứng: model có recall OOF cao nhưng có tập trung lỗi theo người; chưa có dữ liệu prototype đủ nhãn/vị trí đeo, nên thiếu bước xác nhận luồng đo→dự đoán.',
        '- Đầu vào: CSV100Hz sáu kênh, ảnh/ghi chú vị trí và chiều đeo, vài phút hoạt động bình thường, 1–2 lần ngã có kiểm soát chỉ khi điều kiện an toàn phù hợp, mốc thời gian ngã đồng bộ. Theo [yêu cầu bàn giao](../../docs/YEU_CAU_BO_TEST_PHAN_CUNG.md). Giữ log gốc và không xem trigger là nhãn.',
        '- Phép thử: xác minh units, clock/gap, hướng gắn trước; giữ window100/stride50, preprocessing/model/threshold và cảnh báo như baseline; đối chiếu score/cảnh báo với sự kiện có nhãn. Hướng trục chưa xác minh thì ghi hạn chế, không tự xoay để tối đa score.',
        '- Quyết định: dữ liệu sai/thiếu thì xử lý khâu đo/annotation trước. Dữ liệu hợp lệ nhưng model bỏ sót/báo nhầm thì mở phân tích lệch miền và thu thêm dữ liệu độc lập, không chỉnh ngưỡng theo1–2 lần thử. Phát hiện đúng mà không có báo nhầm chỉ xác nhận test nhỏ đó, chưa chứng minh độ chính xác tổng thể.', '',
        '**Sau đó2 — thí nghiệm xác nhận acc-only và bộ đặc trưng trên development.**',
        '- Giả thuyết: bộ20feature acc có thể giảm lỗi theo người so với full40feature, không nhất thiết cần model sâu. Khóa cùng C/grid/5fold theo người và metric trước khi chạy, giữ dữ liệu ngoài development để xác nhận.',
        '- Ủng hộ khi có lợi ích sự kiện được ghép cặp, không làm xấu FA/h/độ trễ và không chỉ do một người; CI chạm0 hoặc lợi ích không ổn định thì kết luận chưa đủ bằng chứng và giữ baseline. Đây là thí nghiệm đề xuất, chưa thực hiện.', '',
        '**Sau đó3 — chỉ cân nhắc model chuỗi nếu có bằng chứng về thứ tự thời gian.**',
        '- Cần chứng minh lỗi còn lại liên quan thông tin trình tự bị mất bởi thống kê, sau khi đã loại trừ units/axes/nhãn/miền dữ liệu. Các xung trong hình riêng lẻ chưa chứng minh điều đó.',
        '- So sánh model chuỗi nhỏ theo cùng protocol và đo tài nguyên ESP32; nếu không cải thiện trade-off hoặc chưa đủ bằng chứng thì giữ model đơn giản. Chưa có lý do để chọn sẵn CNN.', '',
        '## Tái lập và phạm vi', '',
        'Chạy từ root project: `python tools/datasets/analyze_baseline_results.py`. Chỉ đọc score/model/result đã có; không gọi fit, không quét ngưỡng mới, không cập nhật selection_lock. Nguồn audit lấy từ manifest của dataset export. Đọc score CSV với float_precision=round_trip và đối chiếu NPZ để không lật quyết định ở ngưỡng trùng score.',
        'Các file gốc và model/threshold được băm trước/sau; [verification.json](verification.json) ghi hash nguồn, đầu ra, số lỗi và đối chiếu counts. Điểm vận hành trong threshold_tradeoff.csv chỉ mô tả lại đường score đã lưu; không đổi baseline. Khoảng tin cậy recall/chênh recall ở dạng tỷ lệ0–1; nhân100 để đổi sang phần trăm/điểm phần trăm. Các khoảng tin cậy không được dùng để tuyên bố xác nhận độc lập sau tìm kiếm model.',
        'Đầu ra: metric_summary, error_cases/case_windows/case_comparisons, by_subject/by_activity, model_comparison/model_pairs, sensor_comparison, seed_stability, OnField theo file, hardware_readiness và figures. Thiếu dữ liệu phần cứng là kết luận về mức sẵn sàng, không phải phần phân tích còn dang dở.']
    position = lines.index('## 4. OnField và phần cứng: bằng chứng/giới hạn')
    operating = ['**Đường đánh đổi từ score development đã lưu (không cập nhật threshold):**', '',
                 '| Ngân sách FA/h | Recall quan sát | FA/h quan sát | Threshold mô tả |',
                 '|---:|---:|---:|---:|']
    for r in tradeoff:
        if r['available']:
            operating.append(f'| {r["budget"]} | {pct(r["recall"])} | {r["false_alarms_per_nominal_hour"]:.3f} | {r["threshold"]:.9f} |')
    operating += ['', 'Cùng một điểm0FA cho nhiều ngân sách phản ánh thời lượng âm ngắn. Nới ngân sách lên2/h quan sát có thể bắt thêm sự kiện nhưng cũng tăng cảnh báo; đây là mô tả, không phải quyết định thay ngưỡng.', '']
    lines[position:position] = operating
    (out/'REPORT.md').write_text('\n'.join(line.rstrip() for line in lines)+'\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--baseline', type=Path, default=Path('reports/baseline_selection'))
    parser.add_argument('--out', type=Path, default=Path('reports/baseline_analysis'))
    args = parser.parse_args()
    source = args.source or Path(json.loads(Path('data/processed/univrfall_v1/manifest.json').read_text())['source'])
    result = analyze(source, args.baseline, args.out)
    print(json.dumps(dict(status=result['status'], reviewed_errors=len(result['errors']))))
