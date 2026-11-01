# Phase 8.2.1 — Repository Audit & Baseline

Ngày audit: 2026-10-28 (Asia/Bangkok).
Phạm vi: đọc source thật, xác lập baseline và kế hoạch tích hợp; không thêm
Wi-Fi/MQTT, không sửa firmware, không flash hoặc truy cập serial.

## 1. Git và bảo toàn dữ liệu

- Branch: `main`.
- HEAD: `dae70f6067b88da27b20575975c911d56f8a10d2`.
- Commit: `docs: remove obsolete sensor model contract`.
- Lúc bắt đầu: không có tracked modification; có AGENTS/master plan/progress
  chưa track từ bước khởi tạo, captures và các log người dùng có sẵn.
- Đã chụp SHA-256 của 40 file tracked/capture/log có sẵn vào
  `build/phase8_2_1_audit/initial_hashes.json` để kiểm tra bảo toàn sau build.
- Build mới nằm trong `build/phase8_2_1_baseline/`, dùng bản sao sdkconfig tại
  `build/phase8_2_1_audit/sdkconfig.baseline`; không tái sử dụng artifact cũ làm
  bằng chứng build mới. Toàn bộ artifact audit nằm dưới `build/` đã được ignore.
- Không commit/push/merge, reset/clean hoặc xóa dữ liệu local.

## 2. Cấu trúc và build configuration

| Đường dẫn | Vai trò đã xác minh |
| --- | --- |
| `CMakeLists.txt` | Include ESP-IDF project.cmake; project `fall_detection_firmware` |
| `main/CMakeLists.txt` | Build app_main, alert_manager, sensor_manager, gnss_manager, lte_manager |
| `main/` | Các manager firmware; chưa có Wi-Fi/MQTT manager hoặc Kconfig riêng |
| `components/bmi270/` | Bosch BMI2/BMI270 driver, CMake riêng |
| `components/bmp3/` | Bosch BMP3 driver, float compensation mặc định |
| `tools/extract_sensor_csv.py` | Validator/extractor CSV 4.000 mẫu, CRC32 và metadata |
| `tools/mock_device.py` | Simulator MQTT Python; không chạy trên ESP32 |
| `docs/` | Contract, handoff App/Web, AI_DATA_HANDOFF.docx, CSV/metadata mẫu, plan/progress |
| `sdkconfig` | Cấu hình đang được Git theo dõi |
| `.vscode/settings.json` | Máy local trỏ ESP-IDF v5.5.5; được ignore |

Dependencies hiện khai báo trong main: esp_driver_i2c, esp_driver_gpio,
esp_driver_ledc, esp_driver_uart, esp_adc, esp_timer, heap, bmi270, bmp3.
Chưa gọi nvs_flash/esp_netif/esp_event/esp_wifi/esp_mqtt/cJSON trong source main.
Kconfig có Wi-Fi/MQTT enabled không đồng nghĩa ứng dụng đã init/kết nối chúng.

SDK/toolchain quan sát:

- ESP-IDF thực tế: v5.5.5 tại `C:\esp\v5.5.5\esp-idf`, xác nhận bằng idf.py
  --version và tools/cmake/version.cmake.
- Python ESP-IDF: `C:\Espressif\tools\python\v5.5.5\venv\Scripts\python.exe`.
  Shell mặc định tìm thấy Python MSYS; idf.py/cmake/ninja chưa có sẵn trên PATH.
- CMake 3.30.2; Ninja 1.12.1; Xtensa GCC 14.2.0 (esp-14.2.0_20260121).
- Target esp32s3, flash 16 MB, 80 MHz; sdkconfig có lựa chọn QIO và effective
  `CONFIG_ESPTOOLPY_FLASHMODE="dio"`; không tự sửa cấu hình baseline.
- PSRAM enabled, octal 80 MHz, malloc integration và memtest; CPU 160 MHz.
- FreeRTOS tick 100 Hz; esp_timer task affinity CPU0; Wi-Fi task mặc định CPU0;
  lwIP task no affinity. Các application task hiện dùng xTaskCreate, không pin core.
