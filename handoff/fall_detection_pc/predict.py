"""Standalone, frozen Logistic Regression inference for 100 Hz IMU CSV."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
CHANNELS = ['ax', 'ay', 'az', 'gx', 'gy', 'gz']
LENGTH, STRIDE = 100, 50


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def features(x):
    x = np.asarray(x, dtype=np.float64)
    x = np.concatenate([x, np.linalg.norm(x[:, :, :3], axis=2, keepdims=True),
                        np.linalg.norm(x[:, :, 3:], axis=2, keepdims=True)], axis=2)
    return np.concatenate([x.mean(axis=1), x.std(axis=1), x.min(axis=1),
                           x.max(axis=1), np.sqrt((x*x).mean(axis=1))], axis=1)


def score(model, f):
    z = ((f - np.asarray(model['mean'])) / np.asarray(model['scale'])) @ np.asarray(model['coef']) + model['intercept']
    # Stable sigmoid without a scipy/sklearn runtime dependency.
    e = np.exp(-np.abs(z))
    return np.where(z >= 0, 1 / (1 + e), e / (1 + e))


def alarm_edges(scores, threshold):
    positive = np.asarray(scores) >= threshold
    return positive & ~np.r_[False, positive[:-1]] if len(positive) else positive


def read_input(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = ['timestamp_us'] + CHANNELS
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError('CSV requires timestamp_us,ax,ay,az,gx,gy,gz')
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('Duplicate column names')
        has_seq = 'seq' in reader.fieldnames
        times, signals, seq = [], [], []
        for line, row in enumerate(reader, 2):
            try:
                times.append(int(row['timestamp_us']))
                signals.append([float(row[c]) for c in CHANNELS])
                if has_seq:
                    seq.append(int(row['seq']))
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f'Invalid numeric value at CSV line {line}') from exc
    if not times:
        raise ValueError('CSV has no samples')
    try:
        times = np.asarray(times, dtype=np.int64)
        seq = np.asarray(seq, dtype=np.int64) if has_seq else None
    except OverflowError as exc:
        raise ValueError('Timestamp/seq outside int64 range') from exc
    x = np.asarray(signals, dtype=np.float64)
    if np.any(times < 0) or not np.isfinite(x).all():
        raise ValueError('Negative timestamp or NaN/Inf in IMU data')
    dt = np.diff(times)
    if np.any(dt <= 0):
        raise ValueError('Timestamps must increase strictly; input is never sorted automatically')
    if len(dt) and not 9500 <= np.median(dt) <= 10500:
        raise ValueError('Expected 100 Hz: median timestamp interval must be 9500..10500 us')
    breaks = (dt < 5000) | (dt > 15000)
    if seq is not None:
        breaks |= np.diff(seq) != 1
    starts = np.r_[0, np.flatnonzero(breaks) + 1]
    stops = np.r_[starts[1:], len(times)]
    return x, times, list(zip(starts.tolist(), stops.tolist()))


def write_csv(path, fields, rows):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(input_path, output_path):
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    # Never overwrite raw input by selecting its directory as output.
    outputs = [output_path / n for n in ['predictions.csv', 'alarms.csv', 'summary.json', 'plot.png']]
    if input_path in outputs:
        raise ValueError('Output would overwrite input CSV')
    model_path = HERE / 'model.json'
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    if sha(model_path) != manifest['model_sha256']:
        raise ValueError('Model checksum mismatch')
    model = json.loads(model_path.read_text(encoding='utf-8'))
    x, times, segments = read_input(input_path)
    predictions, alarms = [], []
    unscored = 0
    for segment, (start, stop) in enumerate(segments):
        offsets = list(range(start, stop - LENGTH + 1, STRIDE))
        if not offsets:
            unscored += stop - start
            continue
        # Bounded batches: no full recording-sized window tensor.
        values = []
        for batch in range(0, len(offsets), 1024):
            windows = np.stack([x[i:i+LENGTH] for i in offsets[batch:batch+1024]])
            values.extend(score(model, features(windows)).tolist())
        edges = alarm_edges(values, model['threshold'])
        for i, value, edge in zip(offsets, values, edges):
            row = dict(segment=segment, start_row=i, end_row=i+LENGTH-1,
                       start_us=int(times[i]), end_us=int(times[i+LENGTH-1]),
                       score=value, threshold=model['threshold'],
                       prediction='FALL' if value >= model['threshold'] else 'NON_FALL')
            predictions.append(row)
            if edge:
                alarms.append(dict(segment=segment, timestamp_us=row['end_us'], score=value))
        unscored += stop - (offsets[-1] + LENGTH)
    output_path.mkdir(parents=True, exist_ok=True)
    write_csv(outputs[0], ['segment','start_row','end_row','start_us','end_us','score','threshold','prediction'], predictions)
    write_csv(outputs[1], ['segment','timestamp_us','score'], alarms)
    dt = np.diff(times)
    summary = dict(schema_version=1, samples=len(x), windows=len(predictions), alarms=len(alarms),
                   segments=len(segments), discontinuities=len(segments)-1,
                   unscored_tail_or_short_segment_samples=unscored,
                   median_interval_us=float(np.median(dt)) if len(dt) else None,
                   min_interval_us=int(dt.min()) if len(dt) else None,
                   max_interval_us=int(dt.max()) if len(dt) else None,
                   input_sha256=sha(input_path), model_sha256=sha(model_path),
                   threshold=model['threshold'], window_samples=LENGTH, stride_samples=STRIDE,
                   ground_truth='unknown; flags and filenames are not labels',
                   units='acceleration m/s2 including gravity; gyroscope rad/s',
                   axes='Input axes retained; source-to-hardware alignment not verified')
    outputs[2].write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    plot(outputs[3], x, times, segments, predictions, alarms, model['threshold'])
    return summary


def plot(path, x, times, segments, predictions, alarms, threshold):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    for a, b in segments:
        t = (times[a:b] - times[0]) / 1e6
        axes[0].plot(t, np.linalg.norm(x[a:b, :3], axis=1), color='steelblue')
        axes[1].plot(t, np.linalg.norm(x[a:b, 3:], axis=1), color='darkorange')
    for segment in range(len(segments)):
        rows = [r for r in predictions if r['segment'] == segment]
        axes[2].plot([(r['end_us']-int(times[0]))/1e6 for r in rows], [r['score'] for r in rows], color='green')
    axes[2].axhline(threshold, color='red', linestyle='--', label=f'Threshold {threshold:.6f}')
    for row in alarms:
        for ax in axes:
            ax.axvline((row['timestamp_us']-int(times[0]))/1e6, color='red', alpha=.35)
    for ax, label in zip(axes, ['Acceleration norm (m/s2)', 'Gyroscope norm (rad/s)', 'Model score']):
        ax.set_ylabel(label)
        ax.grid(alpha=.2)
    axes[2].set_ylim(-.02, 1.02)
    axes[2].legend()
    axes[2].set_xlabel('Seconds since first sample; alarm = window end')
    fig.suptitle('Frozen baseline predictions - ground truth not supplied')
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.input, args.output)
    except (ValueError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    print(f"Samples: {result['samples']}; windows: {result['windows']}; alarms: {result['alarms']}")
    print(f'Results: {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
