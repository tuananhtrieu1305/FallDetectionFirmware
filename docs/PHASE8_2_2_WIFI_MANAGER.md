# Phase 8.2.2 — Wi-Fi Manager

Ngày: 2026-10-28 (Asia/Bangkok).
Nguồn tiến độ: [PHASE8_2_PROGRESS.md](PHASE8_2_PROGRESS.md).
Phạm vi: Wi-Fi Station trên ESP32-S3, DHCP, snapshot và reconnect. Chưa thêm MQTT.

## 1. Kiến trúc và API

- `app_main` gọi `wifi_manager_start()` sau khi cấu hình cảm biến, **trước**
  `sensor_manager_start()` và timer acquisition. NVS/driver/PHY/radio được chuẩn
  bị đồng bộ trước khi lấy mẫu; không chờ AP hoặc DHCP. Lỗi Wi-Fi được trả về và
  log, sau đó vẫn khởi động Sensor Manager; không gọi reset hoặc erase NVS.
- Credentials được copy trước khi start trả về. `ESP_OK` chỉ xác nhận đã tạo
  radio đã chuẩn bị và worker đã tạo, không phải thiết bị đã online.
  SSID trống trả `ESP_ERR_NOT_FOUND` và
  giữ trạng thái DISABLED, không tạo task hoặc init NVS/radio.
- Worker `wifi_manager`, priority 3, stack 6.144 byte; sensor vẫn priority 12.
  Caller boot sở hữu NVS/netif/event loop/STA init/config/start. Worker sở hữu
  connect/disconnect, backoff, log kết nối và cleanup khi lỗi runtime.
- Callback Wi-Fi/IP chỉ copy dữ liệu hữu hạn trong critical section ngắn và
  notify worker. Không publish, điều khiển actuator, delay hoặc gọi driver connect.
- `wifi_manager_get_snapshot(out)` lấy trạng thái thread-safe, không chờ mạng.
  `wifi_manager_is_connected()` chỉ true khi đã nhận IPv4 khác 0 cho interface
  này. Disconnect/lost-IP/stop làm connected=false và xóa IP ngay trong callback.
- Snapshot có state, connected, IP/netmask/gateway, tổng connect_attempts,
  disconnect_count, disconnect_reason, retry_delay_ms/retry_at_us và last_error.
  last_error là lỗi API/timeout; reason riêng thể hiện nguyên nhân disconnect.

States: DISABLED → STARTING → CONNECTING → CONNECTED; lỗi kết nối chuyển
WAITING_RETRY rồi thử lại; lỗi khởi tạo/driver bị stop bất thường chuyển ERROR.
Manager sở hữu STA suốt boot; không có API stop/reconfigure ở phase này.
Sau lỗi khởi tạo hoặc runtime cần sửa nguyên nhân và reboot, không gọi start lặp.
Riêng lỗi cấp task được cleanup và cho phép thử start lại trước acquisition.

## 2. Reconnect và tài nguyên

- Backoff: 1, 2, 4, 8, 16, 30 giây, sau đó giữ 30 giây; reset về 1 giây chỉ
  sau khi nhận IP. Không reset backoff chỉ vì đã associate hoặc gọi connect OK.
- Duplicate disconnect trong thời gian chờ không làm retry sớm hơn hoặc tạo
  queue tăng vô hạn. Notifications coalesce; không có application event queue.
- Mỗi attempt có timeout 30 giây, bao gồm chờ DHCP. Timeout/lost IP khi còn
  association được reset bằng disconnect từ worker rồi backoff.
- Worker ngủ bằng task notification timeout đến deadline monotonic, không busy
  loop; FreeRTOS tick có thể làm thời gian chờ dài hơn một chút.
- NVS init lỗi: ERROR và giữ NVS; không tự erase toàn bộ partition.
- Không dùng helper create_default_wifi_sta có assert/abort khi thiếu tài nguyên;
  gọi esp_netif_new/attach/default handlers riêng để kiểm tra kết quả.