- Watchdog 5 giây, kiểm tra idle cả CPU0/CPU1; console UART0 115200 baud.
- Partition single app: NVS 0x6000, phy_init 0x1000, factory app 1 MB. Flash vật
  lý 16 MB không làm app partition tự lớn hơn; phải theo dõi size ở phase MQTT.
- ESP-MQTT đã có trong ESP-IDF (`components/mqtt/esp-mqtt`); component để require
  là `mqtt`, JSON là `json`. Không cần tự tải một MQTT library khác ở Phase 1.

Git ignore hiện chỉ bảo vệ build/, sdkconfig.old, Python cache, file tạm OS,
.vscode/settings.json và bmi270_temp/. `.env`, sdkconfig.local,
sdkconfig.secrets và network_config.local.h chưa được ignore.
Không đưa credentials vào tracked sdkconfig. Phase 2 phải thiết lập đường cấu
hình local an toàn và ignore tương ứng trước khi điền secret.

## 3. app_main và initialization

Thứ tự thực tế trong [app_main.c](../main/app_main.c):

1. alert_manager_init: vibration/buzzer output an toàn, button init; gọi off.
2. Shared I2C0 trên GPIO8/9, 100 kHz; probe BMI270 0x68, BMP388 0x76.
3. Init Bosch driver với context/static driver objects tồn tại suốt vòng đời.
4. BMI270 ACC 100 Hz ±8g, GYRO 100 Hz ±2000 dps; BMP388 pressure/temp, ODR 25 Hz.
5. Delay khởi tạo 100 ms rồi sensor_manager_start(&bmi, &bmp).
6. gnss_manager_start; lỗi được log, không dừng Sensor Manager.
7. lte_manager_start; lỗi được log, không dừng sensor/GNSS.
8. Main idle loop delay 1 giây, không xử lý button hoặc fall detection.

Lỗi alert/I2C/sensor init khiến app_main return trước các manager phía sau.
Để giữ baseline, điểm tích hợp dự kiến là sau LTE start và trước idle loop;
network init phải nhanh, không chờ mạng/broker trong đường init sensor và không
reset hệ thống chỉ vì mất mạng. Giới hạn phụ thuộc boot sensor cần được ghi rõ.

Một số log/comment cũ sai với implementation: app_main nói BMP388 chưa sampled
và LTE AT task đã started; sensor_manager.h/sensor_ring.h vẫn mô tả giai đoạn
cũ. Dựa vào implementation dưới đây, chưa sửa các dòng này trong Phase 1.

## 4. Sensor Manager, ring buffer và CSV

Nguồn: [sensor_manager.c](../main/sensor_manager.c),
[sensor_sample.h](../main/sensor_sample.h), [sensor_ring.h](../main/sensor_ring.h).

- esp_timer periodic 10.000 us, dispatch ESP_TIMER_TASK; callback chỉ
  xTaskNotifyGive. Sensor task ulTaskNotifyTake, cộng pending vào seq và đếm
  skipped_ticks. Không dùng vTaskDelay để định thời BMI270.
- Sensor task priority 12, stack 6.144 byte; logger priority 4, stack 4.096 byte;
  diagnostic queue dài 32, gửi nonblocking và đếm dropped diagnostics.
- Chỉ sensor task đọc BMI270/BMP388 và ghi ring. BMP388 đọc sau IMU mỗi seq chia
  hết cho 4; pressure sample-and-hold chỉ gắn khi không thuộc tương lai và tuổi
  không quá 200 ms. bmp_hz trong diagnostics đo số lần thử đọc, không phải chỉ
  các lần pressure thành công; cần xem thêm bmp_ok/bmp_err.
- sample 56 byte: monotonic timestamp trước IMU read, accel m/s² gồm gravity,
  gyro rad/s, pressure Pa, seq, flags và pressure timestamp.
