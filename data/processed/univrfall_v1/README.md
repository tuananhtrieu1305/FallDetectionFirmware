# UNIVRFall v1 — dữ liệu đã xử lý, đọc tại đây

**Mở `dataset.csv` để xem toàn bộ dataset có nhãn và giá trị IMU thật.**
Mở `examples/fall_window.csv` để xem một window dưới dạng 100 dòng × 6 kênh dễ đọc.

| File | Dùng để làm gì |
|---|---|
| [dataset.csv](dataset.csv) | 17,813 window có nhãn; một dòng là một window, chứa 600 giá trị IMU và thông tin nhãn/người/split |
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

`train`: 11,243 window; `validation`: 2,943; `test`: 3,627.
Chọn fold0 làm validation để có một cách nạp cố định; không chia lại người hoặc chỉnh theo kết quả test.
2,873 window IGNORE được loại khỏi bản dành cho huấn luyện này, không đổi thành NON_FALL.
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
