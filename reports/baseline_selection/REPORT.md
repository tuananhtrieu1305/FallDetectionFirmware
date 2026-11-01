# Kết quả phân tích và lựa chọn baseline

**Chọn lr_C0.1: Logistic Regression C=0.1 + StandardScaler + balanced weights + 40 đặc trưng thống kê.** Ngưỡng 0.98477275965882582, window100×6, stride50. Đây là tốt nhất trong nhóm đã khóa, chưa phải tối ưu cho mọi model hoặc phần cứng.

## Cơ sở từ dữ liệu
EDA ghi trước thí nghiệm: 23 người, 916 trial, 456 lần ngã; 16.424 window gồm 2.238 IGNORE; 1,5187 giờ ADL danh nghĩa. Đặc trưng cực trị/biến thiên của accel và gyro khác biệt mô tả giữa lớp, tạo cơ sở thử model thống kê có regularization trước model chuỗi sâu. Biểu đồ median/trial không chứng minh tách lớp hoàn toàn.
Window chồng lấn không độc lập; SA10–SA12 chỉ còn trial ngã nên có nguy cơ confounding giữa người và nhãn. Tín hiệu hữu hạn, không có gap frame ở development; clock100Hz vẫn danh nghĩa, biên độ gần4g và hướng gắn prototype chưa xác minh. Xem [EDA.md](EDA.md), [trace sáu kênh ví dụ](plots/six_channels_F03.png), [phân bố theo người](features_by_subject.csv).

## So sánh cùng điều kiện
| Cấu hình | Phát hiện /456 | Recall | FA/h | P95 trễ danh nghĩa |
|---|---:|---:|---:|---:|
| acc_threshold | 151 | 33.11% | 0.658 | 0.470s |
| dt_d3_l10 | 14 | 3.07% | 0.658 | 0.987s |
| dt_d3_l30 | 79 | 17.32% | 0.658 | 0.570s |
| dt_d5_l10 | — | Không có ngưỡng phát hiện ngã đạt ≤1FA/h | — | — |
| dt_d5_l30 | 246 | 53.95% | 0.658 | 0.558s |
| dt_d8_l10 | — | Không có ngưỡng phát hiện ngã đạt ≤1FA/h | — | — |
| dt_d8_l30 | 428 | 93.86% | 0.658 | 0.540s |
| lr_C0.1 | 449 | 98.46% | 0.658 | 0.486s |
| lr_C1.0 | 444 | 97.37% | 0.658 | 0.480s |
| lr_C10.0 | 448 | 98.25% | 0.658 | 0.490s |
| rf_d10_l10 | 439 | 96.27% | 0.658 | 0.510s |
| rf_d10_l30 | 423 | 92.76% | 0.658 | 0.549s |
| rf_d5_l10 | 425 | 93.20% | 0.658 | 0.548s |
| rf_d5_l30 | 433 | 94.96% | 0.658 | 0.514s |

Ngưỡng max độ lớn gia tốc là mốc vật lý; LR kiểm tra tổ hợp tuyến tính, cây kiểm tra luật phi tuyến, forest kiểm tra lợi ích kết hợp cây. Tất cả dùng cùng phân chia theo người, cùng window và cơ chế cảnh báo. Cây/forest không cải thiện recall so với LR ở ngân sách1/h trong bộ đặc trưng này.
LR C=0.1 phát hiện 449/456, bỏ sót 7, có 1 báo nhầm trên 1.5187 giờ ADL. So với C=1, chênh lệch recall 1.10 điểm phần trăm, khoảng bootstrap theo người [0.0, 0.02466367713004484]. Đây là kết quả lựa chọn development, không phải kiểm định độc lập; CI chỉ có điều kiện trên prediction cố định.
Seed42/43/44: [seed_stability.csv](seed_stability.csv). LR giữ nguyên kết quả; cây có seed không có điểm vận hành khả thi. Không chọn seed theo test.

## Ablation và lỗi còn lại
Chẩn đoán LR C=1: acc-only recall 98.90%, gyro-only 61.84%. Acc-only cao hơn nhóm40feature cho thấy cần kiểm chứng thêm lựa chọn cảm biến/đặc trưng trước khi tăng độ phức tạp. Đây là chẩn đoán ngoài grid chính; chưa tự thay baseline được khóa. Không suy ra nên bỏ gyro trên phần cứng thật chỉ từ dataset này.
Trong 7 lần ngã bỏ sót, 4 thuộc SA36; một cảnh báo nhầm là S22T15R01 (ADL15, collapse into chair). Đồ thị lỗi có xung gia tốc nhưng gyro tương đối thấp ở một số ca; đây là quan sát, chưa chứng minh nguyên nhân. Nên kiểm tra giả thuyết trọng số gyro/đặc trưng và khả năng khái quát theo người trước khi tăng độ phức tạp.
Xem [các lỗi OOF](selected_oof_errors.csv), [đồ thị lỗi](plots/selected_oof_errors.png), [tương quan](plots/feature_correlation.png), [dịch chuyển theo người](plots/subject_feature_shift.png), [trước/sau impact](pre_post_impact.csv). Không suy ra nguyên nhân tư thế từ IMU đơn thuần. Nhóm lỗi theo người/hoạt động nằm trong development_by_subject_id.csv và development_by_activity_key.csv.

## Benchmark sau khóa lựa chọn
Test: 117/117, FA=0 trên 0.3905 giờ ADL; median/P95 delay=0.24/0.47s danh nghĩa. Cận trên Poisson95% của FA/h là 7.67; thời lượng âm quá ngắn để kết luận báo nhầm thực thấp.
OnField đủ18file: 30/54.88 giờ, 0.547 cảnh báo/source-negative hour. Không retune ngưỡng; đủ18file khớp giữa chunks100000/37123. Nhãn âm/ID người chưa được xác minh độc lập.
Test/OnField từng được xem trong baseline trước; đây là benchmark cố định, chưa phải dữ liệu xác nhận cuối mới. Chi phí máy tính: [host_cost.json](host_cost.json); RAM và latency ESP32 NOT MEASURED.

## Quyết định
Giữ LR C=0.1 +40feature làm baseline chính của vòng so sánh. Ưu tiên xác nhận acc-only và thu ADL có nhãn từ đúng phần cứng/vị trí đeo để kiểm tra lệch miền. Chỉ thử CNN khi lỗi còn lại tạo giả thuyết rõ về lợi ích học thứ tự thời gian; hiện chưa có lý do bắt buộc chuyển CNN.
