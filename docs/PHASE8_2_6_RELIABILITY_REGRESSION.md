# Phase 8.2.6 — Reliability & Regression

Ngày: 2026-10-31, Asia/Bangkok. Chỉ kiểm thử/củng cố các chức năng Phase 2–5,
không triển khai Backend/App hoặc tự chuyển Phase 7. Kết quả cuối trong progress
và artifact verifier; việc tạo tài liệu này không tự đánh PASS.

## 1. Scope và phép đo

Giữ BMI270 timer 10 ms/core 1, BMP388 every-four-ticks, ring/CSV, GNSS parser,
GPIO/UART mapping và LTE OFFLINE_UNVERIFIED. Không dùng vTaskDelay để thay timer
sensor, không đổi counters/ngưỡng jitter để vượt test. Demo không gọi/SMS/cứu hộ.

Firmware thêm diagnostic serial mỗi 10 s trong worker core 0:

- Internal heap free/minimum/largest block, free 8-bit heap, task count và stack
  high-water mark. Dùng read-only heap counters; không quét integrity toàn bộ
  PSRAM trong sensor path. Minimum heap là low-water lifetime, không phải leak.
- MQTT RX/TX queue occupancy/capacity, outbox bytes, worker stack, accepted/
  failed publish và TX drops. Không gọi SDK từ callback hoặc dưới status lock.
- Queue depth vẫn 4/4; SDK outbox config 8.192 byte. SDK kiểm tra payload trước
  enqueue, serialized topic/header và item metadata có overhead; không coi con
  số config là toàn bộ RAM usage. Snapshot 10 s có thể bỏ lỡ transient peak.

Local diagnostics dưới serial opt-in hiện có, không thêm MQTT topic/schema:

- `TEST_MOTOR`: sau boot 10 s và khi còi off, yêu cầu motor ON 500 ms rồi OFF
  trong cùng worker; không tạo event/alert. Không arm local buzzer khi motor test
  đang active. Existing void vibration APIs không chứng minh driver/acoustic/
  tactile success; cần người dùng xác nhận rung/dừng. Không bật motor auto boot.
- `TEST_PUBLISH_OFFLINE`: chỉ khi MQTT snapshot offline, thử publish một payload
  TEST_ALERT/isTest=true bằng API thật để kiểm tra rejection. Mong đợi
  `expected_offline_rejection=1`, không enqueue/replay. Đây là yêu cầu test chủ
  động, không auto loop/boot. Không dùng FALL_CONFIRMED hoặc tọa độ mẫu.

Thêm `TEST_WIFI_DROP` dưới cùng demo opt-in: gọi API test của Wi-Fi Manager,
SDK disconnect một lần rồi callback/worker có sẵn xử lý backoff/connect/DHCP.
Không thay backoff/reconnect policy, SSID hoặc reset board. Vì người
dùng chưa thể switch AP trong lượt này, dùng station fault injection thật để
kiểm tra Wi-Fi recovery; không gọi đây là bài test AP power outage.

## 2. Test matrix

| Bài test | Bằng chứng cần có |
| --- | --- |
| Boot broker offline | Wi-Fi/IP và acquisition/CSV vẫn chạy ≥60 s, không MQTT connected/auto event |
| Broker recovery/restart | CONNACK/SUBACK/status online trở lại, không reset board, không event UUID tự phát |
| Publish failure | Offline API rejection thật; SDK enqueue/full-outbox/queue failure injection ở host tests ghi riêng |
| Queue pressure | Burst hữu hạn 32 malformed command frames, RX drops tăng, queue hữu hạn và drain/recovery; không actuator/ACK success |
| Buzzer failsafe | Arm local test, broker offline, off sau khoảng 30 s monotonic, không giả command ACK; event vẫn còn context |
| Wi-Fi loss | AP loss nếu có thể; hoặc local SDK station disconnect có log rõ nguồn fault. Đều cần disconnect/backoff→GOT_IP→MQTT SUBACK, không reset |
| STOP/duplicate | Fresh command dừng output, đúng ACK/correlation; repeat cùng payload/ID trả cached result, không thêm execution |
| Event duplication | So sánh UUID/serial request với MQTT frames, không suy ra exactly-once từ một run không thấy duplicate |
| Button/motor | Hold GPIO4 để xác minh polarity/debounce, nhiều press/release không alert; motor rung/ngừng được người dùng xác nhận |
| GNSS/LTE | Self-test/live NMEA parser vẫn tăng; no-fix không biến thành GPS fix; LTE UART disabled/no AT/OFFLINE_UNVERIFIED |
| Soak/resources | Campaign tối thiểu 900 s, heap/task/queue/stack snapshots và sampling; không crash/reset/leak trend nghiêm trọng |

