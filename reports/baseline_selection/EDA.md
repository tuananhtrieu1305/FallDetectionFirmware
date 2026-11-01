# Phân tích development trước chọn baseline

Có 23 người, 916 trial, 456 sự kiện ngã, 16424 window và 1.5187 giờ ADL danh nghĩa. Window chồng lấn không phải quan sát độc lập. Người chỉ có trial ngã sau quarantine: ['SA10', 'SA11', 'SA12']; cần theo dõi confounding giữa người và nhãn.

IMU hữu hạn: True; gap frame: 0. Accel tối đa theo trục 3.997g, gyro 2111.20 dps. Không cắt/xóa tín hiệu cực trị; timestamp 100Hz chỉ danh nghĩa. Chất lượng nhãn/đơn vị/split đã audit ở dataset v1; chưa xác minh frame hướng đeo prototype.

Biểu đồ phân bố đặc trưng dùng median từng trial/lớp để giảm chi phối từ window chồng lấn; không dùng p-value với giả định window độc lập. Cùng trial có thể có cả pre-fall âm và impact dương; bảng không coi chúng độc lập. Biểu đồ trace chọn trial đầu tiên theo thứ tự manifest cho mỗi hoạt động, không chọn theo điểm dự đoán; chỉ là minh họa, không đại diện toàn bộ người.

## Quan sát → giả thuyết → ứng viên

- Các trace có đoạn va chạm/biến thiên biên độ: kiểm tra ngưỡng max độ lớn gia tốc làm mốc vật lý đơn giản. Hoạt động thường cũng có xung lớn nên không mặc định biên độ đủ phân biệt.
- Có 40 thống kê biên độ/biến thiên và tương quan giữa chúng: Logistic Regression có regularization kiểm tra tổ hợp tuyến tính, ít tham số, giữ đối chiếu baseline hiện có.
- Phân bố FALL/NON_FALL vẫn có thể chồng lấn và phụ thuộc trục/hoạt động: cây nhỏ kiểm tra luật phi tuyến/tương tác; Random Forest giới hạn độ sâu kiểm tra lợi ích kết hợp cây so với cây đơn. Không suy ra phi tuyến tốt hơn chỉ từ hình ảnh.
- Mẫu gồm 23 người, thời lượng âm hạn chế, nhiều window phụ thuộc: giới hạn độ sâu/min leaf, không chuyển sang mạng sâu trước khi có bằng chứng từ so sánh.

Khóa nhóm ứng viên: ngưỡng gia tốc + 13 cấu hình (3 LR, 6 cây, 4 forest), cùng 40 feature và cùng 5 fold. Mean/std và trọng số chỉ fit trên train của fold. Không chọn đặc trưng từ toàn bộ development rồi gọi OOF là ước lượng độc lập; vòng này giữ feature cố định. So sánh ablation acc-only/gyro-only mang tính chẩn đoán, không mở rộng tìm kiếm theo test.

## Cần đọc cùng

- [Thống kê theo người](counts_by_subject_id.csv), [theo fold](counts_by_partition.csv), [theo hoạt động](counts_by_activity_key.csv).
- [Chất lượng từng trial](quality_by_trial.csv), [trước/sau impact](pre_post_impact.csv).
- [Phân bố đặc trưng](plots/feature_distributions.png), [tương quan](plots/feature_correlation.png), [trace hoạt động](plots/activity_traces.png).
- [Lỗi OOF baseline hiện tại](existing_oof_error_trials.csv); không dùng lỗi test/OnField để thiết kế model.

Báo cáo này và checksum được tạo trước vòng so sánh mới. EDA không xác định được model tốt nhất; thí nghiệm development kiểm chứng các giả thuyết trên. Không có kết luận dự đoán ngã trước impact.
