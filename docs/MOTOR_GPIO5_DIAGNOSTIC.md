# Motor GPIO5 diagnostic

Ngày: 2026-10-29 (Asia/Bangkok). Phạm vi riêng: kiểm tra module motor rung
VCC/GND/IN sau khi đi dây lại; không bắt đầu hoặc chuyển phase Wi-Fi/MQTT.

## Cấu hình và trình tự

- GPIO: `GPIO_NUM_5`, output, active-high.
- Internal pull-up: tắt; internal pull-down: bật.
- OFF: GPIO5 = 0. ON: GPIO5 = 1.
- `vibration_init()` ghi OFF trước khi cấu hình output, kiểm tra kết quả; sau
  `gpio_config()` ghi OFF và kiểm tra lần nữa.
- `MOTOR_GPIO5_DIAG=1` bật diagnostic. Đặt thành `0`, build và flash lại để
  tắt việc lên lịch test.
- `motor_gpio5_diag_start()` được gọi sau khi Sensor Manager, GNSS, LTE và Wi-Fi
  worker đã được start. Nó tạo một task one-shot priority 2, không polling.
- Task chờ 5.000 ms cho startup ổn định, đảm bảo OFF, bật motor đúng 500 ms theo
  FreeRTOS tick, tắt motor, log kết quả và tự xóa. Guard tĩnh chỉ cho phép một
  lần lên lịch trong mỗi lần boot.

GPIO5 cleanup OFF được gọi không điều kiện sau thao tác ON, kể cả khi GPIO driver
báo lỗi trong đường test. Nếu không tạo được task, hàm start tự yêu cầu OFF.
Firmware ghi rõ nếu chính yêu cầu OFF thất bại; không thể khẳng định trạng thái
điện vật lý khi driver trả lỗi.

Task không gọi buzzer, button handler, MQTT, fall alert hoặc cuộc gọi. Button
GPIO4 vẫn được main task poll 20 ms với debounce/log hiện có. Sensor Manager giữ
priority 12/100 Hz; task motor priority 2 chỉ tồn tại khoảng 5,5 giây rồi xóa.

## Log mong đợi

Ngay sau khi schedule:

```text
MOTOR_GPIO5_DIAG scheduled once | start_delay_ms=5000 | on_time_ms=500 | task_priority=2
```

Sau khoảng 5 giây:

```text
MOTOR TEST START | GPIO5 active-high | at_us=...
MOTOR ON | GPIO5=1 | at_us=... | duration_ms=500 | diagnostic_only=1 no_alert=1
MOTOR OFF | GPIO5=0 | at_us=...
MOTOR TEST COMPLETE | result=PASS | motor_off=CONFIRMED_BY_GPIO_DRIVER | at_us=... | runs_this_boot=1
```

`PASS` chỉ xác nhận các lời gọi GPIO driver thành công. Cần quan sát motor vật lý
rung một lần khoảng 500 ms rồi dừng. Không coi build hoặc log driver là bằng
chứng phần cứng đã rung thật.

Nếu có `MOTOR ON FAILED`, cleanup OFF vẫn được thực hiện. Nếu có
`MOTOR OFF FAILED`, ngắt nguồn motor/board để đưa phần cứng về trạng thái an toàn
và kiểm tra lại wiring; không tiếp tục test actuator trong phiên đó.

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

1. Motor im lặng từ reset đến dòng `MOTOR ON`.
2. Motor rung đúng một lần khoảng 500 ms.
3. Motor dừng tại `MOTOR OFF` và không rung lại ít nhất 60 giây.
4. Không có buzzer, MQTT alert hoặc fall/emergency event do bài test.
5. GPIO4 vẫn log nhấn/thả; sensor `diag_5s` vẫn gần 100 Hz và không tăng bất
   thường `missed_ticks`, `imu_err` hoặc `diag_dropped`.

Lượt triển khai source chưa flash/monitor, vì vậy motor vật lý, thời lượng thực,
no-repeat và regression 100 Hz vẫn cần xác minh trên board.
