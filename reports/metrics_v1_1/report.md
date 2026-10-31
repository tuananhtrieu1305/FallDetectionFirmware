# Báo cáo baseline theo metric v1.1

Threshold: 0.99671361547521276; chọn từ OOF development, ≤1 FA/giờ danh nghĩa.

| Tập | TP / số ngã | Recall | Macro recall | FA / giờ ADL | FA/h | Median / P95 delay (s danh nghĩa) |
|---|---:|---:|---:|---:|---:|---:|
| development | 444/456 | 0.9736842105263158 | 0.9732731037078864 | 1/1.518711 | 0.6584530742442422 | 0.25 / 0.48 |
| test | 117/117 | 1.0 | 1.0 | 0/0.390469 | 0.0 | 0.24 / 0.47 |

Các khoảng tin cậy, Recall@0.5s, alarm-active fraction, metric window và giới hạn nằm trong [metrics.json](metrics.json).
Đối chiếu metric cũ ở cùng threshold: PASS. Ngưỡng mới có thể khác do quét toàn bộ score và đổi tie-break.
Test đã từng được xem ở baseline; thời gian nguồn danh nghĩa; chưa đo RAM/latency thiết bị.