- PSRAM: hai ring x 4.000 mẫu và POST 1.000 mẫu = 504.000 byte payload.
  30 giây PRE (3.000 mẫu) + 10 giây POST (1.000 mẫu); ring overwrite mẫu cũ
  không đồng nghĩa mất IMU tick.
- Synthetic requests tại seq 500/4500/4600/5700: dự kiến reject sớm tại 500,
  accept 4500, reject busy 4600/5700; state IDLE → COLLECTING → READY, không reset
  để export nhiều event. Nếu có missed ticks hoặc read error, event_verify có
  thể fail; không được suy ra số mẫu đầy đủ chỉ từ timer đã chạy.
- Logger xác minh snapshot, export một lần FDCSV_BEGIN/FDMETA/header/4.000 dòng/
  FDCSV_END với CRC32 IEEE; yield 1 tick sau mỗi 8 dòng để tránh watchdog.
- Flags event marker hiện do synthetic capture tạo, không phải button thật,
  dù comment trong sensor_sample.h nói button event marker.

State machine này chỉ phục vụ capture sensor, không phải fall alert state
machine và không được tái sử dụng thành MQTT TEST_ALERT tự phát khi boot.
Ring không có API snapshot thread-safe cho network; không đọc storage đang
ghi từ MQTT task. Không thêm printf, JSON, publish hoặc actuator vào sensor task.
Timeout I2C callbacks hiện lên tới 1.000 ms: lỗi bus có thể ảnh hưởng timing,
đây là rủi ro baseline cần theo dõi, chưa thay driver trong audit.

## 5. GNSS và LTE

[GNSS Manager](../main/gnss_manager.c): UART1 RX GPIO15, 9600 8N1, RX buffer
2.048 byte; đọc chunk 128 byte với timeout 100 ms, sentence tối đa 256 byte.
Task priority 3, stack 4.096 byte. Parser checksum, UTC/date/coordinate, RMC và
GGA; stale sau 3 giây chuyển CURRENT sang LAST_KNOWN. Last Known chỉ trong RAM.
gnss_manager_get_snapshot dùng mutex với timeout 20 ms, phù hợp gọi từ worker
publish/status; không gọi trong callback cần phản hồi nhanh.

7 self-test FIX/LOST/FIX chạy trước UART init, dùng test state local không đẩy
vị trí giả vào s_state. Chưa chạy lại chúng trên thiết bị trong phiên audit.
Không có settimeofday/SNTP trong main: UTC trong GNSS location không đồng nghĩa
system clock đã đồng bộ hoặc command expiration đã có nguồn thời gian tin cậy.

[LTE Manager](../main/lte_manager.c) hiện là **Phase 7.12e TX IDLE DIAGNOSTIC**:

- Không init UART2, không phát AT, không APN/IP/MQTT/call/SMS.
- GPIO18 input, chờ 8 giây; 500 lần đọc x 10 ms không pull; sau đó bật internal
  pulldown, chờ 500 ms, đọc thêm 500 lần, in kết quả rồi task tự xóa.
- Task `lte_tx_diag`, priority 3, stack 4.096 byte; không có readiness getter.
- Header/app_main còn mô tả AT-only/UART2 TX17/RX18; log đó không chứng minh UART
  hoặc LTE đang chạy. Giữ `OFFLINE_UNVERIFIED`, status tương lai `lteReady=false`.
  Không phục hồi AT bring-up hoặc thay GPIO17/18 trong Phase 8.2.

## 6. Button, vibration, buzzer và alert state

Nguồn: [alert_manager.c](../main/alert_manager.c),
[alert_manager.h](../main/alert_manager.h).

- GPIO4 **ACTIVE-HIGH**, pull-down, debounce 40 ms; trái với master prompt ghi
  active-low. Source comment nói đã kiểm thử module active-high. Giữ nguyên code,
  xác minh wiring thực tế trước khi dùng button làm trigger ở phase sau.
- button_pressed cần polling định kỳ, nhưng hiện không có caller trong main.
  Baseline không có luồng button xác nhận “Tôi ổn” đang chạy.
