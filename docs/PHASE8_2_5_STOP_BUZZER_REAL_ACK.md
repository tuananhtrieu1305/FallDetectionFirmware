# Phase 8.2.5 — STOP_BUZZER & Real ACK

Ngày hoàn tất: 2026-10-31 (Asia/Bangkok). **PASS trên broker demo và ESP32 thật**,
người dùng xác nhận nghe hai lượt còi bật rồi dừng. Không phải Backend/App PASS.
Wire profile được người dùng chấp thuận trong phiên này:
[Demo command contract](PHASE8_2_5_DEMO_COMMAND_CONTRACT.md).
Backend/Member 3 cần đồng bộ profile; không sửa Backend/AI hoặc mock.

## 1. Kiến trúc và thực thi

MQTT callback Phase 3 chỉ ghép/copy raw frame vào queue 4 entry, không actuator.
`device_telemetry` worker priority 2/core 0 là owner duy nhất của command processor,
đọc tối đa một command/vòng 100 ms khi không còn ACK pending. Parser cJSON của
SDK được giới hạn 512 byte, object phẳng bốn string, không escaped/nested values,
không duplicate/unknown key. Có exact topic binding/device ID từ transport và ACL.

Processor kiểm tra schema/correlation, connection epoch, supported command,
TTL/skew/UTC, active event, driver state và dedup. ACK success chỉ được tạo sau
`buzzer_stop_checked()` hoàn tất LEDC set/update duty 0, chờ một tick cho PWM
update rồi readback duty 0. Lỗi primary/readback luôn FAILED, kể cả fallback
best-effort có thể đã làm im output. Không điều khiển GPIO6 trực tiếp từ MQTT.

Giữ nguyên void APIs, boot diagnostic, frequency/inversion/GPIO, button, motor,
GNSS parser, sensor timer và LTE safe mode. STOP không đụng motor hoặc hủy event.
Serial `TEST_ALERT_BUZZER` chỉ là local demo arm, không phải remote START_BUZZER.
Plain TEST_ALERT vẫn chỉ publish, không bật còi. Event/buzzer demo tự off sau
30 s monotonic; cache/active UUID và ACK output state tách biệt.

ACK `lastCommand` được ghép vào full status retained; heartbeat/reconnect cũng
giữ lastCommand mới nhất. Một ACK pending backpressure việc đọc command tiếp theo;
SDK/application queues vẫn hữu hạn. Publish queue acceptance/PUBACK không được
hiểu như execution. Không có durable per-command ACK journal; xem delivery limits
và dedup scope trong phụ lục. Worker stack tăng từ 6.144 lên 8.192 byte vì thêm
bounded RX frame/ACK/cJSON; đo high-water mark thật, không giả heap/stack PASS.

## 2. UTC và app partition

SNTP được chuẩn bị trước khi sensor acquisition chạy; start khi MQTT ready, không
block sensor để chờ đồng bộ. Callback chỉ lưu anchor UTC/monotonic. Anchor tối đa
một giờ; fallback current GNSS fix thật tối đa 5 s. Status/event có thể dùng UTC
SNTP dù location vẫn UNAVAILABLE; không biến UTC sync thành GNSS fix PASS.

Attempt đầu với hostname NTP mặc định chưa sync sau 100 s. Laptop nhận response
thật từ ba server; ESP32 thực tế trả REJECTED/CLOCK_UNAVAILABLE/processedAt=null.
Đổi **riêng local config** sang IPv4 server NTP vừa được DNS/response xác minh
đã làm ESP32 sync và suite PASS. Không set giờ test từ serial/command/fixture,
không bỏ TTL. Chưa kết luận root cause là DNS, peer lựa chọn hay điều kiện mạng.
NTP demo unauthenticated, không phải secure time production; hostname/IP là cấu
hình vận hành có thể thay đổi, không coi IP test là endpoint cố định vĩnh viễn.

Build đầu vượt partition 1 MB `0x560` = 1.376 byte. Chuyển preset ESP-IDF
`CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE=y` (factory 1.500 KiB). Table trước/sau:

| Partition | Offset | Trước | Sau |
| --- | --- | --- | --- |
| NVS | 0x9000 | 24 KiB | 24 KiB |
| PHY | 0xf000 | 4 KiB | 4 KiB |
| factory app | 0x10000 | 1.024 KiB | 1.500 KiB |

Không đổi app offset, flash size 16 MB, PSRAM, OTA layout hoặc erase toàn bộ flash.
Không thêm custom partition/file system. App cuối 1.050.304 byte (`0x1006c0`), còn
485.696 byte (`0x76940`, 32%). NVS/PHY không bị ghi bởi lệnh flash đã dùng.

## 3. Local configuration, build và test

Chỉ sửa macro trong ignored `main/network_config.local.h`, giữ Wi-Fi/MQTT
credentials hiện có và tránh định nghĩa trùng:

```c
#define NETWORK_COMMANDS_ENABLED 1
#define NETWORK_TEST_ALERT_SERIAL_ENABLED 1
/* NETWORK_TIME_SERVER: hostname hoặc IPv4 NTP đã xác minh trên mạng demo. */
```

Default tracked config/template vẫn commands=0/serial=0, NTP hostname mặc định.
Binary trên board hiện bật hai opt-in local. Muốn tắt demo phải sửa macro về 0
và build/flash; chỉ sửa header không đổi binary đang chạy. Thiếu UTC không được
khắc phục bằng bỏ validation hoặc hard-code timestamp.

