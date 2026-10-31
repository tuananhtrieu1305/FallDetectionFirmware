"""Independent exhaustive release check, not just a sample conversion check."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta


def verify(raw,root):
    source=json.loads((raw/'full_download_manifest.json').read_text())
    records=json.loads((root/'recording_manifest.json').read_text())
    quarantine=json.loads((root/'quarantine.json').read_text())
    split=json.loads((root/'splits.json').read_text())['subjects']
    checks={}
    lab={k:v for k,v in source.items() if '/laboratory/' in k}
    for member,entry in lab.items():
        assert hashlib.sha256(Path(entry['file']).read_bytes()).hexdigest()==entry['sha256'],member
    csvs={n for n in lab if n.endswith('.csv')}
    assert csvs=={r['source_member'] for r in records+quarantine}
    assert len(records)+len(quarantine)==len(csvs)
    assert len({r['trial_id'] for r in records})==len(records)
    assert len(split)==29 and sum(v=='test' for v in split.values())==6
    checks['raw_lab_members_hashed']=len(lab)
    checks['all_csv_accounted_for']=len(csvs)
    arrays=[]
    for r in records:
        raw_frame=pd.read_csv(source[r['source_member']]['file'])
        with np.load(root/r['recording']) as data:
            values=data['values'].copy();frames=data['frame'].copy()
            expected=raw_frame.iloc[:,2:8].to_numpy(float)*np.array([.00980665]*3+[np.pi/180000]*3)
            np.testing.assert_allclose(values,expected,rtol=1e-6,atol=1e-7)
            np.testing.assert_array_equal(frames,raw_frame.FrameCounter)
            np.testing.assert_allclose(data['time_s'],(frames-frames[0])/100,atol=1e-12)
            assert np.isfinite(values).all() and (np.diff(frames)==1).all()
        assert r['partition']==split[r['subject_id']]
        if r['event']:
            table=pd.read_excel(source[r['annotation_source_member']]['file'])
            match=table.iloc[:,0].ffill().astype(str).str.extract(r'\((\d+)\)')[0].astype(int).eq(r['task_id']) & table['Trial ID'].eq(r['trial'])
            assert match.sum()==1
            annotation=table[match].iloc[0]
            assert int(annotation.Fall_onset_frame)==r['event']['onset']
            assert int(annotation.Fall_impact_frame)==r['event']['impact']
        arrays.append(values)
    stats=json.loads((root/'normalizers.json').read_text())
    for fold,s in stats.items():
        chosen=[x for r,x in zip(records,arrays) if r['partition'] not in ['test',fold]]
        cat=np.concatenate(chosen).astype(np.float64)
        np.testing.assert_allclose(s['mean'],cat.mean(axis=0),atol=1e-12)
        np.testing.assert_allclose(s['std'],cat.std(axis=0),rtol=1e-10)
        assert not set(s['subjects']) & {p for p,v in split.items() if v=='test' or v==fold}
    checks['physical_recordings_verified']=len(records)
    checks['normalizers_no_test_or_validation_leakage']=len(stats)
    hashes=json.loads((root/'tensor_hashes.json').read_text())
    for length in [100,200,300]:
        index=pd.read_csv(root/f'window_index_{length}.csv')
        with np.load(root/f'windows_{length}.npz') as shard:
            x,y=shard['X'],shard['y']
            assert list(x.shape)==hashes[str(length)]['shape']
            assert hashlib.sha256(x.tobytes()).hexdigest()==hashes[str(length)]['X']
            assert hashlib.sha256(y.tobytes()).hexdigest()==hashes[str(length)]['y']
            assert len(index)==len(x)==len(y)
            for i,w in enumerate(index.itertuples(index=False)):
                r=records[w.recording_id]
                np.testing.assert_array_equal(x[i],arrays[w.recording_id][w.start_row:w.end_row+1])
                assert w.subject_id==r['subject_id'] and w.partition==r['partition']
                assert w.end_row-w.start_row+1==length and 0<=w.start_row<=w.end_row<r['rows']
                assert w.start_frame==r['frame_first']+w.start_row
                assert w.end_frame==r['frame_first']+w.end_row
                e=r['event']
                expected=0 if e is None else (1 if w.start_frame<=e['impact']<=w.end_frame<=e['impact']+100 else
                                               0 if w.end_frame<e['onset']-50 else -1)
                assert int(y[i])==w.y==expected
        checks[f'windows_{length}_exhaustively_verified']=len(index)
    if (root/'benchmark.json').exists():
        b=json.loads((root/'benchmark.json').read_text());t=b['test']
        n,k=t['events'],t['detected'];duration=t['adl_monitored_nominal_hours']
        checks['test_uncertainty']=dict(event_binomial_95_interval=[float(beta.ppf(.025,k,n-k+1)) if k else 0.,
                         float(beta.ppf(.975,k+1,n-k)) if k<n else 1.],
                         zero_false_alarm_poisson_one_sided_95_upper_per_nominal_hour=float(-np.log(.05)/duration) if t['false_alarms']==0 else None,
                         limitation='Events within a person are correlated; binomial interval assumes independent events. Nominal clock; laboratory only.')
    checks['status']='PASS'
    (root/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks),flush=True)
    return checks


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    args=parser.parse_args()
    verify(args.raw,args.dataset)
