# Dataset của project

**Dữ liệu đã xử lý nằm trong `data/processed/univrfall_v1/`.**

- [Mở dataset.csv — đầy đủ giá trị IMU và nhãn](processed/univrfall_v1/dataset.csv)
- [Mở ví dụ một window ngã — 100 dòng, 6 kênh](processed/univrfall_v1/examples/fall_window.csv)
- [Mở ví dụ một window không ngã](processed/univrfall_v1/examples/non_fall_window.csv)
- [Cách đọc file và nạp vào model](processed/univrfall_v1/README.md)
- [Metric và quy tắc đánh giá model đã chốt](../docs/dataset_research/METRICS_PROTOCOL.md)
- [Kết quả kiểm tra bộ metric và baseline v1.1](../reports/metrics_v1_1/README.md)

CSV có một dòng cho mỗi window, gồm 600 giá trị IMU, nhãn, người và tập chia. NPZ chứa cùng dữ liệu dưới dạng ma trận để train nhanh hơn.

Bản tiện dùng này giữ các window có nhãn 0/1, dùng fold0 làm validation, fold1–4 làm train và giữ nguyên sáu người test. Nhãn IGNORE không được dùng để train. Dữ liệu vẫn ở đơn vị vật lý; cách chuẩn hóa nằm trong README đi kèm.

CSV đầy đủ và tensor được bỏ qua trong Git vì kích thước lớn, nhưng tồn tại trên đĩa trong project. README và ví dụ nhỏ được lưu cùng code. Dữ liệu nguồn và bản audit đầy đủ vẫn nằm ở đường dẫn ghi trong `manifest.json` của bản xuất.

Tạo lại từ bản đã audit:

```powershell
python tools/datasets/export_dataset.py --source 'C:/Users/Admin/.codex/visualizations/2026/10/31/01a19255-0f78-7130-b6ac-088fb917fbd1/dataset-research/univrfall_binary_v1' --out data/processed/univrfall_v1
```

- [Phân tích dữ liệu và lựa chọn baseline](../reports/baseline_selection/README.md)
- [Phân tích lỗi baseline và hướng làm tiếp theo](../reports/baseline_analysis/README.md)
