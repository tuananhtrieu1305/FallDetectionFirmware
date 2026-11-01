"""Acceptance verification: all laboratory artifacts and all 18 field files."""
import argparse
import json
from pathlib import Path
import numpy as np
from onfield_metrics_v11 import run as field_run, evaluate_file
from run_metrics_v11 import run as laboratory_run, sha, dump


def verify(source,raw,out):
    source,raw,out=Path(source),Path(raw),Path(out)
    report=laboratory_run(source,out)
    field=field_run(raw,source,out)
    manifest=json.loads((raw/'full_download_manifest.json').read_text())
    model=json.loads((source/'baseline_model.json').read_text())
    legacy=json.loads((source/'onfield_evaluation.json').read_text())
    old_by_member={r['source_member']:r for r in legacy['files']}
    rows=[]
    for member,entry in sorted(manifest.items()):
        if '/OnField/' not in member or not member.endswith('.csv'):continue
        frozen=json.loads((out/'onfield'/(Path(member).stem+'.json')).read_text(encoding='utf-8'))
        changed=dict(model,threshold=report['selection']['threshold'])
        different_chunk=evaluate_file(entry['file'],changed,chunksize=37123)
        for key in ['false_alarms','adl_monitored_nominal_hours','alarm_active_fraction',
                    'longest_positive_run_nominal_s','sensor_rows','windows','segments','alarms']:
            a,b=frozen[key],different_chunk[key]
            assert a==b,(member,key)
        # Independent old evaluator's saved release results at its original threshold.
        original=evaluate_file(entry['file'],model,chunksize=37123)
        old=old_by_member[member]
        assert original['false_alarms']==old['alarms'],member
        assert np.isclose(original['adl_monitored_nominal_hours'],old['monitored_nominal_hours'],rtol=1e-12),member
        assert original['sensor_rows']==old['sensor_rows'],member
        assert [a['frame'] for a in original['alarms']]==old['alarm_sensor_rows'],member
        rows.append(dict(source_member=member,chunk_invariance='PASS',legacy_counts_exposure_alarm_rows='PASS',raw_sha256=entry['sha256']))
        print('VERIFIED '+Path(member).name,flush=True)
    assert len(rows)==18
    expected=['README.md','metrics.json','report.md','events.csv','alarms.csv','by_subject.csv','by_activity.csv','threshold_curve.csv','selection_lock.json']
    for name in expected:assert (out/name).is_file()
    assert report['legacy_parity']['pass']
    result=dict(status='PASS',protocol='1.1',laboratory_legacy_parity=True,onfield_files_verified=18,
        source_predictions_sha256=sha(source/'selected_window_predictions.csv'),
        artifact_hashes={name:sha(out/name) for name in expected},onfield=rows,
        full_source_field_hours=field['monitored_nominal_hours'],notes='No training; frozen predictions; source clock nominal')
    dump(out/'verification.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('reports/metrics_v1_1'));a=p.parse_args();r=verify(a.source,a.raw,a.out);print(r['status'])
