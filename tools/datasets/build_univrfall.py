"""Build auditable physical-unit recordings, subject splits and window tensors.

Example: python tools/datasets/build_univrfall.py --raw RAW/univrfall --out OUTPUT
All output is research-grade nominal time until the source clock is resolved.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from univrfall_core import (CHANNELS, RAW_CHANNELS, parse_annotations, resolve_label,
                           physical_units, validate_trial, subject_split,
                           window_bounds, window_label, fit_normalizer)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_annotations(manifest):
    labels, errors, records, protocols = {}, [], [], {}
    for member, provenance in sorted(manifest.items()):
        if not member.endswith('_label.xlsx'):
            continue
        subject = re.search(r'(SA\d+)_label', member)[1]
        path = Path(provenance['file'])
        if sha(path) != provenance['sha256']:
            raise ValueError(f'Annotation hash changed: {member}')
        table = pd.read_excel(path).dropna(how='all')
        table.iloc[:, :2] = table.iloc[:, :2].ffill()
        labels[subject] = {}
        for index, row in table.iterrows():
            evidence = dict(subject_id=subject, source_member=member,
                            annotation_sha256=provenance['sha256'], row=int(index)+2)
            try:
                parsed = parse_annotations(pd.DataFrame([row], index=[index]))
                key, event = next(iter(parsed.items()))
                if key in labels[subject]:
                    # Remove ambiguous previous entry too; never keep the first silently.
                    labels[subject][key] = None
                    raise ValueError('Duplicate task/trial annotation')
                labels[subject][key] = {**event, 'annotation_source_member': member,
                                       'annotation_sha256': provenance['sha256'],
                                       'annotation_row': int(index)+2}
                records.append({**event, **evidence, 'task_id': key[0], 'trial': key[1]})
            except ValueError as exc:
                errors.append({**evidence, 'reason': str(exc), 'original': row.to_dict()})
        protocols[subject] = any(v and v['fall_code'] == 'F01' and k[0] == 22
                                 for k, v in labels[subject].items())
    return labels, errors, records, protocols


def build(raw, out, expected_csv=1234):
    raw, out = Path(raw), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out/'recordings').mkdir(exist_ok=True)
    manifest = json.loads((raw/'full_download_manifest.json').read_text(encoding='utf-8'))
    labels, annotation_errors, annotations, shifted = load_annotations(manifest)
    accepted, rejected, signal_hashes = [], [], {}
    source_rows = 0
    csv_members = [n for n in sorted(manifest) if '/laboratory/sensors_data/' in n and n.endswith('.csv')]
    if len(csv_members) != expected_csv:
        raise ValueError(f'Expected {expected_csv} laboratory CSV, found {len(csv_members)}')
    matched_annotations = set()
    for member in csv_members:
        provenance = manifest[member]
        path = Path(provenance['file'])
        if sha(path) != provenance['sha256']:
            raise ValueError(f'Raw checksum changed: {member}')
        match = re.fullmatch(r'S(\d+)T(\d+)R(\d+)\.csv', Path(member).name)
        if not match:
            raise ValueError(f'Unexpected filename {member}')
        subject, task, trial = f'SA{match[1]}', int(match[2]), int(match[3])
        info = dict(subject_id=subject, trial_id=path.name.split('_', 1)[-1].removesuffix('.csv'),
                    task_id=task, trial=trial, source_member=member, source_sha256=provenance['sha256'])
        # Use original member basename, independent of local cache naming.
        info['trial_id'] = Path(member).stem
        df = pd.read_csv(path)
        source_rows += len(df)
        info['rows'] = len(df)
        try:
            if df.columns[0] not in ['TimeStamp(s)', 'Unnamed: 0'] or df.columns.tolist()[1:] != ['FrameCounter'] + RAW_CHANNELS + ['EulerX','EulerY','EulerZ']:
                raise ValueError('Unexpected raw schema')
            info['raw_timestamp_column'] = str(df.columns[0])
            annotation = labels[subject].get((task, trial), 'absent')
            if annotation is None:
                raise ValueError('Ambiguous duplicate annotation')
            label = resolve_label(task, trial, labels[subject])
            if label['label'] == 0 and shifted[subject]:
                raise ValueError('ADL task mapping unverified in shifted subject protocol')
            frames = df.FrameCounter.to_numpy(dtype=np.float64)
            values = physical_units(df[RAW_CHANNELS].to_numpy(dtype=np.float64))
            event = {k: label[k] for k in ['onset','impact']} if label['label'] else None
            validate_trial(frames, values, event)
            host = df.iloc[:, 0].to_numpy(dtype=np.float64) / 1000
            if not np.isfinite(host).all():
                raise ValueError('Nonfinite source timestamp')
            elapsed = float(host[-1] - host[0])
            dt = np.diff(host)
            flags = []
            if (dt == 0).any(): flags.append('duplicate_host_timestamps')
            if (dt < 0).any(): flags.append('backward_host_timestamps')
            if (np.abs(values[:, 3:]) > np.deg2rad(2000)).any(): flags.append('gyro_above_published_range')
            if (np.abs(df[RAW_CHANNELS[:3]].to_numpy()) >= 3990).any(): flags.append('accel_near_observed_4g_envelope')
            info.update(label)
            info.update(event=event, flags=flags, time_basis='frame_counter_100hz_nominal_unverified',
                        frame_first=int(frames[0]), frame_last=int(frames[-1]),
                        host_elapsed_s=elapsed, nominal_elapsed_s=float((frames[-1]-frames[0])/100),
                        host_effective_hz=(len(frames)-1)/elapsed if elapsed > 0 else None,
                        duplicate_host_steps=int((dt == 0).sum()), backward_host_steps=int((dt < 0).sum()),
                        gyro_max_dps=float(np.rad2deg(np.abs(values[:,3:]).max())),
                        accel_max_g=float(np.abs(values[:,:3]).max()/9.80665),
                        annotation_evidence=('subject XLSX' if event else 'Zenodo v1 documented ADL ID; standard protocol'))
            output = out/'recordings'/f'{info["trial_id"]}.npz'
            np.savez_compressed(output, values=values.astype(np.float32), frame=frames.astype(np.int64),
                                host_time_s=host, time_s=(frames-frames[0])/100)
            info['recording'] = f'recordings/{output.name}'
            info['signal_sha256'] = hashlib.sha256(values.astype(np.float32).tobytes()).hexdigest()
            signal_hashes.setdefault(info['signal_sha256'], []).append(info['trial_id'])
            accepted.append(info)
            if event:
                matched_annotations.add((subject,task,trial))
        except (ValueError, KeyError, TypeError) as exc:
            rejected.append({**info, 'reason': str(exc)})
    split = subject_split(accepted)
    for info in accepted:
        info['partition'] = split[info['subject_id']]
    dump(out/'splits.json', dict(seed=42, search_candidates=1000, subjects=split,
                               method='metadata-only balanced subject permutations; fixed before model training'))
    dump(out/'recording_manifest.json', accepted)
    dump(out/'quarantine.json', rejected)
    dump(out/'annotations.json', annotations)
    dump(out/'annotation_errors.json', annotation_errors)
    unmatched = [a for a in annotations if (a['subject_id'],a['task_id'],a['trial']) not in matched_annotations]
    dump(out/'unmatched_annotations.json', unmatched)
    # Fit per-fold and final statistics on each raw train row exactly once.
    stats = {}
    for name in ['fold0','fold1','fold2','fold3','fold4','final']:
        train = [r for r in accepted if r['partition'] != 'test' and r['partition'] != name]
        stats[name] = fit_normalizer(np.load(out/r['recording'])['values'] for r in train)
        stats[name]['subjects'] = sorted({r['subject_id'] for r in train})
    dump(out/'normalizers.json', stats)
    tensor_hashes, window_reports = {}, {}
    for length in [100,200,300]:
        tensors, indices, ys = [], [], []
        event_covered, ignored = [], 0
        for rid, info in enumerate(accepted):
            values = np.load(out/info['recording'])['values']
            positive = 0
            for start, end in window_bounds(len(values),length):
                absolute_start, absolute_end = start+info['frame_first'], end+info['frame_first']
                y = window_label(absolute_start, absolute_end, info['event'])
                tensors.append(values[start:end+1])
                ys.append(y)
                indices.append(dict(recording_id=rid, trial_id=info['trial_id'], subject_id=info['subject_id'],
                                    activity_key=info['activity_key'], partition=info['partition'],
                                    start_row=start, end_row=end, start_frame=absolute_start,
                                    end_frame=absolute_end, y=y, quality_flags='|'.join(info['flags'])))
                positive += y == 1
                ignored += y == -1
            if info['event']:
                event_covered.append(dict(trial_id=info['trial_id'], positive_windows=positive))
        x, y = np.asarray(tensors,dtype=np.float32), np.array(ys,dtype=np.int8)
        np.savez_compressed(out/f'windows_{length}.npz', X=x, y=y)
        pd.DataFrame(indices).to_csv(out/f'window_index_{length}.csv',index=False,lineterminator='\n')
        tensor_hashes[str(length)] = dict(X=hashlib.sha256(x.tobytes()).hexdigest(),
                                           y=hashlib.sha256(y.tobytes()).hexdigest(), shape=list(x.shape))
        window_reports[str(length)] = dict(counts=dict(Counter(str(v) for v in ys)),
                                            events_without_positive=[e for e in event_covered if not e['positive_windows']],
                                            event_coverage=len([e for e in event_covered if e['positive_windows']]))
    dump(out/'tensor_hashes.json',tensor_hashes)
    coverage = {}
    for partition in sorted(set(split.values())):
        selected = [r for r in accepted if r['partition']==partition]
        coverage[partition] = dict(subjects=sorted({r['subject_id'] for r in selected}),
                                  fall_events=sum(r['label'] for r in selected),
                                  adl_nominal_hours=sum(r['rows']/100/3600 for r in selected if not r['label']),
                                  activities=dict(Counter(r['activity_key'] for r in selected)))
    audit = dict(source_csv_files=len(csv_members), source_rows=source_rows,
                 source_annotation_rows=len(annotations)+len(annotation_errors),
                 accepted_trials=len(accepted), quarantined_trials=len(rejected),
                 accepted_rows=sum(r['rows'] for r in accepted),
                 valid_fall_events=sum(r['label'] for r in accepted),
                 annotation_errors=len(annotation_errors), unmatched_annotations=len(unmatched),
                 quarantine_reasons=dict(Counter(r['reason'] for r in rejected)),
                 flags=dict(Counter(flag for r in accepted for flag in r['flags'])),
                 duplicate_signal_trials=[v for v in signal_hashes.values() if len(v)>1],
                 partitions=coverage, windows=window_reports,
                 clock_status='nominal_unverified', axes='source_sensor_frame; hardware alignment pending')
    dump(out/'audit.json',audit)
    dump(out/'config.json',dict(version='univrfall_binary_v1', source_record=18346755,
                               channels=CHANNELS, accel_unit='m/s2', gyro_unit='rad/s',
                               gravity_included=True, hz_nominal=100, lengths=[100,200,300],stride=50,
                               positive_horizon_frames=100, pre_onset_exclusion_frames=50,
                               filtering='none', augmentation='disabled', placement='lower_back_L1_L2',
                               labels={'0':'NON_FALL','1':'FALL','-1':'IGNORE_NOT_A_CLASS'}))
    print(json.dumps({k:v for k,v in audit.items() if k not in ['partitions','windows','duplicate_signal_trials']},ensure_ascii=True),flush=True)
    return audit


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    build(args.raw,args.out)
