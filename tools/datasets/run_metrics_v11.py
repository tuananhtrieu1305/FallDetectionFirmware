"""Run v1.1 on frozen baseline predictions, without retraining or modifying v1."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from benchmark_univrfall import event_metrics as legacy_metrics
from metrics_v11 import evaluate, select_threshold, _rank


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def run(source,out,bootstrap=10000):
    source,out=Path(source),Path(out);out.mkdir(parents=True,exist_ok=True)
    records=json.loads((source/'recording_manifest.json').read_text())
    records=[dict(r,recording_id=j) for j,r in enumerate(records)]
    index=pd.read_csv(source/'selected_window_predictions.csv')
    old=json.loads((source/'selection_lock.json').read_text())
    if old['length']!=100 or old['stride']!=50:raise ValueError('Expected frozen 100x6, stride50 baseline')
    sources={name:sha(source/name) for name in ['recording_manifest.json','selected_window_predictions.csv','selection_lock.json','baseline_model.json']}
    sections={}
    for name,test in [('development',False),('test',True)]:
        rr=[r for r in records if (r['partition']=='test')==test]
        ii=index[index.recording_id.isin([r['recording_id'] for r in rr])].copy()
        sections[name]=(rr,ii)
    rr,ii=sections['development']
    best,curve=select_threshold(rr,ii,ii.score.to_numpy())
    if best is None:raise ValueError('No detecting operating point meets FA/h budget')
    selection=dict(protocol='1.1',threshold=best['threshold'],window=100,stride=50,seed=42,
        selection_data='23 development subjects, frozen five-fold OOF predictions',
        test_used_for_selection=False,training='Frozen baseline; no retraining',
        baseline_model_sha256=sources['baseline_model.json'],
        development_prediction_sha256=hashlib.sha256(ii.to_csv(index=False).encode()).hexdigest(),
        evaluator_sha256=sha(Path(__file__).with_name('metrics_v11.py')),
        rule='Recall, macro recall, fewer FA/h, lower P95 delay, lower active fraction, higher threshold; one fixed model')
    # Write selection lock before scoring test. Full-file hash is provenance only,
    # and intentionally absent from the development selection lock.
    dump(out/'selection_lock.json',selection)
    pd.DataFrame(curve).to_csv(out/'threshold_curve.csv',index=False)
    report=dict(protocol='1.1',selection=selection,source_hashes=sources,metrics={},
        hardware_metrics='NOT MEASURED',limitations=['Nominal source clock','Test/OnField previously observed in baseline; fixed benchmark, not fresh final validation'])
    operating={}
    for limit in [.1,.25,.5,1.,2.]:
        candidates=[r for r in curve if r['false_alarms_per_nominal_hour']<=limit and (r['recall'] or 0)>0]
        operating[str(limit)]=max(candidates,key=_rank) if candidates else None
    report['development_operating_points']=operating
    all_trials=[];all_alarms=[];by_subject=[];by_activity=[];parity=[]
    for name,(rr,ii) in sections.items():
        score=ii.score.to_numpy()
        result=evaluate(rr,ii,score,best['threshold'],bootstrap=bootstrap)
        report['metrics'][name]={k:v for k,v in result.items() if k not in ['per_trial','alarms','by_subject_id','by_activity_key']}
        all_trials.extend(dict(split=name,**r) for r in result['per_trial'])
        all_alarms.extend(dict(split=name,**r) for r in result['alarms'])
        by_subject.extend(dict(split=name,subject_id=s,**v) for s,v in result['by_subject_id'].items())
        by_activity.extend(dict(split=name,activity_key=s,**v) for s,v in result['by_activity_key'].items())
        old_result=legacy_metrics(ii,score,old['threshold'],records,100)
        current=evaluate(rr,ii,score,old['threshold'],bootstrap=0)
        checks={}
        for key in ['events','detected','recall','false_alarms','adl_monitored_nominal_hours','false_alarms_per_nominal_hour',
                    'median_delay_nominal_s','p95_delay_nominal_s','early_fall_trial_alarms','late_fall_trial_alarms','extra_alarms_in_detection_interval']:
            a,b=old_result[key],current[key]
            checks[key]=a==b if a is None or b is None else bool(np.isclose(a,b,rtol=1e-12,atol=1e-12))
        parity.append(dict(split=name,checks=checks,legacy=old_result))
    report['legacy_parity']=dict(**{'pass':all(all(r['checks'].values()) for r in parity)},splits=parity,threshold=old['threshold'])
    if not report['legacy_parity']['pass']:raise AssertionError('Unexplained legacy parity difference')
    pd.DataFrame(all_trials).to_csv(out/'events.csv',index=False)
    pd.DataFrame(all_alarms).to_csv(out/'alarms.csv',index=False)
    pd.DataFrame(by_subject).to_csv(out/'by_subject.csv',index=False)
    pd.DataFrame(by_activity).to_csv(out/'by_activity.csv',index=False)
    dump(out/'metrics.json',report)
    lines=['# Báo cáo baseline theo metric v1.1','',f"Threshold: {best['threshold']:.17g}; chọn từ OOF development, ≤1 FA/giờ danh nghĩa.",'',
           '| Tập | TP / số ngã | Recall | Macro recall | FA / giờ ADL | FA/h | Median / P95 delay (s danh nghĩa) |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for name,m in report['metrics'].items():
        lines.append(f"| {name} | {m['detected']}/{m['events']} | {m['recall']} | {m['macro_recall']} | {m['false_alarms']}/{m['adl_monitored_nominal_hours']:.6f} | {m['false_alarms_per_nominal_hour']} | {m['median_delay_nominal_s']} / {m['p95_delay_nominal_s']} |")
    lines+=['','Các khoảng tin cậy, Recall@0.5s, alarm-active fraction, metric window và giới hạn nằm trong [metrics.json](metrics.json).',
            'Đối chiếu metric cũ ở cùng threshold: PASS. Ngưỡng mới có thể khác do quét toàn bộ score và đổi tie-break.',
            'Test đã từng được xem ở baseline; thời gian nguồn danh nghĩa; chưa đo RAM/latency thiết bị.']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'README.md').write_text('''# Kết quả bộ metric v1.1

- [Báo cáo dễ đọc](report.md)
- [Đầy đủ metric và khoảng tin cậy](metrics.json)
- [Từng trial/sự kiện](events.csv), [từng cảnh báo](alarms.csv)
- [Theo người](by_subject.csv), [theo hoạt động](by_activity.csv)
- [Đường threshold](threshold_curve.csv), [khóa lựa chọn](selection_lock.json)

Giá trị null nghĩa là không xác định/không có mẫu số. Một dòng events.csv là một trial, gồm cả ADL; lọc events=1 để xem lần ngã.
Báo cáo dùng score baseline đã lưu, không train CNN. Score development là OOF; test là model baseline fit trên 23 người development.
OnField nếu đã chạy nằm tại onfield/summary.json, tách riêng với laboratory. Đơn vị thời gian nguồn là danh nghĩa.

Chạy lại từ root project:

```powershell
python tools/datasets/run_metrics_v11.py --source <thu_muc_audit_trong_manifest> --out reports/metrics_v1_1
```

Model khác cung cấp cùng schema prediction, đầy đủ IGNORE và metadata manifest. Chỉ dùng development để chọn threshold; khóa trước khi evaluate test.
''',encoding='utf-8')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--out',type=Path,default=Path('reports/metrics_v1_1'))
    parser.add_argument('--bootstrap',type=int,default=10000)
    args=parser.parse_args();result=run(args.source,args.out,args.bootstrap)
    print(json.dumps(dict(selection=result['selection'],legacy_parity=result['legacy_parity']['pass']),indent=2))
