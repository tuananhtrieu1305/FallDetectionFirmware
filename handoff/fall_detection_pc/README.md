# Chạy thử model phát hiện ngã trên PC

Gói này nhận CSV cảm biến và xuất điểm dự đoán cùng mốc cảnh báo. Model là Logistic Regression C=0.1 đã train; ngưỡng cố định `0.9847727596588258`. Không cần dataset train, scikit-learn hay ESP-IDF.

## 1. Cài và chạy sample trên Windows

Cài Python **3.11 trở lên** (đã kiểm tra runtime 3.13). Mở PowerShell trong thư mục có README này:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe predict.py --input examples/sensor_sample_4000.csv --output results/sample
```

Lần cài dependencies cần Internet. Sau đó chạy dự đoán offline. Nếu clone repo:

```powershell
git clone --branch Tien https://github.com/tuananhtrieu1305/FallDetectionFirmware.git
cd FallDetectionFirmware/handoff/fall_detection_pc
```

Sample gồm 4.000 mẫu đo thật, phải tạo **79 window, 0 cảnh báo**. Tham khảo `example_results/`. Metadata ghi trigger thử nghiệm, nhãn thật chưa biết; kết quả này chỉ kiểm tra chương trình hoạt động. `flags=3` không phải nhãn ngã.

## 2. Chạy CSV mới từ thiết bị

```powershell
.\.venv\Scripts\python.exe predict.py --input D:/hardware_test/nga_01.csv --output results/nga_01
```

Mỗi file chạy một lần, dùng thư mục output riêng. CSV có header tối thiểu:

```csv
timestamp_us,ax,ay,az,gx,gy,gz
```

- `timestamp_us`: số nguyên microsecond, tăng liên tục theo clock thiết bị.
- `ax,ay,az`: m/s² **có trọng lực**. `gx,gy,gz`: rad/s.
- Tần suất 100 Hz. Không lọc, chuẩn hóa hoặc tự cắt window trước khi gửi.
- Có thể giữ `seq`, `flags`, pressure và các cột phụ. Chương trình dùng `seq` nếu có để phát hiện mất mẫu; flags/pressure không tham gia model.
- Thiếu cột, NaN/Inf, timestamp không tăng hoặc chu kỳ trung vị ngoài 9.5–10.5 ms sẽ báo lỗi.
- Khoảng mẫu ngoài 5–15 ms hoặc seq đứt sẽ tách đoạn. Không ghép window qua chỗ mất mẫu, không nội suy hay padding. File dưới 100 mẫu xuất 0 window.

Model dùng window 100 mẫu, stride 50. 40 đặc trưng theo thứ tự mean, std(ddof=0), min, max, RMS, mỗi nhóm gồm ax, ay, az, gx, gy, gz, norm gia tốc, norm gyro. Scaler nằm trong model; score là điểm dự đoán, chưa phải xác suất đã hiệu chuẩn.

## 3. Đọc kết quả

| File | Nội dung |
|---|---|
| `predictions.csv` | Mỗi dòng một window: segment, dòng đầu/cuối (đánh số từ 0, không tính header), timestamp, score, threshold, dự đoán FALL/NON_FALL |
| `alarms.csv` | Bắt đầu cảnh báo khi score chuyển từ dưới ngưỡng sang bằng/trên ngưỡng; timestamp là mẫu cuối window |
| `summary.json` | Số mẫu/window/cảnh báo, thống kê thời gian, mất mẫu, số mẫu đuôi/đoạn ngắn chưa được dùng, checksum input và model |
| `plot.png` | Norm gia tốc, norm gyro và score; vạch đỏ dọc là mốc cảnh báo |

Nhiều window dương liên tiếp tính một cảnh báo. Đoạn mới reset trạng thái. Không phát kết luận cho 99 mẫu đầu mỗi đoạn; phần cuối chưa đủ window bị bỏ. Chạy lại cùng output sẽ ghi đè kết quả cũ.

## 4. Thu thử và gửi lại

Đeo chắc ở **lưng dưới**, giữ cùng vị trí và chiều trong buổi thử, chụp ảnh cách đeo. Ghi vài phút đi lại, ngồi/đứng, cúi và nằm xuống chủ động. Thu 1–2 lần ngã thử có kiểm soát khi có đệm và người hỗ trợ; giữ khoảng 5 giây trước/sau ngã.

Hướng trục giữa source và phần cứng **chưa được xác minh**; sample cũ ghi đeo bụng và sensor_frame_unmapped. Chương trình giữ nguyên trục đầu vào, không tự xoay/đổi trục để tăng score. Ghi rõ vị trí/chiều gắn thực tế và đơn vị. Chưa xác nhận những điều này thì kết quả chỉ dùng để kiểm tra sơ bộ.

Điền `ghi_chu.txt` và thêm dòng vào `labels.csv`:

```csv
file,label,onset_us,impact_us,activity
binh_thuong.csv,NON_FALL,,,di lai va ngoi xuong
nga_01.csv,FALL,,,nga thu sang ben - chua xac dinh moc
```

- Nhãn dùng `FALL`, `NON_FALL`, `UNKNOWN`. FALL nghĩa file **chứa** lần ngã, không phải mọi dòng đều ngã. Nằm xuống chủ động là NON_FALL.
- `onset_us`: bắt đầu mất thăng bằng; `impact_us`: va chạm. Dùng cùng clock với CSV. Chưa biết thì để trống; ghi rõ nếu ước lượng hoặc gửi video có dấu đồng bộ.
- Tên file và trigger/flags không tự xác nhận ngã.

Gửi lại CSV gốc + labels/ghi chú + ảnh cách đeo + thư mục kết quả; video nếu có. Runner hiện chưa tự đọc labels để tính metric. Khi có mốc nhãn thật, phía AI đối chiếu phát hiện/bỏ sót, độ trễ và báo nhầm. Một vài lần thử chưa đủ kết luận độ chính xác chung.

## 5. Đóng ZIP

```powershell
python package.py
```

ZIP nằm ở `dist/fall_detection_pc.zip`, chỉ chứa file trong danh sách bàn giao, không chứa `.venv`, dữ liệu mới hay output cá nhân. Manifest lưu checksum model và commit nguồn. Model được giữ nguyên từ báo cáo baseline; chương trình kiểm tra checksum trước mỗi lần chạy.

`validation.json` ghi bằng chứng kiểm tra: 6 test bàn giao, coverage khoảng 98%, sai số so với baseline tối đa 1e-12, kiểm tra môi trường riêng và audit dependencies. Toàn bộ bộ test hiện tại của tools/datasets cũng đạt 51/51.