Điều kiện resource cho verifier: queue ≤4/4, outbox serialized snapshot ≤8.320
byte (config + header allowance), worker free stack ≥1.024 byte, task count ≤20
so với baseline quan sát 16. So sánh minimum của năm sample đầu sau warmup 120 s
và năm sample cuối: tail không giảm quá 2 KiB; đánh giá cả diễn biến và trạng thái
network, không thay threshold sau khi thấy fail. Đây là gate demo có giới hạn,
không phải chứng minh không leak trong mọi workload/24 h.

## 3. Build và host checks

Trong ESP-IDF v5.5.5 terminal:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
python -B tools\test_wifi_manager.py
python -B tools\test_mqtt_manager.py
python -B tools\test_device_telemetry.py
python -B tools\test_command_processor.py
python -B tools\test_device_clock.py
python -B tools\test_buzzer_checked.py
$env:IDF_CCACHE_ENABLE='0'
$env:CCACHE_DISABLE='1'
$env:IDF_PY_BUILD_JOBS='1'
$env:ESP_ROM_ELF_DIR='C:\Espressif\tools\esp-rom-elfs\20241011'
idf.py --no-ccache -D CCACHE_ENABLE=0 build
if ($LASTEXITCODE -ne 0) { throw 'Build failed; do not flash' }
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 flash
```

Host fixtures dùng actual manager/processor/encoder source, driver/RTOS/network
boundaries giả; không coi đó là hardware PASS. Không cài/sửa Backend/AI hoặc SDK.
Default flags/template giữ an toàn; board demo có serial/commands opt-in local
từ Phase 5, NTP endpoint đã cấu hình riêng, credentials không ở Git.

## 4. Capture và thao tác thủ công

Đóng monitor đang giữ COM5. Trong terminal thứ nhất, dùng directory mới:

```powershell
docker stop fall-phase3-broker
python -B tools\phase6_capture.py --port COM5 --out-dir build\phase8_2_6\manual_01 --duration 1200 --reset
```

Recorder có hard cap 1..1.800 s, lưu raw serial/MQTT JSONL và status mỗi 2 s.
Khi broker stopped, subscriber retry trên laptop; không giả kết nối của ESP32.
Khi restart, recorder subscribe lại. Chỉ kill PID subscriber của chính session
sau khi kiểm tra unique client ID; deadline native là lớp cleanup dự phòng.

Terminal thứ hai xem status và gửi local diagnostic qua control file whitelist:

```powershell
$capture = 'build\phase8_2_6\manual_01'
Get-Content "$capture\status.json"
Set-Content -Encoding Ascii "$capture\control.json" '{"serial":"TEST_PUBLISH_OFFLINE"}'
# Chờ recorder consume control.json và log rejection, rồi bật broker sau >=60 s.
docker start fall-phase3-broker
```

Mỗi lần chỉ đặt một control file và chờ nó được consume; không ghi đè lệnh đang
chờ. Các string được phép: TEST_ALERT, TEST_ALERT_BUZZER, TEST_MOTOR,
TEST_PUBLISH_OFFLINE, TEST_WIFI_DROP. Recorder không đọc/eval shell từ control file.
Không gửi control thủ công trong khi `phase6_wifi_cycles.py` còn chạy; đợi script
kết thúc hoàn toàn. Producer của script dùng exclusive-create, không replace một
control file đang chờ. Không tính lượt bị mất do điều phối thành firmware recovery.

Khi MQTT/UTC ready, qua boot 10 s, có thể test motor hoặc arm còi local. Chuẩn bị
người nghe/cảm nhận trước khi gửi. Với failsafe, chờ event được broker nhận và
log TEST_BUZZER_ARMED rồi stop broker; giữ USB, theo dõi off sau 30 s, restart
broker và chờ SUBACK. Không dùng auto-off để thay bằng chứng STOP qua command.

Queue pressure/command probes (demo broker credentials tự đọc từ ignored build,
không in password, không chạy mock):

```powershell
python -B tools\phase6_command_probe.py --capture-dir $capture --label burst_01 --burst-invalid
# Sau local buzzer arm, chờ event/status on rồi mới gửi STOP:
python -B tools\phase6_command_probe.py --capture-dir $capture --label stop_01
python -B tools\phase6_command_probe.py --capture-dir $capture --label duplicate_01 --repeat "$capture\stop_01.json"
```

Với event đã auto-off nhưng context vẫn giữ, probe mới phải NOT_BUZZING:

```powershell
python -B tools\phase6_command_probe.py --capture-dir $capture --label after_timeout --expect REJECTED --reason NOT_BUZZING
```

AP test: tắt đúng router/hotspot đang cấp mạng cho ESP32 ≥60 s, bật lại, giữ USB
liên tục và không reset. Phải thấy WIFI_MANAGER offline/GOT_IP mới và MQTT SUBACK
mới; chỉ thấy MQTT disconnect chưa đủ chứng minh mất Wi-Fi. Nếu IP LAN laptop
đổi, xử lý broker/config theo evidence; không nhận recovery khi chưa có log.

Sau ≥900 s và hoàn tất các bài test, restore broker/AP rồi dừng recorder:

```powershell
New-Item -ItemType File "$capture\stop"
python -B tools\extract_sensor_csv.py "$capture\runtime.log" --out-dir "$capture\csv"
python -B tools\analyze_phase6_capture.py $capture
```

Verifier yêu cầu manual_evidence.json ghi các xác nhận thực tế với các key
button_physical/motor_physical/auto_off_acoustic=true; p101_toggled ghi đúng việc
có thực sự switch AP hay không. Không tạo các giá trị này chỉ để vượt test;
thiếu evidence sẽ INCOMPLETE_OR_FAILED. Raw capture
và ACKs có thể chứa vị trí riêng tư, chỉ lưu dưới ignored build, không paste secrets.

## 5. Kết quả và giới hạn

Artifact Phase 6 dưới `build/phase8_2_6/`. Kết quả cuối **PASS cho profile demo
đã đo**, ngày2026-10-31; chi tiết trong mục27 của [progress](PHASE8_2_PROGRESS.md).
Các capture lỗi bên dưới vẫn là FAIL, không sửa/xóa để đạt kết quả cuối.

| Capture | Kết quả thực tế |
| --- | --- |
| `campaign/` | 1.042,64 s/207 sensor windows, 0 missed/outlier/error/reset bất thường; boot broker offline, broker recovery/restart, bounded queue pressure, real STOP/cached ACK, button/motor/auto-off xác nhận thật. Chưa có Wi-Fi link fault trong run này |
| `wifi_fault/` | SDK disconnect và IP recovery thật, sau đó TG1WDT_SYS_RST; FAIL |
| `wifi_repro/` | Reconnect có SUBACK nhưng 1 missed/4 outlier; FAIL |
| `network_pinned/` | Chỉ pin network core0 chưa đủ: cycle2 có 2 missed/10 outlier; FAIL |
| `irq_core1/` | Thêm I2C IRQ core1, cycle1/2 sạch; cycle3 có 2 outlier rồi Cache error/MMU entry fault; FAIL |
| `no_modem_sleep/` | Final profile: 1.000,19 s/199 sensor windows,8 real SDK disconnect/recovery,10 SUBACK,0 missed/outlier/error/reset bất thường. CSV4.000/CRC079119B5; STOP thật/cached ACK/broker restart/offline rejection/auto-off lặp lại đạt |

Source cần sửa tối thiểu để phân tách tài nguyên khi đo:

- TCP/IP task và SDK MQTT task pin core0; Sensor Task/esp_timer task giữ core1,
  timer ISR vẫn core0. Không tăng
  task priority của sensor hay thay timer/threshold để che jitter.
- `sensor_bus_create()` khởi tạo bus trên boot helper core1 để SDK cấp I2C IRQ
  cùng core acquisition; app_main đợi hoàn tất trước sampling. Config I2C, GPIO,
  bus clock và driver Bosch giữ nguyên. Đây là sửa đường khởi tạo đã PASS vì
  runtime network fault phát hiện regression; helper riêng có host test.
- Wi-Fi đặt `WIFI_PS_NONE` trước start để đo profile radio luôn thức. Có tăng
  điện năng; chưa đánh giá pin/wearable power budget. Hardware evidence cuối
  chỉ áp dụng profile này, chưa chứng minh nguyên nhân gốc cache fault trước đó.

Host regression mới nhất: Wi-Fi32/32 (98,70%), MQTT22/22 (99,59%), telemetry18/18
(91,26%), command processor99,25%, clock/checked actuator/boot bus helper PASS.
Build/flash profile cuối PASS (ELF1840d338d, app1.052.816 bytes/31% free), không
thay SDK, watchdog hoặc GNSS/LTE/actuator driver.

Người dùng đã xác nhận motor rung ngắn rồi dừng và còi tự dừng khi broker tắt;
đã giữ/bấm GPIO4, log xác nhận active-high. Người dùng chưa thể switch AP AP_DEMO;
không ghi AP power outage là PASS. SDK station disconnect là phép đo khác,
cần ghi rõ khi báo cáo.

Phase 7/Backend/App, production TLS/security, GNSS fix, LTE data/MQTT và
24-hour soak không nằm trong campaign này. Root cause của các reset trước
chưa được chứng minh; mọi capture lỗi và ELF phù hợp được giữ để đối chiếu.

Verifier tổng hợp27/27 PASS sau khi hai recorder đóng/hash raw khớp:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
python -B tools\analyze_phase6_capture.py build\phase8_2_6\campaign --network-capture build\phase8_2_6\no_modem_sleep
python -B tools\extract_sensor_csv.py build\phase8_2_6\no_modem_sleep\runtime.log --out-dir build\phase8_2_6\no_modem_sleep\recheck_csv
```

