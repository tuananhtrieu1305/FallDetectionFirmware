# Button GPIO4 diagnostic

Ngày: 2026-10-29 (Asia/Bangkok). Đây là chẩn đoán riêng cho mức logic GPIO4;
không bắt đầu hoặc chuyển phase Wi-Fi/MQTT.

## Cấu hình source hiện tại

`alert_manager` cấu hình module button như sau:

- GPIO: `GPIO_NUM_4`.
- Mode: input.
- Pull-up nội ESP32-S3: tắt.
- Pull-down nội ESP32-S3: bật.
- Interrupt: tắt.
- Active level đang cấu hình: `1` (ACTIVE-HIGH).
- Debounce: 40.000 us.

ACTIVE-HIGH ở đây chỉ là cấu hình firmware đang tồn tại, chưa phải kết luận mới
về module 3 chân VCC/GND/OUT. Diagnostic không đổi `BUTTON_ACTIVE_LEVEL`.

## Cách diagnostic hoạt động

Main task có sẵn gọi `button_pressed()` mỗi 20 ms. Không tạo task mới. Main task
ở ưu tiên thấp; Sensor Manager vẫn ở priority 12 và chu kỳ 100 Hz. Hàm debounce
chỉ chấp nhận chuyển mức sau khi GPIO4 giữ nguyên ít nhất 40 ms.

Event `true` của `button_pressed()` bị ép bỏ bằng `(void)button_pressed()`.
Không có nhánh gọi vibration, buzzer, MQTT, emergency alert hoặc cuộc gọi từ
diagnostic. Log chỉ xuất hiện lúc khởi tạo và khi có chuyển mức đã debounce;
không có heartbeat hoặc log liên tục khi mức không đổi.

Để tắt riêng log GPIO4 sau khi đo, đặt `BUTTON_GPIO4_DIAGNOSTIC` thành `0`, rồi
build và flash lại. Poll/debounce API cũ vẫn hoạt động; active level không đổi.

## Cách đọc log

Ví dụ lúc khởi tạo:

```text
BUTTON_GPIO4_DIAG initial GPIO4=0 at_us=123456 mode=INPUT pull_up=DISABLED pull_down=ENABLED configured_active_level=1 debounce_us=40000 diagnostic_only=1 no_action=1
```

Ví dụ chuyển mức:

```text
BUTTON_GPIO4_DIAG transition=1 GPIO4=0->1 candidate_at_us=... stable_at_us=... debounce_us=40000 raw_edges=1 matches_configured_active=1 diagnostic_only=1 no_action=1
BUTTON_GPIO4_DIAG transition=2 GPIO4=1->0 candidate_at_us=... stable_at_us=... debounce_us=40000 raw_edges=1 matches_configured_active=0 diagnostic_only=1 no_action=1
```

- `candidate_at_us`: thời điểm monotonic firmware thấy cạnh raw cuối cùng bắt
  đầu mức ứng viên.
- `stable_at_us`: thời điểm mức được chấp nhận sau debounce.
- `raw_edges`: số cạnh raw quan sát trong lần chuyển mức được chấp nhận.
- `matches_configured_active`: mức ổn định có khớp active level đang cấu hình
  hay không. Field này không tự kết luận đó là lúc nút vật lý được nhấn.
- `diagnostic_only=1 no_action=1`: xác nhận đường log không thực thi action.

Để kết luận polarity thực tế, sau khi boot ổn định:

1. Không chạm nút, ghi lại `initial GPIO4`.
2. Nhấn và giữ khoảng 1 giây, ghi lại chuyển mức ổn định.
3. Thả và chờ khoảng 1 giây, ghi lại chuyển mức ổn định.
4. Lặp lại ít nhất ba lần.

Nếu tất cả lần thử cho `released=0`, `pressed=1`, wiring/module đang thể hiện
active-high. Nếu cho `released=1`, `pressed=0`, module đang thể hiện active-low.
Không sửa `BUTTON_ACTIVE_LEVEL` cho đến khi log thật xác nhận chuỗi này.

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

Nếu đúng binary đã được flash và chỉ cần mở lại monitor:

```powershell
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 monitor
```

Thoát monitor bằng `Ctrl+]`. Trong lúc thử nút, theo dõi thêm sensor `diag_5s`:
IMU gần 100 Hz, `missed_ticks`, `imu_err`, `diag_dropped` và jitter. Build không
thay thế kiểm tra timing trên board.

Không cần bật motor hoặc buzzer. Không chạy mock/MQTT alert để đo polarity nút.
Lượt triển khai này chưa flash hoặc đo GPIO4 thật, nên chưa kết luận nút vật lý
là active-high hay active-low.
