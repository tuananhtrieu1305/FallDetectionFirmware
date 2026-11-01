# LTE TX ADC diagnostic

Ngày: 2026-10-30 (Asia/Bangkok). Phạm vi riêng: đo thụ động A7670C TX tại
GPIO18/ADC2 channel 7. Không triển khai phase network tiếp theo.

## Source và lựa chọn mode

Source ban đầu là Phase 7.12e: GPIO18 input, lấy 500 mẫu digital không pull,
sau đó bật pull-down và lấy 500 mẫu nữa. UART2 chưa được cài driver và không gửi
AT. Không tìm thấy source 7.12c trong lịch sử Git hiện có. Các kết quả 7.12e
HIGH=285/LOW=215/transitions=404, pull-down LOW=500 và đo cũ khoảng 1,8 V là
ngữ cảnh người dùng cung cấp, chưa được đo lại trong lượt triển khai.

Sau Phase 11.11 (2026-10-30), source chọn **`LTE_UART_AT_DIAG=1`** và
**`LTE_TX_ADC_DIAG=0`**. Muốn chạy lại ADC riêng, đặt UART thành **`0`** rồi
ADC thành **`1`**, build/flash lại. Bật cả hai gây compile error để ngăn tranh
GPIO18. Chi tiết mode UART: [Phase 11.11](PHASE11_11_LTE_UART_AT_DIAGNOSTIC.md).
Không nghiệm thu Wi-Fi từ bản ADC. Khi chọn ADC:

- Chọn task ADC, loại toàn bộ nhánh GPIO Phase 7.12e khỏi bản compile này.
- `app_main` bỏ khởi động Wi-Fi trong **cả phiên boot**, dù có credentials local.
  Không tự bật lại radio sau phép đo. Wi-Fi Manager/config không bị sửa.
- Trước khi đo, task yêu cầu `esp_wifi_get_mode()` trả `ESP_ERR_WIFI_NOT_INIT`;
  nếu driver đã được init từ đường khác, task abort thay vì đo khi có tranh chấp.
- Đặt **cả UART và ADC** thành `0`, build và flash lại để trở về 7.12e và đường startup
  Wi-Fi cũ. Khi đó GPIO18 lại được 7.12e đọc và bật pull-down như baseline.

Không thay GPIO17 hoặc gửi tín hiệu lên RX modem. GPIO18 tắt cả pull-up và
pull-down, interrupt/digital input/output disable trước cấu hình analog. Sau đo
giải phóng ADC2 và calibration; không bật lại pull. Tìm kiếm source xác nhận
không có caller ADC/GPIO18 khác trong `main` của bản này. UART1 GNSS giữ nguyên.

## Thu mẫu và thống kê

- Chờ 8 giây sau task startup; các bài Button/Motor/Buzzer giữ nguyên source và
  lịch chạy hiện có. Buzzer one-shot trước đó thường đã hoàn tất trước cửa sổ đo;
  diagnostic LTE không gọi actuator.
- Xác minh mapping GPIO18 → ADC_UNIT_2 / ADC_CHANNEL_7 bằng SDK API.
- ADC oneshot 12 bit, attenuation 12 dB. ESP32-S3 dùng curve-fitting calibration
  khi SDK/eFuse hỗ trợ; không giả hệ số hiệu chỉnh hoặc dùng RAW * 3300/4095.
- Lấy tối đa 500 mẫu, chu kỳ khoảng 10 ms, dừng khi đủ mẫu hoặc hết khoảng
  5 giây. Có thể ít hơn 500 mẫu do scheduler/ADC latency; log `elapsed_us`,
  `attempts`, `valid`, read errors và lỗi cuối. Không catch-up bằng vòng busy.
- Buffer tĩnh cố định, GNSS/LTE task priority 3; không log mỗi mẫu. Sensor
  Manager giữ nguyên 100 Hz/priority 12.
- RAW min/median/max chỉ tính read thành công. Median chẵn là trung bình hai
  giá trị giữa, giữ được phần .5.
- `raw>=4090` được coi near-upper-rail/saturation đáng nghi. Log số lượng/tỷ lệ
  và cảnh báo không biết điện áp phía trên; bỏ các mẫu đó khỏi thống kê mV.
  `raw<=5` được đếm riêng và cảnh báo giới hạn độ chính xác gần sàn ADC.
- Khi calibration hợp lệ: log mV min/median/max cho mẫu không bão hòa, cùng tỷ lệ
  các dải `[0,200)`, `[200,1000)`, `[1000,1600)`, `[1600,2000)`,
  `[2000,3000)`, `[3000,+inf)` mV. Biên trái có tính, biên phải không tính.
- Mẫu số của từng dải là số mẫu **calibrated, unsaturated**; không gồm mẫu lỗi
  đọc hoặc bão hòa. Đọc `valid`, near-rail và mẫu số để tránh suy diễn tỷ lệ trên
  toàn bộ tín hiệu. Nếu có bão hòa, thống kê mV chỉ mô tả phần chưa bão hòa.
- Calibration init lỗi/không hỗ trợ: RAW ONLY, không xuất mV/bands. Bất kỳ lỗi
  conversion nào cũng làm toàn bộ mV/bands của phiên bị suppress, lỗi được log.
  Nếu tất cả mẫu bão hòa hoặc không đọc được: mV/bands unavailable.

Log kết thúc `LTE_TX_ADC_DIAG COMPLETE: SAMPLED/ABORTED` chỉ cho biết có thu được
mẫu ADC hay không, không chứng minh UART ổn định hoặc LTE ready. ADC sampling
100 Hz không đo được waveform UART tốc độ cao; điện áp ước lượng cũng không xác
nhận đường modem TX đang drive, nhất là nếu dây đang floating.

## Build, flash và monitor

Trong terminal đã kích hoạt ESP-IDF v5.5.5:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
idf.py --no-ccache build
idf.py --no-ccache -p COM5 flash monitor
```

Đóng monitor khác đang giữ COM5 trước lệnh flash. Thoát bằng `Ctrl+]`.
Nếu chỉ mở monitor sau khi đã flash đúng binary:

```powershell
idf.py --no-ccache -p COM5 monitor
```

Giữ wiring hiện tại: modem dùng nguồn riêng 5V/3A, GND chung, TX modem → GPIO18,
GPIO17 chưa nối RX modem. Thu log ít nhất 30 giây, gồm:

- Wi-Fi startup skipped / Wi-Fi NOT_INIT; UART2 OFF / no AT.
- Calibration OK hoặc FAILED/UNSUPPORTED.
- ADC SAMPLE START/END, RAW, near-rail/floor, mV/bands nếu hợp lệ và COMPLETE.
- Sensor `diag_5s`: kiểm tra IMU gần 100 Hz, lỗi/missed_ticks/jitter không tăng
  bất thường so với baseline thực tế.

Không tự flash/monitor trong lượt triển khai source. Chưa xác minh điện áp thật,
calibration/eFuse trên board, ADC saturation hoặc sensor regression. Kết quả
build/static được ghi tại mục LTE TX ADC DIAGNOSTIC trong progress.
