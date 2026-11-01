# Yêu cầu test nhanh phần cứng với model AI

Nhờ bạn thu một ít dữ liệu thật để kiểm tra sơ bộ model có phát hiện ngã và có báo nhầm khi chuyển động bình thường không.

1. **Đeo thiết bị chắc ở lưng dưới**, giữ cùng vị trí và chiều gắn trong suốt lần test, chụp một ảnh cách đeo.
2. **Ghi vài phút hoạt động bình thường:** đứng, đi lại, ngồi xuống/đứng lên, cúi người và nằm xuống có chủ đích. Nằm xuống bình thường được ghi là không ngã.
3. **Thu 1–2 lần ngã thử có kiểm soát**, chỉ khi có đệm bảo hộ phù hợp và người hỗ trợ, không tự thả ngã xuống nền cứng. Nếu chưa có điều kiện an toàn thì chỉ thu phần chuyển động bình thường trước.
4. **Xuất CSV gốc ở100Hz** theo định dạng firmware hiện có, có timestamp và sáu kênh ax, ay, az, gx, gy, gz. Gia tốc m/s² có trọng lực, gyro rad/s; không tự lọc, chuẩn hóa hoặc cắt thành window.
5. **Ghi rõ file nào, ngã lúc nào và làm hoạt động gì.** Có thể gửi video kèm dấu đồng bộ để đối chiếu với timestamp CSV. Mỗi lần ngã cần giữ dữ liệu khoảng5 giây trước và5 giây sau.

**Bàn giao:** CSV + ghi chú thời điểm/hoạt động + ảnh cách đeo; video nếu có. Nếu dùng logger snapshot hiện tại, lưu ý nó lấy30 giây trước và10 giây sau trigger: phải ghi đủ buffer và giữ toàn đoạn cần kiểm tra. Trigger/nút bấm chỉ là mốc thời gian, không tự coi là nhãn ngã.

**Phía AI sẽ kiểm tra:** model có báo ở1–2 lần ngã đó không, báo trễ bao lâu và có báo nhầm ở các hoạt động thường không. Đây là test sơ bộ xem luồng đo→dự đoán hoạt động, chưa đủ kết luận độ chính xác chung hoặc độ an toàn của hệ thống.

## Cấu trúc bộ dữ liệu gửi lại

Gửi một file ZIP theo cấu trúc:

```text
hardware_test.zip
└── hardware_test/
    ├── binh_thuong.csv
    ├── nga_01.csv
    ├── nga_02.csv       # Bỏ file này nếu chỉ thử1 lần
    ├── ghi_chu.txt
    └── cach_deo.jpg
```

**Mỗi dòng CSV là một lần đọc cảm biến**, chưa phải một window. Tối thiểu có:

```csv
timestamp_us,ax,ay,az,gx,gy,gz
```

`timestamp_us`: thời gian microsecond từ thiết bị; `ax/ay/az`: m/s² có trọng lực; `gx/gy/gz`: rad/s. Nếu firmware xuất thêm pressure, seq, flags thì giữ nguyên các cột đó. Không chèn log Serial vào giữa các dòng CSV. Gửi dữ liệu đo thật, không điền số mẫu minh họa.

**Nội dung ghi_chu.txt** — điền các mục sau:

```text
Vị trí đeo: lưng dưới
Chiều gắn: mô tả mặt hướng ra ngoài, chiều lên trên; xem ảnh kèm
Tần suất cấu hình: 100 Hz

binh_thuong.csv:
- Khoảng timestamp_us bắt đầu–kết thúc: ...–...
- Hoạt động: đi lại, ngồi xuống/đứng lên, cúi người, nằm xuống...
- Có xảy ra ngã không: không / có / không chắc

nga_01.csv:
- Bắt đầu mất thăng bằng, timestamp_us: ...
- Va chạm đệm, timestamp_us: ...
- Hướng ngã thử: ...
- Mốc thời gian: ước lượng từ ghi chú / đối chiếu video đồng bộ

nga_02.csv (nếu có):
- Bắt đầu mất thăng bằng, timestamp_us: ...
- Va chạm đệm, timestamp_us: ...
- Hướng ngã thử: ...
- Mốc thời gian: ước lượng từ ghi chú / đối chiếu video đồng bộ

Bất thường khi thu: mất kết nối, thiết bị bị lệch, chỉnh dây... hoặc không có.
```

Mốc ngã phải dùng cùng clock với CSV. Nếu chỉ ghi được giây trên video thì gửi video và dấu đồng bộ để phía AI ánh xạ; không biết thì ghi chưa xác định, không tự điền thời điểm giả. Tên `nga_01.csv` chỉ có nghĩa file chứa một lần ngã, không phải toàn bộ các dòng trong file đều có nhãn FALL.