Mong đợi JSON `status: PASS`,27 checks=true; extractor `PASS: 4000 rows,
CRC32=079119B5`. Đây là kiểm tra evidence đã lưu, không reset/flash thiết bị.
Muốn đo hardware lại thì dùng recorder với **out-dir mới**, không overwrite run.

Run cuối: internal heap tail190.311/min140.984/largest110.592 bytes, 100 samples;
steady min5 sample đầu190.303→cuối190.311, tasks tail16, worker free stack
telemetry3.400/MQTT2.952 bytes. Burst32 invalid frame làm RX drop28 rồi drain0;
đây là backpressure có giới hạn, không phải assertion rằng không bao giờ mất
command. Hai event UUID từ hai local requests, không auto event khi reconnect.
STOP thực thi một lần; duplicate trước/sau broker restart giữ processedAt.
Auto-off682.551→712.621ms (30,070s) không tạo ACK command mới, event giữ nguyên;
command mới sau recovery bị NOT_BUZZING đúng trạng thái.

Lịch cycle8 ban đầu bị lệnh motor của người vận hành trùng control slot, không
thực thi SDK drop. Giữ nguyên lỗi timeout ở `wifi_cycles_first7.json`; retry
riêng cùng run không reset đã đạt, tổng8 thực sự là7+1. Raw/actions và
`wifi_cycles_summary.json` xác minh điều này; producer đổi sang exclusive-create
và tài liệu cấm chạy concurrent control producers.

