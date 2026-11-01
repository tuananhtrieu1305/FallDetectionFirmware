# Phân tích dữ liệu và chọn baseline

- [Kết luận và bảng so sánh](REPORT.md), [EDA trước train](EDA.md)
- [CSV so sánh](comparison.csv), [prediction OOF](oof_predictions.csv)
- [Khóa thí nghiệm](experiment_lock.json), [khóa lựa chọn](selection_lock.json), [model JSON](selected_model.json)
- [Seed stability](seed_stability.csv), [ablation cảm biến](sensor_ablation.json), [so sánh theo người](paired_comparison.json)
- [Test](test_metrics.json), [OnField riêng](onfield/summary.json), [chi phí host](host_cost.json)
- [Nghiệm thu](completion_audit.json), [test](tests.txt), [coverage](test_coverage.json)

Chạy từ root project, lấy SOURCE từ trường source trong data/processed/univrfall_v1/manifest.json:

```powershell
python tools/datasets/analyze_baseline_data.py --source SOURCE
python tools/datasets/select_baseline.py --source SOURCE
python tools/datasets/diagnose_baseline_data.py --source SOURCE
python reports/baseline_selection/run_field_acceptance.py
python tools/datasets/report_baseline_selection.py
python tools/datasets/verify_baseline_selection.py --source SOURCE
python -m unittest discover -s tools/datasets -p 'test_*.py'
```

Khi đọc score CSV để đếm lại ở threshold trùng score, dùng `pd.read_csv(path, float_precision="round_trip")`; hoặc đọc score NPZ giữ float64 nguyên vẹn trong cache. Parser mặc định có thể làm đổi chữ số cuối và lật quyết định đúng tại ngưỡng.
Cache score/fold/threshold curve tồn tại trên đĩa, bị bỏ qua trong Git và có thể tạo lại. Model JSON xuất nội bộ đã đối chiếu prediction với sklearn. Chưa train CNN.