- Vibration GPIO5 active-high, LOW off.
- Buzzer GPIO6 LEDC low-speed timer0/channel0, 2.500 Hz, 10-bit, duty 512 để bật.
  output_invert=1; duty 0 tạo mức vật lý HIGH an toàn cho module active-low.
- buzzer_on/off và vibration_on/off trả void. LEDC errors chỉ được log, không
  trả kết quả, không có buzzer state getter, lock hoặc command queue.
- Không tìm thấy fall alert state machine, active MQTT eventId, real ACK hoặc
  fall inference runtime trong main. Chỉ có capture state ở Sensor Manager.

Phase 5 cần thay đổi tối thiểu alert_manager để trả esp_err_t sau LEDC thực thi
và expose trạng thái nhất quán (hoặc thêm API checked giữ wrapper cũ), có một
worker sở hữu thao tác actuator. Đây là điều kiện để ACK thật, không thể gửi
success chỉ vì đã gọi hàm void. Thành công API driver không phải phép đo âm học;
acceptance vẫn phải quan sát còi vật lý dừng.

## 7. MQTT contract và giới hạn mock

Đã đọc toàn bộ [contract](DEVICE_BACKEND_CONTRACT.md) và
[mock_device.py](../tools/mock_device.py).

| Topic | QoS | Retain |
| --- | --- | --- |
| `iot/devices/{deviceId}/event` | 1 | No |
| `iot/devices/{deviceId}/status` | 1 | Yes |
| `iot/devices/{deviceId}/location` | 1 | No |
| `iot/devices/{deviceId}/command` | 1 | No |
| `iot/devices/{deviceId}/health` | 0 | No |

- schemaVersion 1; device thật mode REAL; lteReady false; status Last Will online
  false. Mock và real không được chạy chung device ID.
- TEST_ALERT/isTest=true, eventId duy nhất; confidence null và location
  UNAVAILABLE với lat/lon/observedAt null khi không có dữ liệu. occurredAt null
  nếu không xác định UTC; không lấy monotonic timestamp làm UTC.
- modelVersion cho test firmware chưa có model cần thống nhất giá trị hợp lệ;
  không khai báo model AI đã hoàn thiện. Null observedAt của status cũng chưa
  được định nghĩa rõ như occurredAt của event.
- Command payload hiện gồm commandId/eventId/command/issuedAt, target nằm ở topic;
  không tự bắt buộc field deviceId chưa được contract yêu cầu.
- ACK thực thi thật, result codes, error/duplicate ACK, tương quan event trong
  ACK, TTL/expiry/skew, hành vi thiếu UTC, replay qua reboot và alertState sau
  STOP_BUZZER chưa đủ chi tiết để triển khai đơn phương. Cần thống nhất Member 3.
- Authorization thiết bị trong demo phụ thuộc broker credentials/ACL cùng
  authorization phía Backend; JSON command tự nó chưa chứng minh người gửi có quyền.

Mock dùng paho Callback API v2, env MQTT_USERNAME/MQTT_PASSWORD, subscribe command
QoS1, Last Will retained status, publish status mỗi 10 giây và một TEST_ALERT
trong run() sau kết nối đầu tiên. on_connect publish status/subscribe lại, không
tự tạo TEST_ALERT mới trong callback reconnect. Mock tạo UUID eventId mỗi process.

Mock chỉ kiểm tra JSON object, STOP_BUZZER, matching eventId và commandId string
không rỗng; không validate issuedAt/expiration, dedup/replay, alert state hoặc
authorization ở application layer. ACK_SIMULATED nằm trong lastCommand của
status, không có topic ACK riêng. Mock đổi alertState về IDLE; không sao chép
hành vi này thành hủy trạng thái ngã trên thiết bị thật.
Không dùng mock làm mẫu bảo đảm an toàn đầy đủ cho Phase 5.

## 8. Kế hoạch tích hợp theo source thật

Các file dưới đây là **đề xuất cho phase tương ứng**, chưa tạo/sửa firmware:

| Phase | File dự kiến | Thay đổi và lý do |
| --- | --- | --- |
| 8.2.2 | `main/wifi_manager.c`, `.h` | Station lifecycle, snapshot status, bounded reconnect/backoff qua worker/timer |
| 8.2.2 | `main/app_main.c`, `main/CMakeLists.txt` | Init network sau manager cũ/trước idle; thêm SRCS và esp_wifi/esp_netif/esp_event/nvs_flash dependencies |
| 8.2.2 | `.gitignore`, `main/network_config.example.h`, local header tương ứng | Template không secret, local config ignored; không đặt password trong tracked sdkconfig |
| 8.2.3 | `main/mqtt_manager.c`, `.h`, main CMake/app_main/config template | ESP-MQTT component mqtt, lifecycle/LWT/subscribe/publish API, bounded fragmentation và error/reconnect |
| 8.2.4 | `main/device_messaging.c`, `.h`, CMake/app_main | Worker status/TEST_ALERT có kiểm soát, JSON component json, đọc GNSS snapshot/API network; trạng thái test tách sensor capture |
| 8.2.5 | `main/command_manager.c`, `.h`, CMake và wiring messaging | Parse/validate/dedup/expiry qua worker, bounded command queue, correlation và ACK sau actuator |
| 8.2.5 | `main/alert_manager.c`, `.h` | Thêm API trả kết quả/state tối thiểu để real ACK; giữ mapping/inversion/debounce |
| 8.2.6 | Tài liệu/scripts kiểm thử và module mới nếu có lỗi | Reliability/regression, không đổi timer/sensor task để phục vụ network |
| 8.2.7 | Tài liệu/scripts tích hợp | Xác minh broker/Backend/App thật; không tự viết Backend hoặc AI |
| 8.2.8 | `docs/PHASE8_WIFI_MQTT_HANDOFF.md`, tài liệu liên quan | Bàn giao, payload và trạng thái test đúng firmware |

Thiết kế giới hạn: callback Wi-Fi/MQTT chỉ cập nhật trạng thái/copy message hữu
hạn/đẩy queue, không delay chờ mạng, không đọc sensor/GNSS có mutex, không chạy
actuator. Publish/JSON/command do worker priority thấp hơn sensor, stack/queue/
outbox có giới hạn và log lỗi có kiểm soát. Task affinity/resource tuning cần
đo jitter thực tế, không tự pin task hoặc đổi timing baseline theo comment cũ.
Không erase toàn NVS một cách mặc định khi init lỗi mà chưa xác định ảnh hưởng.

Không cần sửa Bosch driver, sensor ring/sampling, GNSS parser hoặc LTE diagnostic
để thêm Wi-Fi/MQTT. Nếu phát sinh lý do kỹ thuật mới phải giải thích và test lại.

## 9. Build và kiểm thử audit

**Baseline build PASS**, ESP-IDF v5.5.5, target esp32s3, exit code 0:

- Fresh configure/build: `baseline_build.log`, 1.087 bước build chính, sinh ELF,
  app binary, partition table và bootloader; không có compiler warning được tìm thấy.
- Lần đầu có traceback/warning tạo ROM GDB init do thiếu ESP_ROM_ELF_DIR và Git
  dubious ownership ESP-IDF/OpenThread submodule dưới sandbox user. Build vẫn
  hoàn tất; không phải lỗi source ứng dụng.
- Đã set ESP_ROM_ELF_DIR tới ROM ELF có sẵn và thêm safe.directory chỉ cho hai
  đường dẫn SDK qua GIT_CONFIG_COUNT/KEY_n/VALUE_n trong process build. Không sửa
  Git global, SDK hoặc PowerShell profile của người dùng.
- Chạy lại `reconfigure build`: `baseline_verified.log`, exit 0, không còn các
  diagnostic warning/error/fatal/traceback đã kiểm tra. Lần này dùng lại các object
  của fresh build trước, không được mô tả là biên dịch mới toàn bộ lần thứ hai.