- Nếu init lỗi, unregister handlers, stop/deinit driver đã tạo, destroy interface,
  xóa bản copy cấu hình tạm và trả lỗi; lỗi runtime dọn tương tự rồi dừng worker.
  Shared netif stack/event loop/NVS
  được giữ cho vòng đời application; không xóa tài nguyên global của module khác.
- Không thay đổi Bosch driver, ring/sampling/CSV, GNSS parser hoặc alert GPIO/PWM.
  Mode LTE cho test Wi-Fi: UART=0/ADC=0, giữ implementation diagnostic; LTE vẫn
  OFFLINE_UNVERIFIED, không có UART/AT/call/SMS trong mode test hiện tại.

## 3. Cấu hình local và secrets

`main/network_config.example.h` là template không credentials. File thật
`main/network_config.local.h` được Git ignore. Không đưa credentials vào
template, main source hoặc sdkconfig đang được theo dõi.

Module hỗ trợ Wi-Fi 2.4 GHz WPA2-Personal và WPA3-Personal tương thích;
không hỗ trợ open/WEP/WPA1/enterprise trong phase này. SSID 1–32 byte; password
8–63 byte hoặc PSK 64 ký tự hexadecimal. SSID trống tắt Wi-Fi. Mạng cần DHCP.

Trong ESP-IDF Terminal, tạo file nếu chưa có (không ghi đè cấu hình đã điền):

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
if (-not (Test-Path -LiteralPath main\network_config.local.h)) {
    Copy-Item -LiteralPath main\network_config.example.h -Destination main\network_config.local.h
}
git check-ignore -v -- main/network_config.local.h
git ls-files -- main/network_config.local.h
```

Mong đợi check-ignore chỉ ra rule trong .gitignore, còn ls-files không in file.
Mở file local trong VS Code và điền NETWORK_WIFI_SSID/NETWORK_WIFI_PASSWORD.
Đây là C string: ký tự `"` trong giá trị cần `\"`, backslash cần `\\`.
Không cần gửi credentials lên chat hoặc log.

Wi-Fi config dùng WIFI_STORAGE_RAM trước set_config để driver không lưu
credentials mới vào NVS. NVS vẫn dùng cho hoạt động SDK/hiệu chuẩn bình thường.
Credentials vẫn được nhúng trong binary khi build, nên binary chứa cấu hình
thật cũng phải được giữ riêng trong ignored build/. Đây chưa phải provisioning
hoặc secret storage production. Application logs không in SSID/password.

CMake theo dõi thêm/xóa local header qua CONFIGURE_DEPENDS và đổi compile
definition của app_main; không chỉ theo dõi sửa file. Điều này tránh dùng lại
object chứa cấu hình cũ khi header từ absent thành present hoặc bị xóa.
Dòng `-- GLOB mismatch!` khi thêm/xóa header là tín hiệu CMake chạy lại cấu hình;
nếu sau đó kết thúc `Project build complete` thì không phải compiler error.

## 4. Build / flash / monitor

ESP-IDF v5.5.5 Terminal, dùng ccache tắt và một job do lỗi GCC đã gặp ở Phase 1:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
New-Item -ItemType Directory -Force -Path build\phase8_2_2 | Out-Null
if (-not (Test-Path -LiteralPath build\phase8_2_2\sdkconfig.wifi)) {
    Copy-Item -LiteralPath sdkconfig -Destination build\phase8_2_2\sdkconfig.wifi
}
$wifiPhaseArgs = @('--no-ccache', '-B', 'build\phase8_2_2_firmware',
    '-D', 'SDKCONFIG=C:/Workspace/FallDetectionFirmware/build/phase8_2_2/sdkconfig.wifi',
    '-D', 'CCACHE_ENABLE=0')