Evidence là **hai run/image riêng**: `campaign/` (ELF4fa252585,1.042,64s) chứa
xác nhận button/motor/acoustic của người dùng; `no_modem_sleep/` (ELF1840d338d,
1.000,19s) kiểm thử profile cuối, với button_presses0. Các đường actuator/button
được bảo toàn; không gán xác nhận của run cũ thành quan sát vật lý mới. Không
gộp thời lượng thành một soak35 phút cùng binary. `final_evidence_manifest.json`
và `campaign/verification.json` ghi rõ các vai trò này.

Raw SHA-256 final:
`33a3d6c280740aefd7ea296c735a15b9eca1e2a900f9a120f1f85ca445cdd731`.
COM5 đã đóng, test subscriber đã dọn, broker demo online trở lại. Actual-secret
scan82 files và tracked diff không có password match; credentials vẫn ignored.
Các biến thể cũ đã lỗi không được coi là profile tích hợp đã nghiệm thu.

Chỉ chuyển sang Phase8.2.7 khi người dùng yêu cầu `làm phase 7`; Backend/App
thật và adoption ACK profile của Member3 vẫn cần xác minh ở phase đó.

## 6. Files trong phạm vi Phase 6

| Files | Mục đích |
| --- | --- |
| `main/app_main.c`, `main/CMakeLists.txt`, `main/sensor_bus.c`, `main/sensor_bus.h` | Boot helper cấp bus/I2C IRQ core1; không đổi bus config/driver/timing |
| `main/wifi_manager.c`, `main/wifi_manager.h` | Task-only SDK disconnect diagnostic; cấu hình modem awake trước start, checked errors |
| `main/mqtt_manager.c` | Resource counters trong worker; giữ transport/command contract |
| `main/device_telemetry.c` | Heap/task/stack logs; local motor/offline-publish/Wi-Fi fault diagnostics |
| `sdkconfig` | Pin TCP/IP và SDK MQTT task core0; alias Kconfig tương ứng |
| `tests/wifi_manager/host_test.c`, `tests/wifi_manager/host_sdk.h`, `tools/test_wifi_manager.py` | Local-drop, awake-before-start và init-error coverage |
| `tests/mqtt_manager/host_test.c`, `tests/mqtt_manager/host_sdk.h`, `tests/device_telemetry/host_test.c`, `tests/device_telemetry/host_sdk.h`, `tools/test_device_telemetry.py` | Fake SDK resource APIs, motor/offline probe và regressions |
| `tests/sensor_bus/host_test.c`, `tests/sensor_bus/host_sdk.h`, `tools/test_sensor_bus.py` | Boot allocation/core/error tests với fake SDK |
| `tools/phase6_capture.py`, `tools/phase6_command_probe.py`, `tools/phase6_wifi_cycles.py`, `tools/analyze_phase6_capture.py` | Real COM5/MQTT recorder, actual command/queue probes, fault cycles, completed-capture/hash verifier |
| `docs/PHASE8_2_PROGRESS.md`, tài liệu này | Kết quả, giới hạn, lỗi chưa/đã tái hiện, manual evidence và cách đo lại |

Các file dirty khác đã có trước Phase 6 được bảo toàn. Header credentials không
đổi trong Phase 6 và vẫn ignored. Không commit/push/merge. Không viết lại AI,
Backend hay API của Member 3.
