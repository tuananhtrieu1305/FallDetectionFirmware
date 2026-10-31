"""Pure, tested contracts for the UNIVRFall binary event dataset.

All frame intervals are inclusive. -1 means IGNORE, never a third class.
No learned preprocessing is fitted inside window generation.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd

CHANNELS = ['ax', 'ay', 'az', 'gx', 'gy', 'gz']
RAW_CHANNELS = ['AccX', 'AccY', 'AccZ', 'GyrX', 'GyrY', 'GyrZ']
# Explicit ADL IDs from Zenodo v1, not the complement of the fall table.
# SA10-SA13 have a different protocol: do not guess the meanings of T20/T21.
ADL = {
    1: 'Stand', 2: 'Tie shoe lace', 3: 'Pick up object', 4: 'Jump gently',
    5: 'Sit on ground and get up', 6: 'Walk normally', 7: 'Walk quickly',
    8: 'Jog normally', 9: 'Jog quickly', 10: 'Stumble over obstacle',
    11: 'Sit on chair', 12: 'Walk downstairs normally',
    13: 'Sit/get up normally', 14: 'Sit/get up quickly',
    15: 'Collapse into chair', 16: 'Walk downstairs quickly',
    17: 'Lie on floor', 18: 'Lie/get up normally', 19: 'Lie/get up quickly',
    35: 'Walk upstairs normally', 36: 'Walk upstairs quickly',
    43: 'Climb stairs', 44: 'Jump over obstacle',
}


def integer(value):
    if pd.isna(value) or not np.isfinite(float(value)) or float(value) != int(value):
        raise ValueError(f'Expected integer, got {value!r}')
    return int(value)


def parse_annotations(table):
    required = ['Task Code (Task ID)', 'Description', 'Trial ID',
                'Fall_onset_frame', 'Fall_impact_frame']
    if list(table.columns) != required:
        raise ValueError('Unexpected annotation columns')
    table = table.dropna(how='all').copy()
    table[required[:2]] = table[required[:2]].ffill()
    result = {}
    for index, row in table.iterrows():
        match = re.fullmatch(r'(F\d{2})\s*\((\d+)\)', str(row[required[0]]).strip())
        if not match or pd.isna(row.Description):
            raise ValueError(f'Invalid annotation row {index}')
        task, trial = int(match[2]), integer(row['Trial ID'])
        onset, impact = integer(row.Fall_onset_frame), integer(row.Fall_impact_frame)
        if onset >= impact or onset < 0 or (task, trial) in result:
            raise ValueError(f'Duplicate/invalid event at annotation row {index}')
        result[(task, trial)] = dict(label=1, fall_code=match[1],
                                    activity=str(row.Description).strip(),
                                    activity_key=match[1], onset=onset, impact=impact,
                                    annotation_row=int(index) + 2)
    return result


def resolve_label(task, trial, annotations):
    if (task, trial) in annotations:
        if task in ADL:
            raise ValueError('Fall annotation conflicts with documented ADL')
        return annotations[(task, trial)].copy()
    if task in ADL:
        return dict(label=0, activity=ADL[task], activity_key=f'ADL{task:02}',
                    onset=None, impact=None)
    raise ValueError(f'No verified annotation for task {task}, trial {trial}')


def physical_units(values):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 6 or not np.isfinite(values).all():
        raise ValueError('Expected finite N x 6 IMU values')
    return values * np.array([.00980665] * 3 + [np.pi / 180000] * 3)


def validate_trial(frames, values, event):
    if len(frames) < 2 or not np.isfinite(frames).all():
        raise ValueError('Missing frames')
    if not np.equal(frames, np.floor(frames)).all() or not (np.diff(frames) == 1).all():
        raise ValueError('FrameCounter must be consecutive integers')
    if values.shape != (len(frames), 6) or not np.isfinite(values).all():
        raise ValueError('Missing/nonfinite IMU')
    if event is not None and not frames[0] <= event['onset'] < event['impact'] <= frames[-1]:
        raise ValueError('Event outside recording')


def window_bounds(rows, length, stride=50):
    if length <= 0 or stride <= 0:
        raise ValueError('Window length/stride must be positive')
    return ((s, s + length - 1) for s in range(0, rows - length + 1, stride))


def window_label(start, end, event, horizon=100):
    if event is None:
        return 0
    if start <= event['impact'] <= end <= event['impact'] + horizon:
        return 1
    if end < event['onset'] - 50:
        return 0
    return -1


def subject_split(rows, seed=42, candidates=1000):
    """Balance subject-only partitions using metadata, never sensor/model scores.

    Missing activity coverage dominates duration/count imbalance. Hash-ordered
    subjects and seeded candidate permutations make ordering of raw files inert.
    """
    subjects = sorted({r['subject_id'] for r in rows}, key=lambda s: hashlib.sha256(
        f'UNIVRFall-v1|{seed}|{s}'.encode()).hexdigest())
    if len(subjects) < 11:
        raise ValueError('Need at least 11 subjects for 6 test + 5 folds')
    categories = sorted({r['activity_key'] for r in rows})
    matrix = np.zeros((len(subjects), len(categories) + 2))
    for row in rows:
        i = subjects.index(row['subject_id'])
        matrix[i, categories.index(row['activity_key'])] += 1
        matrix[i, -2] += row['rows'] if row['label'] == 0 else 0
        matrix[i, -1] += row['label']
    totals = matrix.sum(axis=0)
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(candidates):
        order = rng.permutation(len(subjects))
        groups = [order[:6]] + list(np.array_split(order[6:], 5))
        score = 0.
        for group in groups:
            observed = matrix[group].sum(axis=0)
            expected = totals * len(group) / len(subjects)
            score += float(np.square((observed - expected) / np.maximum(expected, 1)).sum())
            score += 1000 * int((observed[:len(categories)] == 0).sum())
        if best is None or score < best[0]:
            best = score, groups
    return {subjects[int(i)]: ('test' if group == 0 else f'fold{group-1}')
            for group, indices in enumerate(best[1]) for i in indices}


def fit_normalizer(recordings):
    count = 0
    sums, squares = np.zeros(6), np.zeros(6)
    for values in recordings:
        x = np.asarray(values, dtype=np.float64)
        count += len(x)
        sums += x.sum(axis=0)
        squares += (x * x).sum(axis=0)
    if not count:
        raise ValueError('Empty training set')
    mean = sums / count
    std = np.sqrt(np.maximum(squares / count - mean * mean, 0))
    return dict(count=count, mean=mean.tolist(), std=np.maximum(std, 1e-8).tolist())


def apply_normalizer(values, stats):
    return ((values - np.array(stats['mean'])) / np.array(stats['std'])).astype(np.float32)


def evaluate_sequence(ends, decisions, event):
    ends, decisions = np.asarray(ends), np.asarray(decisions, dtype=bool)
    if len(ends) != len(decisions):
        raise ValueError('Predictions and window ends differ')
    starts = ends[decisions & ~np.r_[False, decisions[:-1]]] if len(ends) else []
    if event is None:
        return dict(false_alarms=len(starts), detected=0, delay_frames=None, repeat_alarms=0)
    matched = [int(e) for e in starts if event['onset'] <= e <= event['impact'] + 100]
    # Early false alarms cannot be credited as detection; report separately.
    early = sum(e < event['onset'] for e in starts)
    repeats = len(starts) - early - int(bool(matched))
    return dict(false_alarms=int(early), detected=int(bool(matched)),
                delay_frames=matched[0] - event['impact'] if matched else None,
                repeat_alarms=int(repeats))