- App binary 0x4af50 = 307.024 byte; app partition 0x100000 = 1.048.576 byte,
  còn 0xb50b0 = 741.552 byte (71%). Bootloader 0x5700 byte.
- flasher_args.json xác nhận DIO / 16 MB / 80 MHz; chưa flash.
- SHA-256 sau build: toàn bộ 40 file tracked/log/capture ban đầu giữ nguyên;
  git diff tracked rỗng. Chỉ cập nhật/tạo tài liệu quản lý phase.

Log, exit codes, SDK config copy và artifacts đều ở dưới `build/` (ignored).

Kiểm tra offline đã chạy:

- AST parse hai Python tools: PASS; 4 JSON examples trong contract parse hợp lệ.
- Existing extractor với sensor_csv_verified_4000.txt: PASS 4.000 rows,
  CRC32 D59564EB. Đây là capture cũ riêng, không phải checksum sample docs.
- Extractor với log gốc log.fall_detection_firmware.20261024123237.txt: PASS
  4.000 rows, CRC32 265827BD; bytes CSV sample trong docs khớp checksum metadata.
  Hai capture có checksum khác nhau là dữ liệu khác nhau, không tự coi là lỗi.
- Các kiểm tra capture đều dùng dữ liệu lịch sử, không chứng minh hardware
  đang chạy HEAD hiện tại hoặc kết nối MQTT thật.

