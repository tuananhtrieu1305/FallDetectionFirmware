# Phân tích kết quả baseline đã có

**Đọc [REPORT.md](REPORT.md) để xem kết luận và bước ưu tiên tiếp theo.**

- [Metric theo window/sự kiện/thời gian](metric_summary.csv)
- [8 ca lỗi](error_cases.csv), [các window liên quan](case_windows.csv), [trial đúng để đối chiếu](case_comparisons.csv)
- [Theo người](by_subject.csv), [theo hoạt động](by_activity.csv)
- [So sánh model](model_comparison.csv), [danh sách sự kiện cứu/mất](model_pairs.json)
- [Acc-only/gyro-only](sensor_comparison.json), [kết quả từng sự kiện](sensor_event_outcomes.csv)
- [Đánh đổi threshold cũ](threshold_tradeoff.csv), [OnField từng file](onfield_by_file.csv)
- [Mức sẵn sàng dữ liệu phần cứng](hardware_readiness.json), [đối chiếu/hash](verification.json)

Chạy lại từ root repo:

```powershell
python tools/datasets/analyze_baseline_results.py
python -m unittest discover -s tools/datasets -p 'test_analyze_baseline_results.py'
```

Lượt nghiệm thu đã lưu test log/coverage và dependency audit tại đây.
Đối chiếu độc lập sau khi tạo báo cáo: `python tools/datasets/verify_result_analysis.py`.
Verifier yêu cầu test log/coverage và audit hiện có; nếu chạy lại test hoặc audit thì chạy verifier sau cùng để cập nhật hash.

Script lấy đường dẫn nguồn từ manifest dataset và chỉ đọc report/prediction đã lưu.
Không train lại, không đổi model/threshold. Metric chưa xác định ghi N/A/null.
CSV score phải đọc với float_precision=round_trip để giữ nguyên quyết định ở threshold trùng score.
Kiểm tra tích hợp chặn estimator.fit và chọn threshold mới; không dùng model23người để giải thích score OOF.
Các hình mỗi ca lỗi nằm trong figures; thời gian là danh nghĩa của nguồn.
