# GNSS RAW RX diagnostic

Ngày: 2026-10-29 (Asia/Bangkok). Phạm vi riêng theo yêu cầu chẩn đoán GNSS;
không triển khai phase Wi-Fi/MQTT tiếp theo.

## Cách hoạt động

- `main/gnss_manager.c`: `GNSS_RAW_DIAGNOSTIC=1` bật chẩn đoán. Đổi thành `0`
  rồi build/flash lại để tắt log và event queue chẩn đoán.
- Một reader duy nhất: `uart_read_bytes()` trong `gnss_task`. Chép tối đa
  128 byte đầu cửa sổ từ chính `chunk`, trước bước tìm `$`/lọc ký tự/parser.
  Không đọc UART thêm, không dùng dữ liệu self-test làm RAW và không gửi lệnh
  cấu hình sang GNSS.
- Báo cáo khoảng 5 giây; sau mỗi đợt log chờ ít nhất 5 giây cho đợt tiếp theo.
  Tối đa 128 **byte đầu vào** được biểu diễn, chia hàng 32 byte. `suppressed`
  là số byte chỉ bỏ khỏi log; mọi byte vẫn đi qua luồng parser cũ.
- `RAW_RX ASCII`: giữ ký tự ASCII in được; escape `\r`, `\n`, `\t`, `\xHH`
  cho byte không in được, và `\\` cho dấu backslash. Mỗi hàng có offset/độ dài.
  Hàng chứa byte không in được có thêm `RAW_RX HEX` của **cùng các byte đó**.
  CR/LF cũng là byte không in được nên câu NMEA bình thường vẫn có thể có HEX.
  Không có RX thì `sampled=0`, không in hàng dữ liệu giả.
- Bộ nhớ mẫu cố định, không cấp phát theo dữ liệu, không log từng byte/câu.
  Giữ stack/priority GNSS 4096 byte/3 và Sensor Manager priority 12/100 Hz.
  Tác động timing thực tế vẫn cần đo trên board.

## Đọc log

Các bộ đếm `UART_RX_DIAG`/`NMEA_RX_DIAG` reset sau mỗi báo cáo; dòng
`RX total`/`parsed RMC/GGA` cũ vẫn là tổng tích lũy.

| Log / field | Ý nghĩa |
| --- | --- |
| `RAW_RX window: rx / sampled / suppressed` | Tổng byte UART trả về trong cửa sổ / số byte hiển thị / số byte không hiển thị |
| `UART_RX_DIAG: frame` | Event lỗi framing từ driver |
| `fifo_ovf / buffer_full` | Event tràn RX FIFO / đầy RX ring buffer |
| `parity / break / read_err` | Event parity / break / lần UART read trả giá trị âm |
| `queue_at_capacity` | Số lần thấy queue đầy 32 event khi lấy mẫu; bộ đếm event có thể thiếu khi queue bão hòa |
| `NMEA_RX_DIAG: lines` | Số câu gom đủ `$` đến LF để gọi parser |
| `checksum_or_syntax` | Parser trả false, kiểm tra checksum/định dạng `$...*HH` không đạt |
| `fields_or_header` | Parser trả false vì header/giới hạn fields hoặc nội dung RMC/GGA không được chấp nhận |
| `ignored_other` | Checksum/header hợp lệ nhưng là loại câu khác RMC/GGA; đây là bỏ qua có chủ đích |
| `mutex_skip` | Không lấy được mutex để gọi parser trong timeout cũ |
| `resync` | Gặp `$` mới trong lúc đang gom câu |
| `nonprint_abort / overlong_abort` | Bộ gom câu cũ bỏ câu do byte không in được / quá dài |
| `outside_sentence_bytes` | Byte đi qua khi chưa gom câu; có thể gồm dấu kết thúc câu và byte rác |

Queue event được tiêu thụ bằng thao tác không chờ trong chính GNSS task.
ESP-IDF v5.5.5 mặc định bật overflow/parity/break nhưng chưa bật framing;
diagnostic bổ sung riêng interrupt framing qua `uart_enable_intr_mask()`.
Không đổi ngưỡng RX, GPIO15, UART1, baud 9600, 8N1 hoặc RX ring 2048 byte.
Không thêm flush/recovery làm mất dữ liệu; driver vẫn xử lý overflow theo SDK.
Event queue có giới hạn nên `frame=0` không chứng minh tín hiệu điện hoàn hảo.

Các hàm checksum/parser, self-test, current/stale/last-known giữ nguyên.
Theo logic hiện có, RMC/GGA được xử lý nhưng không có fix vẫn có thể làm tăng
`parsed`; `parsed>0` không đồng nghĩa outdoor fix PASS. Diagnostic chỉ phân loại
các lần parser trả false, không thêm tiêu chí chấp nhận câu hoặc tọa độ.

## Build, flash và monitor

Trong **ESP-IDF v5.5.5 terminal đã kích hoạt**, đóng monitor cũ đang giữ COM5:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
idf.py --no-ccache -D CCACHE_ENABLE=0 build
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 flash monitor
```

Chỉ mở lại monitor, khi đã flash đúng binary:

```powershell
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 monitor
```

Thoát monitor bằng `Ctrl+]`. Giữ nguyên wiring/cấu hình mạng hiện tại. Thu log
ít nhất 60 giây gồm `GNSS RAW RX DIAGNOSTIC ON`, `RAW_RX`, `UART_RX_DIAG`,
`NMEA_RX_DIAG`, `RX total` và sensor `diag_5s`. Đối chiếu IMU khoảng 100 Hz,
`missed_ticks`, `imu_err`, `diag_dropped` và jitter trước/sau diagnostic;
không suy diễn sensor regression PASS từ build.

Nếu ASCII không có cấu trúc `$...*HH\r\n`, dùng HEX và framing/abort counters
để khoanh vùng dữ liệu đầu vào trước khi quyết định sửa parser hay phần cứng.
Nếu có câu đúng cấu trúc, đối chiếu checksum/fields/ignored counters. Mẫu chỉ là
128 byte đầu cửa sổ nên không bảo đảm chứa đủ một câu hoặc mọi loại câu.

Kết quả build và giới hạn kiểm chứng được ghi tại mục GNSS RAW DIAGNOSTIC của
`docs/PHASE8_2_PROGRESS.md`. Chưa flash/monitor hoặc xác minh RX thật trong lượt
triển khai này; chưa kết luận nguyên nhân GNSS không parse và chưa xác nhận
outdoor fix.
