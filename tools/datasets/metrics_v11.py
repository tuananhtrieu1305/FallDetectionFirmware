"""Model-independent continuous fall metrics. Inclusive frames, nominal source time.

Only explicitly selected manifest records belong to an evaluation. Missing scores
are errors; a legitimate short segment contributes its event but no windows.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import beta, chi2
from sklearn.metrics import average_precision_score, confusion_matrix

VERSION = '1.1'


def ratio(a, b):
    return float(a / b) if b else None


def prepare(records, index, scores, length=100, stride=50, fs=100):
    if length < 1 or stride < 1 or fs <= 0:
        raise ValueError('Invalid window/stride/clock')
    scores = np.asarray(scores, dtype=float)
    if scores.shape != (len(index),) or not np.isfinite(scores).all():
        raise ValueError('Missing/nonfinite scores')
    required = {'recording_id', 'end_frame', 'y'}
    if not required.issubset(index.columns):
        raise ValueError('Missing prediction columns')
    if not index.y.isin([-1, 0, 1]).all():
        raise ValueError('Invalid label')
    if 'start_frame' in index and not (index.start_frame == index.end_frame-length+1).all():
        raise ValueError('Invalid window start')
    keys, groups, offset = [], [], 0
    seen = set()
    for position, record in enumerate(records):
        rid = record.get('recording_id', position)
        if rid in seen:
            raise ValueError('Duplicate recording')
        seen.add(rid)
        event = record.get('event')
        segments = record.get('segments', [dict(first_frame=record.get('frame_first', 0), rows=record['rows'])])
        if sum(s['rows'] for s in segments) != record['rows']:
            raise ValueError('Segment lengths disagree with recording rows')
        if event and (not segments or event['onset'] < segments[0]['first_frame'] or
                      event['impact'] >= segments[-1]['first_frame']+segments[-1]['rows']):
            raise ValueError('Event outside recording')
        previous_end = None
        for segment_id, seg in enumerate(segments):
            first, n = seg['first_frame'], seg['rows']
            if int(first) != first or int(n) != n or n < 0:
                raise ValueError('Invalid segment')
            if previous_end is not None and first <= previous_end:
                raise ValueError('Overlapping/unordered segments')
            previous_end = first + n - 1
            ends = np.arange(first + length - 1, first + n, stride, dtype=np.int64)
            durations = np.diff(np.r_[ends, first + n]) if len(ends) else np.array([], int)
            groups.append(dict(rid=rid, record=record, segment=segment_id, first=first, rows=n,
                               begin=offset, end=offset+len(ends), ends=ends, durations=durations))
            offset += len(ends)
            keys.extend((rid, int(e)) for e in ends)
        if event and not event['onset'] < event['impact']:
            raise ValueError('Invalid event')
    actual = list(zip(index.recording_id.tolist(), index.end_frame.tolist()))
    if actual != keys:
        raise ValueError('Missing/duplicate/out-of-order windows or unexpected recording/segment')
    by_id = {r.get('recording_id', p): r for p, r in enumerate(records)}
    for column in ['subject_id', 'partition', 'trial_id']:
        if column in index:
            if any(row[column] != by_id[row['recording_id']][column] for row in index.to_dict('records')):
                raise ValueError('Prediction metadata disagrees with manifest: '+column)
    return dict(records=records, index=index.reset_index(drop=True), scores=scores,
                groups=groups, fs=fs, length=length, stride=stride)


def _trials(p, threshold):
    if not np.isfinite(threshold):
        raise ValueError('Threshold must be finite')
    rows = {r.get('recording_id', j): dict(recording_id=r.get('recording_id', j),
            trial_id=r['trial_id'], subject_id=r['subject_id'], activity_key=r['activity_key'],
            events=int(bool(r.get('event'))), detected=0, fast=0, delay=None,
            false_alarms=0, hours=0., active_seconds=0., longest=0., early=0, late=0, repeats=0,
            source_seconds=0., warmup_seconds=0., windows=0, alarm_frames=[])
            for j, r in enumerate(p['records'])}
    alarms, matching = [], {}
    for g in p['groups']:
        row = rows[g['rid']]
        row['source_seconds'] += g['rows']/p['fs']
        row['warmup_seconds'] += min(g['rows'], p['length']-1)/p['fs']
        decision = p['scores'][g['begin']:g['end']] >= threshold
        ends, durations = g['ends'], g['durations']/p['fs']
        starts = np.flatnonzero(decision & ~np.r_[False, decision[:-1]]) if len(decision) else []
        row['windows'] += len(ends)
        event = g['record'].get('event')
        if event is None:
            row['hours'] += max(0, g['rows']-p['length']+1)/p['fs']/3600
            row['active_seconds'] += float(durations[decision].sum())
            row['false_alarms'] += len(starts)
        run = 0.
        for active, duration in zip(decision, durations):
            run = run + duration if active else 0.
            if event is None:
                row['longest'] = max(row['longest'], run)
        for k in starts:
            frame = int(ends[k]); row['alarm_frames'].append(frame)
            kind = 'false_alarm'
            if event:
                if frame < event['onset']:
                    row['early'] += 1; kind = 'early'
                elif frame > event['impact']+100:
                    row['late'] += 1; kind = 'late'
                else:
                    matching.setdefault(g['rid'], []).append(frame); kind = 'matched_or_repeat'
            alarms.append(dict(recording_id=g['rid'], trial_id=row['trial_id'], subject_id=row['subject_id'],
                               segment=g['segment'], frame=frame, kind=kind))
    for rid, row in rows.items():
        frames = matching.get(rid, [])
        row['no_window'] = row['events'] == 1 and row['windows'] == 0
        if frames:
            event = next(g['record']['event'] for g in p['groups'] if g['rid']==rid)
            row.update(detected=1, fast=int(frames[0]<=event['impact']+50),
                       delay=(frames[0]-event['impact'])/p['fs'], repeats=len(frames)-1)
    return list(rows.values()), alarms


def _aggregate(rows):
    events = sum(r['events'] for r in rows); tp = sum(r['detected'] for r in rows)
    fa = sum(r['false_alarms'] for r in rows); hours = sum(r['hours'] for r in rows)
    delays = [r['delay'] for r in rows if r['delay'] is not None]
    subjects = sorted({r['subject_id'] for r in rows})
    person = [ratio(sum(r['detected'] for r in rows if r['subject_id']==s),
                    sum(r['events'] for r in rows if r['subject_id']==s)) for s in subjects]
    return dict(events=events, detected=tp, missed=events-tp, recall=ratio(tp,events),
                miss_rate=ratio(events-tp,events), macro_recall=float(np.mean([v for v in person if v is not None])) if any(v is not None for v in person) else None,
                false_alarms=fa, adl_monitored_nominal_hours=hours,
                false_alarms_per_nominal_hour=ratio(fa,hours),
                recall_at_0_5s=ratio(sum(r['fast'] for r in rows),events), recall_at_1s=ratio(tp,events),
                median_delay_nominal_s=float(np.median(delays)) if delays else None,
                p95_delay_nominal_s=float(np.percentile(delays,95,method='linear')) if delays else None,
                delay_event_count=len(delays), preimpact_detection_fraction=ratio(sum(d<0 for d in delays),len(delays)),
                alarm_active_fraction=ratio(sum(r['active_seconds'] for r in rows),hours*3600),
                longest_positive_run_nominal_s=max([r['longest'] for r in rows],default=0.),
                early_fall_trial_alarms=sum(r['early'] for r in rows), late_fall_trial_alarms=sum(r['late'] for r in rows),
                extra_alarms_in_detection_interval=sum(r['repeats'] for r in rows),
                source_nominal_seconds=sum(r['source_seconds'] for r in rows),
                warmup_nominal_seconds=sum(r['warmup_seconds'] for r in rows),
                gap_duration_status='Excluded; elapsed gap duration requires verified source timestamps',
                events_without_windows=sum(r['no_window'] for r in rows))


def _window(y, scores, threshold):
    mask = y >= 0; y=y[mask]; scores=scores[mask]
    matrix=confusion_matrix(y,scores>=threshold,labels=[0,1]); tn,fp,fn,tp=map(int,matrix.ravel())
    return dict(confusion_matrix=matrix.tolist(),precision=ratio(tp,tp+fp),recall=ratio(tp,tp+fn),
                f1=ratio(2*tp,2*tp+fp+fn),average_precision=float(average_precision_score(y,scores)) if (y==1).any() else None,
                fall_fraction=ratio(int((y==1).sum()),len(y)),windows=len(y),ignored_windows=int((~mask).sum()))


def uncertainty(rows, count=10000, seed=42):
    m=_aggregate(rows); n=m['events']; k=m['detected']; h=m['adl_monitored_nominal_hours']
    result=dict(event_binomial_95=[float(beta.ppf(.025,k,n-k+1)) if k else 0.,
                 float(beta.ppf(.975,k+1,n-k)) if k<n else 1.] if n else None,
                poisson_upper_95_per_hour=float(chi2.ppf(.95,2*(m['false_alarms']+1))/2/h) if h else None)
    people=sorted({r['subject_id'] for r in rows}); values=[]
    # Bootstrap only sufficient person-level counts, preserving all trials together.
    for s in people:
        rr=[r for r in rows if r['subject_id']==s]
        values.append([sum(r['detected'] for r in rr),sum(r['events'] for r in rr),
                       sum(r['false_alarms'] for r in rr),sum(r['hours'] for r in rr)])
    ci={}
    if count and people:
        rng=np.random.default_rng(seed); a=np.array(values); sums=a[rng.integers(len(a),size=(count,len(a)))].sum(axis=1)
        for name, numerator, denominator in [('recall',0,1),('fa_per_hour',2,3)]:
            valid=sums[:,denominator]>0
            v=sums[valid,numerator]/sums[valid,denominator]
            ci[name]=np.percentile(v,[2.5,97.5]).tolist() if len(v) else None
            ci[name+'_valid_resamples']=int(valid.sum())
    else:
        ci.update(recall=None,fa_per_hour=None)
    result['bootstrap_95']=dict(**ci,resamples=count,seed=seed,subjects=len(people),
        limitation='Conditional on frozen predictions; degenerate intervals do not prove certainty. Events correlated within subjects; binomial/Poisson assumptions are supplementary.')
    return result


def evaluate(records,index,scores,threshold,*,length=100,stride=50,fs=100,bootstrap=10000):
    p=prepare(records,index,scores,length,stride,fs)
    rows,alarms=_trials(p,threshold); m=_aggregate(rows)
    m.update(protocol=VERSION,threshold=float(threshold),time_basis='nominal',per_trial=rows,alarms=alarms,
             window_metrics=_window(p['index'].y.to_numpy(int),p['scores'],threshold),
             **uncertainty(rows,bootstrap))
    for key in ['subject_id','activity_key']:
        m['by_'+key]={s:_aggregate([r for r in rows if r[key]==s]) for s in sorted({r[key] for r in rows})}
    return m


def _rank(row):
    return (row['recall'] if row['recall'] is not None else -1,
            row['macro_recall'] if row['macro_recall'] is not None else -1,
            -row['false_alarms_per_nominal_hour'],
            -(row['p95_delay_nominal_s'] if row['p95_delay_nominal_s'] is not None else np.inf),
            -(row['alarm_active_fraction'] if row['alarm_active_fraction'] is not None else np.inf),row['threshold'])


def select_threshold(records,index,scores,limit=1.,length=100,stride=50,fs=100):
    """Exact sweep, vectorized in bounded batches; no monotonic FA assumption."""
    p=prepare(records,index,scores,length,stride,fs)
    if any(r.get('partition')=='test' for r in records):
        raise ValueError('Test records forbidden in threshold selection')
    s=p['scores']
    if not len(s): raise ValueError('No development scores')
    thresholds=np.unique(np.r_[np.nextafter(s.min(),-np.inf),s,np.nextafter(s.max(),np.inf)])
    # Segment-level operations keep run resets and tails identical to scalar evaluator.
    curve=[]; event_records=[r for r in records if r.get('event')]
    people=sorted({r['subject_id'] for r in event_records})
    hours=sum(max(0,g['rows']-length+1)/fs/3600 for g in p['groups'] if not g['record'].get('event'))
    if not hours: raise ValueError('No monitored ADL for threshold selection')
    for begin in range(0,len(thresholds),128):
        ts=thresholds[begin:begin+128]; size=len(ts)
        false=np.zeros(size,int); active=np.zeros(size); first={r.get('recording_id',j):np.full(size,np.inf) for j,r in enumerate(records) if r.get('event')}
        for g in p['groups']:
            if g['end']==g['begin']:continue
            positive=s[None,g['begin']:g['end']]>=ts[:,None]
            starts=positive & ~np.c_[np.zeros(size,bool),positive[:,:-1]]
            e=g['record'].get('event')
            if not e:
                false+=starts.sum(axis=1)
                active+=(positive*g['durations'][None,:]).sum(axis=1)/fs
            else:
                eligible=(g['ends']>=e['onset']) & (g['ends']<=e['impact']+100)
                frame=np.min(np.where(starts & eligible[None,:],g['ends'][None,:],np.inf),axis=1)
                first[g['rid']]=np.minimum(first[g['rid']],frame)
        detection=[]; delays=[]; person_detection={person:[] for person in people}
        for j,r in enumerate(records):
            if not r.get('event'):continue
            frames=first[r.get('recording_id',j)]; got=np.isfinite(frames)
            detection.append(got);person_detection[r['subject_id']].append(got)
            delays.append((frames-r['event']['impact'])/fs)
        recall=np.mean(detection,axis=0) if detection else np.full(size,np.nan)
        macro=np.mean([np.mean(v,axis=0) for v in person_detection.values()],axis=0) if people else np.full(size,np.nan)
        for k,t in enumerate(ts):
            delay=[d[k] for d in delays if np.isfinite(d[k])]
            curve.append(dict(threshold=float(t),recall=float(recall[k]) if detection else None,
                macro_recall=float(macro[k]) if people else None,false_alarms=int(false[k]),
                false_alarms_per_nominal_hour=float(false[k]/hours),
                p95_delay_nominal_s=float(np.percentile(delay,95)) if delay else None,
                alarm_active_fraction=float(active[k]/(hours*3600))))
    eligible=[r for r in curve if r['false_alarms_per_nominal_hour']<=limit and (r['recall'] or 0)>0]
    return (max(eligible,key=_rank) if eligible else None),curve