Lệnh lặp lại build trong **ESP-IDF Terminal đã kích hoạt v5.5.5** của VS Code:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
New-Item -ItemType Directory -Force -Path build\phase8_2_1_audit | Out-Null
Copy-Item -LiteralPath sdkconfig -Destination build\phase8_2_1_audit\sdkconfig.baseline
idf.py --version
idf.py --no-ccache -B build\phase8_2_1_baseline -D 'SDKCONFIG=C:/Workspace/FallDetectionFirmware/build/phase8_2_1_audit/sdkconfig.baseline' -D 'CCACHE_ENABLE=0' reconfigure build
```

Mong đợi ESP-IDF v5.5.5, `Project build complete`, size check app partition qua.
Nếu terminal cũng chạy dưới user sandbox khác chủ sở hữu SDK, có thể thêm
Git trust **chỉ cho process/terminal đó** trước lệnh build, không dùng global:

```powershell
$auditGitConfigCount = 0
if ($env:GIT_CONFIG_COUNT) { $auditGitConfigCount = [int]$env:GIT_CONFIG_COUNT }
foreach ($auditSafeDirectory in @('C:/esp/v5.5.5/esp-idf', 'C:/esp/v5.5.5/esp-idf/components/openthread/openthread')) {
    Set-Item -Path "Env:GIT_CONFIG_KEY_$auditGitConfigCount" -Value 'safe.directory'
    Set-Item -Path "Env:GIT_CONFIG_VALUE_$auditGitConfigCount" -Value $auditSafeDirectory
    $auditGitConfigCount++
}
$env:GIT_CONFIG_COUNT = [string]$auditGitConfigCount
```

Lặp lại validator dữ liệu lịch sử, không làm thay đổi captures gốc:

```powershell
python -B tools\extract_sensor_csv.py sensor_csv_verified_4000.txt --out-dir build\phase8_2_1_audit\historical_capture_validation
python -B tools\extract_sensor_csv.py log.fall_detection_firmware.20261024123237.txt --out-dir build\phase8_2_1_audit\historical_raw_log_validation
```

Tùy chọn kiểm tra runtime nếu board đã chứa đúng baseline này: giữ nguyên wiring,
đặt board nằm yên trên bàn, mở COM5 và nhấn EN/reset, theo dõi ít nhất 70 giây
để có đủ PRE/POST và export. Không cần thực hiện hardware test để chốt audit.
Lệnh monitor (không flash):

```powershell
idf.py --no-ccache -B build\phase8_2_1_baseline -D 'SDKCONFIG=C:/Workspace/FallDetectionFirmware/build/phase8_2_1_audit/sdkconfig.baseline' -D 'CCACHE_ENABLE=0' -p COM5 monitor
```

Mong đợi: alert_manager_init PASS; BMI270 init/config PASS;
`esp_timer started: period=10000 us; BMP3 every 4 ticks; logger task split`;
`GNSS SELFTEST PASS`; diag_5s IMU khoảng 100 Hz/BMP khoảng 25 Hz, kiểm tra thêm
imu_err/missed_ticks/bmp_err/diag_dropped không tăng; không reset/watchdog;
`event_verify=PASS`, `CSV_EXPORT_FINISHED rows=4000` nếu capture không mất tick.
GNSS UNAVAILABLE khi chưa có fix là trạng thái hợp lệ; LTE phải hiện
`UART disabled, no AT commands`. Không dùng log app_main “LTE AT task started”
để kết luận LTE online. Button không có caller và buzzer không bật trong baseline,
nên monitor này không kiểm chứng button action hay STOP_BUZZER. Thoát Ctrl+].

## 10. Phần chưa xác minh và bước kế tiếp

Chưa flash/monitor COM5, chạy lại GNSS self-test trên board, đo sampling/jitter
live, kiểm tra mức button vật lý hoặc bật/tắt actuator trong phiên này.
Chưa xác minh GNSS outdoor fix, LTE online, AI inference, broker/Backend/App.
Chưa có Wi-Fi credentials hoặc broker LAN/credentials/ACL; không cần chúng cho audit.

Phase tiếp theo là 8.2.2 khi nhận `làm phase 2`; cần cấu hình local không secret
trong Git và mạng Wi-Fi 2.4 GHz/thiết bị thật để đạt PASS hardware.
Các điểm contract còn thiếu chặn phần phụ thuộc ở phase publishing/command,
không chặn thiết kế Wi-Fi Manager.

## 11. Phản hồi build lỗi từ người dùng — 2026-10-28

Log người dùng chạy `idf.py @phase1Args build` cho thấy CMake truyền
`CCACHE_ENABLE=1`, dùng wrapper ccache. GCC 14.2.0 crash trong RTL pass `ira`
khi biên dịch `components/esp_lcd/rgb/esp_lcd_panel_rgb.c`, function
`rgb_panel_draw_bitmap`, báo `internal compiler error: Segmentation fault`
tại dòng 722, Ninja exit 1. Đây là compiler crash khi compile SDK; không có
bằng chứng cần sửa firmware, sensor, LCD driver hoặc optimization của dự án.

Hướng dẫn cuối chat trước thiếu thiết lập ccache tắt như môi trường baseline.
Đã sửa lệnh ở mục 9 bằng explicit `--no-ccache`, CMake `CCACHE_ENABLE=0` và
`IDF_PY_BUILD_JOBS=1` (biến được tools/idf_py_actions/tools.py của bản SDK này
hỗ trợ). Chỉ thay môi trường process/build directory; không xóa cache, không
fullclean, không sửa SDK hoặc cấu hình source, không flash.

Đã giữ bản sao attachment và log Ninja gốc ở ignored build/phase8_2_1_audit/:
`user_build_failure.log`, `user_build_stdout_18724.log`.
Kết quả recovery:

- `baseline_recovery.log` / `.exitcode`: PASS, exit 0, 1.016 bước build chính,
  `Project build complete`; không warning/error/fatal/traceback đã kiểm tra.
  Một số object được tái sử dụng, trong đó có LCD object từ baseline trước.
- Để kiểm chứng đúng translation unit lỗi, đã sao lưu LCD object vào ignored
  audit directory, chỉ xóa object sinh ra ở đúng đường dẫn build đã xác minh,
  rồi chạy Ninja -j1 -v cho riêng target đó. Không xóa cache hoặc source.
- `lcd_recompile.log` / `.exitcode`: PASS exit 0, log xác nhận GCC trực tiếp
  compile esp_lcd_panel_rgb.c không qua ccache, không compiler diagnostic.
- `baseline_recovery_final.log` / `.exitcode`: Ninja all -j1 sau compile lại LCD
  PASS exit 0, link/image/size check hoàn tất; binary vẫn 307.024 byte, app còn 71%.
- Source/config/capture/log cũ giữ nguyên SHA-256 của cả 40 file.

Cách build đã được xác minh với ccache tắt và một job; chưa chứng minh nguyên
nhân gốc của compiler crash là ccache hay parallel build. Terminal người dùng
đã được xác nhận build lại thành công qua log gửi sau đó (mục 12).
Phase 8.2.1 PASS; chưa có hardware test hoặc phase tiếp theo được triển khai.

## 12. Log xác nhận từ terminal người dùng — 2026-10-28

Đã nhận log lệnh reconfigure/build với --no-ccache, CCACHE_ENABLE=0 và Ninja
`-j 1 all`; kết thúc `Project build complete`, size check app/bootloader qua,
không compiler error/crash được quan sát. App 307.024 byte, còn 71% app partition;
bootloader 0x5700 byte, còn 32%. Lần chạy này là incremental build, không phải
fresh compile toàn bộ. Bản sao log: `build/phase8_2_1_audit/user_build_success.log`.

Thông báo esp_blockdev không có CMakeLists và ESP-TEE chỉ hỗ trợ một số SoC
khác xuất hiện trong cấu hình thành công; không cần sửa SDK vì các dòng đó.
Không cần build lại trong lượt phân tích log này. Chưa flash/monitor hoặc kiểm
thử phần cứng; chờ `làm phase 2`, không tự thêm Wi-Fi/MQTT.

## 13. Bổ sung bằng chứng runtime hardware — 2026-10-28

Đã kiểm tra log `log.fall_detection_firmware.20261028182729.txt` và CSV/metadata
`build/phase8_2_1_audit/runtime_capture/fall_event_synthetic_20261028_183231.*`.
Các mục "chưa runtime/hardware test" ở báo cáo trước là trạng thái tại thời
điểm đó; kết quả hiện tại nằm ở đây và progress mục 12.

- Runtime tới 282.142 ms sau một reset POWERON ở đầu; không thêm reset hoặc
  panic/watchdog/brownout/error-level được quan sát. ELF SHA prefix a21f0180b
  khớp ELF baseline local; boot log xác nhận ESP-IDF v5.5.5, version dae70f6.
- PSRAM 8 MB memtest OK, 504.000 byte sensor payload allocated; sensor init PASS.
- 56 cửa sổ diagnostics: IMU 99,9–100,0 Hz, BMP 24,9–25,1 Hz; imu_err,
  missed_ticks, bmp_err, diag_dropped và jitter outliers đều 0. Gap IMU toàn phiên
  9.981–10.022 us. Đây là baseline ngắn, chưa phải network regression/long soak.
- Existing extractor chạy lại PASS 4.000 rows, CRC32 83E4CCDE, khớp nguyên bytes
  CSV người dùng đã tạo. seq 1500–5499; 3.000 PRE + 1.000 POST và một marker đầu
  POST, 4.000 dòng pressure valid; gap capture 9.985–10.015 us, mean 10.000 us.
- GNSS self-test PASS nhưng RX total đứng ở 133 byte, parsed RMC/GGA=0 trong
  toàn bộ 56 báo cáo; LOCATION UNAVAILABLE. Chưa xác minh receiver cung cấp NMEA
  hợp lệ liên tục, chưa có outdoor fix. Không gộp hai loại bằng chứng GNSS.
- LTE vẫn GPIO18 diagnostic/UART disabled/no AT; không online. Button/vibration/
  buzzer chỉ có init logs, chưa kiểm thử hành vi vật lý.

Chi tiết số liệu/hash ở `build/phase8_2_1_audit/runtime_capture/runtime_analysis.json`.
Không đổi source, không thao tác COM/flash trong lượt phân tích. Phase 8.2.1 PASS;
Wi-Fi phase sau phải dùng location UNAVAILABLE khi GNSS chưa có dữ liệu hợp lệ.