idf.py @wifiPhaseArgs build
```

Chỉ khi build thành công, người dùng flash board và mở monitor:

```powershell
$wifiRuntimeStart = Get-Date
idf.py @wifiPhaseArgs -p COM5 flash monitor
```

Trong monitor: Ctrl+T rồi Ctrl+L bật logging; chờ thông báo file log, nhấn EN
để lưu toàn bộ boot. Giữ board nằm yên, chạy ít nhất 5 phút. Thoát Ctrl+].
COM5 phải được đóng ở các terminal/chương trình khác trước khi flash/monitor.

Log mong đợi nếu cấu hình hợp lệ:

```text
WIFI_MANAGER: station started; awaiting IPv4 (2.4 GHz, WPA2/WPA3, DHCP)
WIFI_MANAGER: GOT_IP <IPv4 thực tế>; connected=true attempts=<số lần thử>
```

Nếu chưa điền SSID, phải thấy `Wi-Fi disabled: configure main/network_config.local.h locally`.
Đây là cấu hình chưa sẵn sàng, không phải đã PASS kết nối. Nếu worker báo ERROR,
gửi log lỗi (không credentials); không tự erase NVS hoặc đổi sensor/GNSS/LTE.

## 5. Hardware acceptance tests

| Test | Thao tác | Bằng chứng cần có |
| --- | --- | --- |
| Wi-Fi/DHCP | Mạng 2.4 GHz WPA2, credentials đúng, boot board | GOT_IP với IP LAN hợp lệ; init sensor/GNSS vẫn chạy |
| AP offline lúc boot | Tắt AP trước reset, chờ rồi bật lại | Retry giãn 1/2/4/8/16/30 giây, sensor không dừng; sau khi AP trở lại nhận IP |
| Disconnect/reconnect | Sau GOT_IP, tắt AP 45–60 giây rồi bật; lặp ít nhất 2 lần | Offline/retry và GOT_IP lại, không reset/crash; backoff reset sau IP |
| Sai password (tùy chọn) | Đổi password trong file local và build/flash lại | Không GOT_IP sai; retry hữu hạn tần suất, sensor vẫn chạy; phục hồi cấu hình đúng sau test |
| Sensor regression | Giữ board yên trong lúc Wi-Fi kết nối và reconnect | Theo dõi imu_hz/bmp_hz, imu_err/missed_ticks/bmp_err/diag_dropped và jitter; không tự đặt PASS nếu có lệch |
| CSV | Ghi trọn boot qua snapshot và export | Existing extractor PASS 4.000 mẫu/CRC32, không label ngã thật |
| GNSS/LTE | Quan sát cùng phiên Wi-Fi | GNSS self-test/parser không bị sửa; không giả fix; LTE UART disabled/no AT như baseline |

Sau bật AP có thể cần chờ đến backoff 30 giây cộng thời gian scan/auth/DHCP;
không reset board để che việc reconnect chưa hoàn tất. Ghi riêng lần mất mạng
do người dùng thao tác. Chưa đặt ngưỡng jitter mới ngoài baseline đã đo; so sánh
toàn bộ gap/outlier và seq thay vì chỉ nhìn Hz trung bình.

Validate log mới trong cùng terminal (sau khi thoát monitor):

```powershell
$wifiRuntimeLog = Get-ChildItem -File -Filter 'log.fall_detection_firmware.*.txt' |
    Where-Object { $_.CreationTime -ge $wifiRuntimeStart } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $wifiRuntimeLog) { throw 'Không tìm thấy log Wi-Fi mới; kiểm tra logging.' }
