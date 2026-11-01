# Buzzer GPIO6 diagnostic

Ngày: 2026-10-29 (Asia/Bangkok). Phạm vi riêng: kiểm tra Buzzer MH-FMD trên
GPIO6 bằng LEDC PWM; không bắt đầu hoặc chuyển phase Wi-Fi/MQTT.

## Cấu hình và trình tự

- GPIO: `GPIO_NUM_6`.
- Driver: LEDC low-speed, timer 0, channel 0.
- PWM: 2.500 Hz, resolution 10-bit, duty 512 (khoảng 50%).
- GPIO output được invert như source Phase 4. Duty 0 tạo mức vật lý HIGH im lặng.
- `BUZZER_GPIO6_DIAG=1` bật test; `MOTOR_GPIO5_DIAG=0` tắt test motor tự động.
- `buzzer_gpio6_diag_start()` được gọi sau khi Sensor Manager, GNSS, LTE và Wi-Fi
  worker đã được start. Nó tạo task one-shot priority 2, không polling.
- Task chờ 5.000 ms, phát PWM trong 500 ms, tắt LEDC output, log kết quả rồi tự
  xóa. Static guard chỉ cho phép schedule một lần trong mỗi boot.

Buzzer được đưa về trạng thái im lặng trong init bằng GPIO HIGH trước khi giao
GPIO6 cho LEDC, sau đó LEDC duty 0 + update được kiểm tra lỗi. Diagnostic cũng
đảm bảo OFF trước khi schedule, trước khi ON và sau test.

Nếu duty 0/update lỗi, firmware dùng `ledc_stop()` với idle level 0 làm fallback.
Do GPIO matrix vẫn `output_invert=1`, đây là mức vật lý HIGH/silent của wiring
hiện tại. Cleanup chạy không điều kiện và được thử lại một lần nếu thất bại.
Nếu cả các thao tác OFF đều lỗi, firmware log `BUZZER OFF FAILED`; phần mềm không
thể khẳng định trạng thái điện vật lý khi driver đã từ chối mọi yêu cầu OFF.

Diagnostic không gọi motor, button event, MQTT, fall alert hoặc cuộc gọi. GPIO4
vẫn được main task poll 20 ms. Sensor Manager giữ priority 12/100 Hz; task buzzer
priority 2 chỉ tồn tại khoảng 5,5 giây rồi tự xóa.

## Log mong đợi

Ngay sau khi schedule:

```text
BUZZER_GPIO6_DIAG scheduled once | start_delay_ms=5000 | on_time_ms=500 | pwm_hz=2500 | task_priority=2 | motor_diag=DISABLED
```

Sau khoảng 5 giây:

```text
BUZZER TEST START | GPIO6 LEDC PWM=2500Hz | at_us=...
BUZZER ON | GPIO6 LEDC PWM=2500Hz duty=512 | at_us=... | duration_ms=500 | diagnostic_only=1 no_alert=1
BUZZER OFF | GPIO6 silent | at_us=... | fallback_used=0
BUZZER TEST COMPLETE | result=PASS | buzzer_off=CONFIRMED_BY_LEDC_DRIVER | at_us=... | runs_this_boot=1
```

`PASS` chỉ xác nhận LEDC driver chấp nhận cấu hình ON/OFF. Cần nghe buzzer vật lý
phát một lần khoảng 500 ms rồi im lặng. Build hoặc mock không thay thế kiểm thử
phần cứng.

## Build, flash và monitor

Trong ESP-IDF v5.5.5 terminal, đóng monitor khác đang giữ COM5 rồi chạy:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
idf.py --no-ccache -D CCACHE_ENABLE=0 build
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 flash monitor
```

Nếu đã flash đúng binary và chỉ cần mở lại monitor:

```powershell
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 monitor
```

Thoát monitor bằng `Ctrl+]`. Trong cùng phiên, kiểm tra:

1. Buzzer im lặng từ reset đến dòng `BUZZER ON`.
2. Buzzer phát đúng một lần khoảng 500 ms ở âm PWM 2.500 Hz.
3. Buzzer im tại `BUZZER OFF` và không phát lại ít nhất 60 giây.
4. Motor GPIO5 không rung; không có `MOTOR TEST START`.
5. Không có MQTT alert, fall/emergency event hoặc cuộc gọi do bài test.
6. GPIO4 vẫn log nhấn/thả; sensor `diag_5s` vẫn gần 100 Hz và không tăng bất
   thường `missed_ticks`, `imu_err` hoặc `diag_dropped`.

Lượt triển khai source chưa flash/monitor, vì vậy âm thanh thật, thời lượng,
OFF/no-repeat và regression 100 Hz vẫn cần xác minh trên board.
