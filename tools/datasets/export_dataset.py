"""Export a readable, project-local view of the audited 100-sample dataset.

Each CSV row contains one complete window (600 numeric IMU fields), its label,
subject and split. Only supervised windows are included. Original continuous
evaluation data remains at --source; no labels or subject partitions are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

CHANNELS = ['ax', 'ay', 'az', 'gx', 'gy', 'gz']


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def export_dataset(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Export destination must differ from the audited source')
    with np.load(source / 'windows_100.npz') as data:
        original_x, original_y = data['X'], data['y']
    index = pd.read_csv(source / 'window_index_100.csv')
    if (original_x.shape != (len(original_y), 100, 6) or len(index) != len(original_y)
            or not np.array_equal(index.y.to_numpy(), original_y)):
        raise ValueError('Source tensor and index do not match')
    if not np.isfinite(original_x).all() or not np.isin(original_y, [-1, 0, 1]).all():
        raise ValueError('Invalid source values or labels')
    partition_map = {f'fold{i}': 'validation' if i == 0 else 'train' for i in range(5)}
    partition_map['test'] = 'test'
    if not set(index.partition).issubset(partition_map):
        raise ValueError('Unknown source partition')
    eligible = original_y >= 0
    x = original_x[eligible].astype(np.float32)
    y = original_y[eligible].astype(np.int8)
    metadata = index.loc[eligible].reset_index(drop=True)
    metadata.insert(0, 'source_window_row', np.flatnonzero(eligible))
    metadata.insert(0, 'dataset_row', np.arange(len(metadata)))
    metadata.insert(2, 'split', metadata.partition.map(partition_map))
    metadata.insert(3, 'label_name', np.where(y == 1, 'FALL', 'NON_FALL'))
    subjects = {split: set(metadata.loc[metadata.split == split, 'subject_id'])
                for split in ['train', 'validation', 'test']}
    if any(subjects[a] & subjects[b] for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]):
        raise ValueError('Subject leakage in export')
    destination.mkdir(parents=True, exist_ok=True)
    examples = destination / 'examples'
    examples.mkdir(exist_ok=True)
    columns = [f'{channel}_{step:03}' for step in range(100) for channel in CHANNELS]
    frame = pd.concat([metadata, pd.DataFrame(x.reshape(len(x), 600), columns=columns)], axis=1)
    csv_path = destination / 'dataset.csv'
    frame.to_csv(csv_path, index=False, float_format='%.9g', lineterminator='\n')
    metadata.to_csv(destination / 'index.csv', index=False, lineterminator='\n')
    np.savez_compressed(destination / 'dataset.npz', X=x, y=y,
                        split=metadata.split.to_numpy(dtype='U10'),
                        source_window_row=metadata.source_window_row.to_numpy(np.int64))
    for name in ['normalizers.json', 'splits.json']:
        shutil.copyfile(source / name, destination / name)
    for label, name in [(0, 'non_fall_window'), (1, 'fall_window')]:
        candidates = np.flatnonzero(y == label)
        if not len(candidates):
            continue
        row = int(candidates[0])
        example = pd.DataFrame(x[row], columns=CHANNELS)
        example.insert(0, 'sample_in_window', np.arange(100))
        example.to_csv(examples / f'{name}.csv', index=False, float_format='%.9g', lineterminator='\n')
        (examples / f'{name}.json').write_text(metadata.iloc[row].to_json(indent=2), encoding='utf-8')
    # Exhaustive readback catches CSV precision loss, channel order and row drift.
    decoded = pd.read_csv(csv_path, dtype={c: np.float32 for c in columns}, float_precision='round_trip')
    np.testing.assert_array_equal(decoded[columns].to_numpy().reshape(-1, 100, 6), x)
    np.testing.assert_array_equal(decoded.y.to_numpy(), y)
    np.testing.assert_array_equal(decoded.source_window_row.to_numpy(), np.flatnonzero(eligible))
    counts = metadata.groupby('split').size().to_dict()
    report = dict(version='univrfall_v1_readable', rows=len(x), window_samples=100,
                  channels=CHANNELS, feature_columns=columns, excluded_ignore_windows=int((~eligible).sum()),
                  split_counts={k: int(v) for k, v in counts.items()},
                  class_counts={str(label): int((y == label).sum()) for label in [0, 1]},
                  split_rule='validation=original fold0; train=fold1..4; test=original six held-out subjects',
                  units=dict(accel='m/s2 including gravity', gyro='rad/s'), normalization_applied=False,
                  normalizer_to_use='normalizers.json -> fold0 for this train/validation split',
                  source=str(source), source_tensor_sha256=sha(source / 'windows_100.npz'),
                  source_index_sha256=sha(source / 'window_index_100.csv'),
                  csv_sha256=sha(csv_path), npz_sha256=sha(destination / 'dataset.npz'),
                  verification='PASS: every CSV signal value and label equals the exported NPZ/source window')
    (destination / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    readme = f'''# UNIVRFall v1 — dữ liệu đã xử lý, đọc tại đây

**Mở `dataset.csv` để xem toàn bộ dataset có nhãn và giá trị IMU thật.**
Mở `examples/fall_window.csv` để xem một window dưới dạng 100 dòng × 6 kênh dễ đọc.

| File | Dùng để làm gì |
|---|---|
| [dataset.csv](dataset.csv) | {len(x):,} window có nhãn; một dòng là một window, chứa 600 giá trị IMU và thông tin nhãn/người/split |
| [dataset.npz](dataset.npz) | Cùng dữ liệu dưới dạng `X[N,100,6]`, `y[N]`, `split[N]` để nạp bằng NumPy |
| [index.csv](index.csv) | Bảng tra cứu; không chứa tín hiệu IMU |
| [examples/fall_window.csv](examples/fall_window.csv) | Một window FALL: 100 mẫu, cột ax/ay/az/gx/gy/gz |
| [examples/non_fall_window.csv](examples/non_fall_window.csv) | Một window NON_FALL |
| [normalizers.json](normalizers.json) | Mean/std chỉ fit trên train; dùng khóa `fold0` với split tiện dùng này |
| [manifest.json](manifest.json) | Đơn vị, số lượng, checksum và cách ánh xạ về bản đã audit |

## Cách đọc dataset.csv

- `y`: 0 = NON_FALL, 1 = FALL. `label_name` là tên nhãn.
- `split`: train / validation / test. `partition` giữ fold gốc để chạy cross-validation.
- `subject_id`, `trial_id`: người và lần đo nguồn.
- `ax_000, ay_000, az_000, gx_000, gy_000, gz_000`: mẫu đầu của window.
- Tương tự đến `ax_099, ..., gz_099`: mẫu cuối. Tổng cộng 600 cột tín hiệu.
- `dataset_row` là vị trí trong NPZ này; `source_window_row` là vị trí trong NPZ gốc.
- Gia tốc m/s² có trọng lực, gyro rad/s; chưa áp dụng chuẩn hóa thống kê. Trục vẫn theo nguồn.

## Chia tập

`train`: {counts.get('train', 0):,} window; `validation`: {counts.get('validation', 0):,}; `test`: {counts.get('test', 0):,}.
Chọn fold0 làm validation để có một cách nạp cố định; không chia lại người hoặc chỉnh theo kết quả test.
{int((~eligible).sum()):,} window IGNORE được loại khỏi bản dành cho huấn luyện này, không đổi thành NON_FALL.
Bản đầy đủ dùng để đánh giá chuỗi liên tục vẫn được giữ tại nguồn ghi trong manifest.
Clock laboratory vẫn là 100 Hz danh định chưa xác minh; không coi 100 mẫu là đúng một giây vật lý đã chứng minh.

## Nạp bằng Python

```python
import json
import numpy as np

with np.load('data/processed/univrfall_v1/dataset.npz') as data:
    X, y, split = data['X'], data['y'], data['split']
with open('data/processed/univrfall_v1/normalizers.json') as file:
    stats = json.load(file)['fold0']
X = ((X - np.array(stats['mean'])) / np.array(stats['std'])).astype(np.float32)
X_train, y_train = X[split == 'train'], y[split == 'train']
X_valid, y_valid = X[split == 'validation'], y[split == 'validation']
X_test, y_test = X[split == 'test'], y[split == 'test']
```

Giữ test riêng khi chọn model/ngưỡng. Bản này phục vụ huấn luyện theo window; đánh giá báo động liên tục dùng bản đầy đủ có cả IGNORE.
Nguồn UNIVRFall: https://zenodo.org/records/18346755 — Ali, Demrozi, Turetta và Pravadelli, CC BY 4.0.
'''
    (destination / 'README.md').write_text(readme, encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['rows', 'split_counts', 'excluded_ignore_windows', 'verification']}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('data/processed/univrfall_v1'))
    args = parser.parse_args()
    export_dataset(args.source, args.out)
