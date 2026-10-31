# Dùng bộ metric v1.1

Bộ tính dùng chung cho score của Logistic Regression, CNN hoặc model khác. Không đọc nhãn ngã để tạo cảnh báo; nhãn chỉ dùng chấm điểm sau suy luận.

## Chạy lại nghiệm thu đầy đủ

Từ root project trong PowerShell:

```powershell
$datasetManifest = Get-Content data/processed/univrfall_v1/manifest.json -Raw | ConvertFrom-Json
$datasetSource = $datasetManifest.source
$rawSource = Join-Path (Split-Path $datasetSource) 'raw/univrfall'
python tools/datasets/verify_metrics_v11.py --source $datasetSource --raw $rawSource --out reports/metrics_v1_1
python -m unittest discover -s tools/datasets -p 'test_*.py'
```

Lệnh nghiệm thu dùng score baseline đã lưu, không train lại model. Mặc định bootstrap 10.000 lần theo người; quét toàn bộ score development phân biệt để chọn ngưỡng.

## Cấp prediction từ CNN sau này

```python
import sys
sys.path.insert(0, 'tools/datasets')
from metrics_v11 import select_threshold, evaluate

# records_dev / records_test là manifest đã lọc đúng split.
# Giữ recording_id gốc trong mỗi record trước khi lọc.
# index_dev/index_test: recording_id, end_frame, y, và metadata nếu có.
# score_dev: OOF theo người; score_test: model cuối fit trên development.
# Các bảng phải đủ cả window IGNORE và sắp theo manifest/segment/frame.
selected, curve = select_threshold(records_dev, index_dev, score_dev)
if selected is None:
    raise RuntimeError('Không có điểm vận hành phát hiện ngã đạt ngân sách FA/h')
threshold = selected['threshold']  # Lưu lock/hash trước bước đánh giá test.
metrics = evaluate(records_test, index_test, score_test, threshold)
```

Một record tối thiểu có `recording_id`, `subject_id`, `trial_id`, `activity_key`, `partition`, `rows`, `frame_first`, `event`. `event=None` cho ADL đã xác minh; trial ngã dùng `event={'onset': O, 'impact': I}`. Dữ liệu mất đoạn dùng `segments=[{'first_frame': F, 'rows': N}, ...]`; rows của record bằng tổng số mẫu các segment. Frame phải là số nguyên và segment không chồng lấn. Khởi tạo window và cảnh báo lại sau gap.

`y=-1` không tham gia metric window nhưng prediction đó vẫn tham gia đếm cảnh báo. Thiếu prediction của một window đủ điều kiện là lỗi. Trial ngắn không sinh được window vẫn phải có trong manifest để giữ đúng mẫu số sự kiện.

Mean/std, augmentation, class weights, early stopping và OOF là trách nhiệm pipeline train. Evaluator kiểm tra schema, số window, thứ tự, segment, metadata và việc test không đi vào chọn ngưỡng; nó không thể chứng minh model chưa học test chỉ từ một vector score. Cần giữ provenance của quá trình train.

## Đọc kết quả

- `metrics.json`: metric development/test, CI, counts và giới hạn.
- `events.csv`: một dòng/trial; `events=1` là trial có ngã, `detected=0` là bỏ sót. Delay trống nghĩa là chưa phát hiện, không phải trễ 0 giây.
- `alarms.csv`: từng cạnh cảnh báo; `matched_or_repeat` được đối chiếu với trial để phân biệt cảnh báo đúng đầu tiên và các lần lặp.
- `threshold_curve.csv`: chỉ từ development; FA/h theo số cạnh có thể không đơn điệu khi thay threshold.
- `onfield/summary.json`: source-negative theo mô tả nguồn; không có recall và không bootstrap theo người vì ID chưa xác minh. Mỗi JSON file kèm số giây gap bị loại, raw hash và code/model hash.
- `verification.json`: parity với evaluator cũ và chunk invariance trên đủ 18 file thật, kèm checksum artifact.
- `test_output.txt`, `test_coverage.json`: kiểm tra tự động và coverage của ba module triển khai.
- `dependency_audit.json`: audit các dependency trực tiếp đã pin; không phải audit mọi package trong Python toàn máy.

Thời gian nguồn là danh nghĩa, chưa phải số đo end-to-end trên ESP32. Các số đo RAM, latency suy luận thiết bị và độ trễ truyền tin hiện NOT MEASURED. Khi đổi model/runtime hoặc quantization phải đánh giá lại. Test/OnField đã từng xem ở baseline nên không coi là bộ xác nhận cuối hoàn toàn mới.
