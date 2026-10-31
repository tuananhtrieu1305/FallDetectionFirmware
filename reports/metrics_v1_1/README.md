# Kết quả bộ metric v1.1

- [Báo cáo dễ đọc](report.md)
- [Đầy đủ metric và khoảng tin cậy](metrics.json)
- [Từng trial/sự kiện](events.csv), [từng cảnh báo](alarms.csv)
- [Theo người](by_subject.csv), [theo hoạt động](by_activity.csv)
- [Đường threshold](threshold_curve.csv), [khóa lựa chọn](selection_lock.json)

Giá trị null nghĩa là không xác định/không có mẫu số. Một dòng events.csv là một trial, gồm cả ADL; lọc events=1 để xem lần ngã.
Báo cáo dùng score baseline đã lưu, không train CNN. Score development là OOF; test là model baseline fit trên 23 người development.
OnField nếu đã chạy nằm tại onfield/summary.json, tách riêng với laboratory. Đơn vị thời gian nguồn là danh nghĩa.

Chạy lại từ root project:

```powershell
python tools/datasets/run_metrics_v11.py --source <thu_muc_audit_trong_manifest> --out reports/metrics_v1_1
```

Model khác cung cấp cùng schema prediction, đầy đủ IGNORE và metadata manifest. Chỉ dùng development để chọn threshold; khóa trước khi evaluate test.