Trong ESP-IDF v5.5.5 terminal:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
python -B tools\test_command_processor.py
python -B tools\test_buzzer_checked.py
python -B tools\test_device_clock.py
python -B tools\test_device_telemetry.py
python -B tools\test_mqtt_manager.py
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
idf.py --no-ccache -D CCACHE_ENABLE=0 build
if ($LASTEXITCODE -ne 0) { throw 'Build failed; do not flash' }
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 flash
```

Giữ USB data/AP_DEMO/broker demo bật, đóng monitor khác đang giữ COM5. Suite dưới
đây bật còi thật hai lượt có auto-off 30 s, gửi MQTT command bằng backend demo
credentials trong ignored build, restart đúng broker demo, rồi kiểm tra CSV:

```powershell
python -B tools\test_phase5_device.py --port COM5 --out-dir build\phase8_2_5\manual_01
if ($LASTEXITCODE -ne 0) { throw 'Hardware suite failed; inspect runtime/MQTT frames' }
python -B tools\extract_sensor_csv.py build\phase8_2_5\manual_01\runtime.log --out-dir build\phase8_2_5\manual_01\csv
```

Mỗi lần dùng out-dir mới; không ghi đè evidence. Script chỉ tự xác minh điện/
driver và protocol; `acoustic_confirmation=PENDING_USER` là đúng cho một run mới,
không tự lấy xác nhận âm thanh của run cũ. Người test nghe/ghi lại kết quả thật.

Manual demo: `idf.py -p COM5 monitor`, chờ SUBACK/UTC và qua boot 10 s, gõ
`TEST_ALERT_BUZZER` Enter. Lấy eventId thật từ subscriber; sau đó backend demo
terminal gửi command (không in password):

```powershell
$cfg = Get-Content -Raw build\phase8_2_3\broker\client_secrets.json | ConvertFrom-Json
$eventId = Read-Host 'eventId TEST_ALERT_BUZZER vua nhan tu ESP32'
$command = @{
    commandId = [guid]::NewGuid().ToString()
    eventId = $eventId
    command = 'STOP_BUZZER'
    issuedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
} | ConvertTo-Json -Compress
$command | docker exec -i fall-phase3-broker mosquitto_pub -h 127.0.0.1 `
    -u $cfg.backendUsername -P $cfg.backendPassword `
    -t ('iot/devices/' + $cfg.deviceId + '/command') -q 1 -s
```

Mong đợi còi dừng trước timeout, firmware log `STOP_BUZZER EXECUTED ... output
verified off; event retained`, status `lastCommand.result=EXECUTED`/`reason=STOPPED`
với commandId/eventId đúng, output state IDLE. Duplicate cùng payload/ID chỉ trả
cached ACK, không điều khiển lại. Hạn 30 s theo issuedAt, future skew 5 s; thiếu
UTC thì REJECTED/CLOCK_UNAVAILABLE. Không đánh success từ publisher exit/PUBACK.

## 4. Kết quả đã xác minh — 2026-10-31

- Command parser/processor host tests PASS, line coverage 99,25%; checked buzzer
  fault injection và clock source/init/expiry tests PASS (fake boundaries, không
  claim hardware). Publisher regression 16/16 PASS/89,17%; MQTT 22/22/99,58%.
- Final build/COM5 flash PASS, esptool hash verified. ELF SHA-256
  `890D4BB95752ECCA86CEB5B3AADA0C8C807BDCDD08BD4817E83C692946261725`;
  BIN `747E85F45BA18C3345154B55642CAD3D8D4A982B02D3093D98BD3D2833AD718E`.
  Runtime prefix `890d4bb95` khớp. Artifact dưới `build/phase8_2_5/`.
- Final suite `hardware_ipv4/`: 100,17 s, hai local buzzer events + một plain
  Phase 4 TEST_ALERT, tất cả isTest=true. Hai STOP thật được xác minh driver
  ở uptime 19.380/32.260 ms; không có auto-timeout thay cho STOP trong run này.
- Negative tests EXPIRED, FUTURE_ISSUED_AT, EVENT_NOT_ACTIVE, UNSUPPORTED_COMMAND,
  COMMAND_ID_REUSED, NOT_BUZZING PASS; malformed/extra-target field không thực thi.
  Exact duplicate/cached success của old event không dừng còi new event; fresh
  old-event command bị từ chối. Sau reconnect, dedup/ACK correlation vẫn đúng.
- ACK success log/enqueue sau verified off; native subscriber nhận JSON thật,
  không mock. Người dùng xác nhận **"Có, nghe hai lượt còi bật rồi dừng"**.
  `results.json`, `mqtt_frames.json`, `acoustic_confirmation.json`, `broker_final.log`.
- 19 sensor diagnostic windows, seq/ok 9.506/9.506, missed_ticks/IMU/BMP error/
  outlier/diag_dropped đều 0; gaps 8.332–11.689 us. Worker minimum free stack
  3.500 byte. CSV 4.000 rows CRC32 `C3E22E3D`, không reset bất thường/panic.
- GNSS parser/self-test vẫn chạy/no-fix, LTE UART disabled/no AT/OFFLINE_UNVERIFIED.
  Sensor/Wi-Fi/MQTT/GNSS/LTE source giữ hash. Broker cuối chỉ còn server process,
  COM5 đã giải phóng; không commit/push/merge.

Chưa xác minh production TLS/user authorization/secure time, Backend/App adoption,
dedup bền vững qua reboot, long soak/heap fault campaign, GNSS fix hoặc hardware
auto-off 30 s khi mất mạng. Auto-off/driver failure được host-test, không thay
bằng chứng hardware; kiểm tra rộng hơn ở Phase 6 khi có lệnh.

**Phase 8.2.5: PASS cho profile demo đã được chấp thuận.** Phase 6 chỉ bắt đầu
khi người dùng yêu cầu; không coi kết quả này là E2E Backend/App PASS.