python -B tools\extract_sensor_csv.py $wifiRuntimeLog.FullName --out-dir build\phase8_2_2\runtime_capture
```

Capture sensor chỉ tự xuất một lần mỗi boot; không yêu cầu xuất lại khi reconnect.
Runtime baseline Phase 1 đã có GNSS self-test PASS nhưng NMEA thật đứng ở 133
byte/parsed 0. Đây là vấn đề có trước Wi-Fi, chưa phải bằng chứng regression do
Phase 2; không đánh dấu live GNSS hoặc outdoor fix PASS từ self-test.

## 6. Host tests và giới hạn bằng chứng

```powershell
python -B tools\test_wifi_manager.py --cc C:/msys64/ucrt64/bin/gcc.exe --gcov C:/msys64/ucrt64/bin/gcov.exe
```

Runner biên dịch **source wifi_manager.c thật** với fake SDK/FreeRTOS boundaries,
clock ảo và fault injection; không gọi COM/radio. Tests chạy trước implementation
đã thất bại vì thiếu module; sau implementation kiểm tra credentials/boundaries,
connected snapshot, mất mạng/mất IP, reset backoff, DHCP timeout, event trùng,
foreign/zero IP, init failure cleanup, stop, startup event timeout và shared loop.
Host coverage không chứng minh thread scheduling/timing trên ESP32 hoặc Wi-Fi thật.
Hardware end-to-end cho Phase 2 là các bài ở mục 5; kết quả mới nhất ở mục 8
và progress, không suy ra từ host coverage.

Artifacts host nằm ở build/phase8_2_2/host_tests/; build logs và kết quả cuối cùng
được ghi trong progress. Chưa có MQTT, status publish, TEST_ALERT, command hoặc ACK.

## 7. Kết quả đã xác minh khi triển khai

- Test-first: pre-implementation runner thất bại vì chưa có wifi_manager.c,
  log `build/phase8_2_2/tests_red.log`.
- Host tests: **28 kịch bản PASS**, source manager thật line coverage
  **98,59% (210/213 dòng executable)**, branches executed 98,86%, taken at least
  once 85,23% theo gcov. Kết quả `host_tests/results.json`, log `host_tests.log`.
- Fresh ESP-IDF v5.5.5 build: **PASS exit 0**, 1.089 bước build chính, không
  compiler/CMake warning/error/fatal/traceback được quan sát; ccache tắt, một job.
  Log `build/phase8_2_2/firmware_build.log`.
- App binary **855.504 byte (0xd0dd0)**, factory partition 1 MB, còn
  **193.072 byte (18%)**. Không đổi partition; Phase 3 cần kiểm tra size khi thêm MQTT.
- Kiểm thử cấu hình local thực với CMake: tạo header chỉ chứa giá trị build-only,
  build tự reconfigure/recompile app_main và marker xuất hiện trong binary;
  xóa đúng header test, build tự recompile và marker biến mất. Hai build PASS;
  logs config_present_build.log/config_removed_build.log, config_rebuild.exitcode=0.
  Không dùng credentials thật hoặc kết nối AP trong bài này.
- Tại thời điểm bàn giao code, file local test đã được xóa, firmware dùng defaults SSID rỗng:
  **Wi-Fi disabled cho đến khi người dùng cấu hình lại và build**.
- Source sensor/ring, GNSS, LTE, alert và sdkconfig gốc giữ nguyên SHA-256;
  các log/capture có sẵn giữ nguyên. main/app_main chỉ thêm include và start Wi-Fi.
- Chưa flash/monitor, chưa có Wi-Fi thật/IP/reconnect/sampling với radio đang chạy.
  **Phase status: CODE_DONE_NEEDS_HARDWARE_TEST**. Không tự commit/push/merge hoặc
  chuyển sang Phase 3.

## 8. Audit log hardware mới nhất — 2026-10-28

Log: `log.fall_detection_firmware.20261028190530.txt`.
Đã phân tích trực tiếp, không sửa firmware/build/flash trong lượt audit.

- Wi-Fi thật nhận DHCP IP 192.168.0.11 tại monotonic 6.451 ms, attempts=1.
  Chỉ có một GOT_IP, chưa có disconnect/retry/reconnect; chưa đủ bằng chứng
  network recovery. Log khoảng 102 giây, chưa đủ phiên quan sát 5 phút.
- Sensor có regression startup so với Phase 1: seq=500 nhưng ok=484,
  missed_ticks=16, imu_hz=96,7, gap max 72.413 us, 7 jitter outliers ở cửa sổ đầu.
  19 cửa sổ tiếp theo không mất thêm tick; IMU 99,9–100,0 Hz, outliers=0.
  Không coi sampling đã giữ nguyên chỉ vì tốc độ sau startup trở lại bình thường.
- Existing extractor PASS 4.000 rows/CRC32 40A38A5D, event_verify PASS, pressure
  valid 4.000 dòng. Capture seq 1500–5499 không bao quát cửa sổ đầu mất tick.
- Không panic/watchdog/error-level/reset được quan sát trong đoạn log đã ghi.
  GNSS self-test PASS, live RX/parsed 0; LTE UART disabled/no AT.
- PHY có full RF calibration và lưu dữ liệu ở startup; chỉ là ngữ cảnh tương
  quan thời gian, chưa khẳng định root cause của sensor gap.

**Trạng thái hiện tại IN_PROGRESS, chưa PASS Phase 8.2.2.** Cần xử lý/xác minh
lại sampling lúc Wi-Fi startup và kiểm thử AP mất/kết nối lại trong khi sensor
chạy. Không sửa timing BMI270 hoặc bỏ qua counters để hợp thức hóa kết quả.
Bằng chứng máy đọc được và CSV/metadata: `build/phase8_2_2/log_review/`.

## 9. Retest trực tiếp COM5 — 2026-10-30

Đã mở serial bằng Python/pyserial, reset và thu log thật. Board ban đầu chạy
LTE ADC diagnostic, bỏ Wi-Fi cả boot. Đã chuyển `LTE_TX_ADC_DIAG=0`, build PASS
(app 860.816 byte, còn 18%) và flash app/hash verify PASS. LTE vẫn GPIO diagnostic,
UART/AT disabled. Không sửa Wi-Fi/sensor/GNSS/actuator code hoặc credentials.

Runtime ELF prefix `55c2e1707` khớp build. Capture 421,80 s, 83 diagnostic windows:

- DHCP thật PASS: GOT_IP 192.168.0.5 ở 3.387 ms, attempts=1.
- Startup vẫn mất 15 tick, gap max 72.979 us, 7 jitter outliers; cửa sổ đầu
  IMU 96,9 Hz. Các cửa sổ sau không mất thêm tick; không xem đó là fix startup.
- imu_err/bmp_err/diag_dropped=0; không reset bất thường được quan sát.
- Existing extractor PASS 4.000 dòng, CRC32 44A31E64. Capture seq 1500–5499
  không chứa cửa sổ startup bị mất tick.
- Chỉ 1 GOT_IP, không offline/retry. Người dùng đã tắt Wi-Fi laptop, không AP;
  **chưa kiểm thử reconnect**. USB ESP32 cấp nguồn/serial; radio ESP32 tự kết nối
  theo cấu hình đã nạp. Tắt Wi-Fi laptop chỉ ngắt ESP32 nếu laptop thực sự là
  hotspot và hotspot đó bị tắt.

**Phase 8.2.2 vẫn IN_PROGRESS.** Cần sửa/xác minh startup và xác định AP thật
(xem `NETWORK_WIFI_SSID` trong file local tại máy, không gửi password qua chat)
trước test AP offline/reconnect theo mục 5. Artifact:
`build/phase8_2_2/live_probe/wifi_retest_summary.json`, raw log
`wifi_runtime_20261030_083741.log` và CSV/metadata trong `runtime_capture/`.
COM5 đã đóng sau capture; không có monitor nền giữ cổng.

## 10. Sửa regression và nghiệm thu phần cứng — 2026-10-30

SSID local và log kết nối thật được đối chiếu trùng nhau; tên mạng không ghi vào
tài liệu tracked và password không được đọc/in. Điểm phát đúng đã được người dùng
tắt/bật trực tiếp trong khi ESP32 giữ nguồn USB và không reset.

Nguyên nhân theo bằng chứng runtime: radio/PHY từng được init sau khi timer 10 ms
đã chạy, tạo gap startup 72,979 ms. Sau khi chuyển radio init trước acquisition,
startup sạch nhưng các lần retry vẫn có thể trì hoãn callback vì Wi-Fi và
`esp_timer` task cùng core 0. Bản cuối giữ Wi-Fi/ISR ở core 0, pin Wi-Fi worker
core 0, pin Sensor Task core 1 và đặt `esp_timer` task core 1. Không đổi period
10.000 us, BMI270/BMP388 logic, ring, counters hoặc ngưỡng jitter.

Files thay đổi cho fix cuối:

| File | Lý do |
| --- | --- |
| `main/wifi_manager.c/.h` | Boot-only NVS/netif/driver/PHY init hoàn tất trước khi trả về; association/DHCP/reconnect vẫn ở worker; cleanup đồng bộ; worker core 0 |
| `main/app_main.c` | Gọi Wi-Fi start trước `sensor_manager_start`; lỗi Wi-Fi không chặn sensor |
| `main/sensor_manager.c` | Sensor Task priority 12 pin core 1; timer period/logic giữ nguyên |
| `sdkconfig` | `esp_timer` task core 1; ISR tiếp tục core 0; Wi-Fi task core 0 |
| `tests/wifi_manager/*`, `tools/test_wifi_manager.py` | Test radio đã ready trước khi start trả về, sync-init cleanup, task-failure retry và worker affinity |
| `main/lte_manager.h` | Chọn UART=0/ADC=0 để đường Wi-Fi hoạt động; giữ nguyên implementation diagnostic và LTE OFFLINE_UNVERIFIED |

TDD/evidence trung gian: test mới RED trước implementation, sau đó 30 kịch bản
PASS, line coverage 98,67% (222/225). Hardware RED đầu tiên chứng minh chuyển
radio init giải quyết startup nhưng retry vẫn làm dồn 1–2 tick; affinity Sensor
Task riêng chưa đủ. Bản timer-core1 cuối mới được dùng để nghiệm thu.

Build cuối ESP-IDF v5.5.5 PASS, ccache off, Ninja -j1. Lần build đầy đủ đầu tiên
gặp lại GCC ICE trong SDK `esp_lcd_panel_rgb.c`; retry cùng source/config PASS,
không sửa SDK. App 860.928 byte (`0xd2300`), còn `0x2dd00` (18%) trong partition
1 MB. Flash app offset 0x10000 PASS, esptool hash verified. ELF SHA-256:
`F11052067FDD94CD92A5EF6B910FC880CDCC08D8045822BB42DA8C71FA9881C7`;
runtime prefix `f11052067` khớp.

Runtime cuối: `build/phase8_2_2/startup_fix/timer_core1_retry.log`, 567,59 s,
SHA-256 `4ed04c2bc255f74c0ad14445523a96b89ebb34f29c19fe0c9fa1043ceab1e760`.

- Startup nhận IP ở 3.277 ms, attempts=1. Hai lần mất đúng AP được ghi ở
  143.327 ms và 365.297 ms; nhận IP lại ở 317.767 ms và 538.677 ms.
- Backoff mỗi lượt bắt đầu lại 1/2/4/8/16/30 giây rồi giữ 30 giây; tổng cộng
  3 `GOT_IP`, chứng minh reset backoff sau IP.
- 112 cửa sổ diagnostic: seq cuối 56.035, ok 56.035, missed_ticks=0,
  imu_err=0, bmp_err=0, diag_dropped=0, cumulative jitter outlier=0.
  Gap toàn phiên 9.918–10.077 us; IMU 99,9–100,0 Hz, BMP 24,9–25,1 Hz.
- Existing extractor PASS 4.000 dòng, CRC32 A7B13734, seq 1500–5499,
  pressure valid 4.000. GNSS self-test PASS; LTE log UART disabled/no AT.
- Chỉ có reset POWERON chủ động đầu capture; không brownout/panic/watchdog.

Một boot ngay sau flash/reset kép bị BMI270 probe fail và app_main dừng; không có
Sensor/Wi-Fi runtime nên bị loại khỏi bằng chứng. Reset lại không đổi firmware
cho phiên cuối 567,59 s PASS. Theo dõi hiện tượng probe rời rạc ở Phase 8.2.6;
không quy lỗi hoặc che bằng retry tự động trong Phase 2.

**Phase 8.2.2: PASS.** Wi-Fi STA/DHCP/reconnect và sensor regression đã có bằng
chứng board thật. AP-off-at-boot hợp lệ chưa được ghi riêng; hai chu kỳ mất AP
sau khi online đáp ứng acceptance reconnect. Phase 3 chỉ bắt đầu khi có lệnh.
