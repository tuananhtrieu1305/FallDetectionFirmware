# Phase 8.2.4 — Status & TEST_ALERT Publishing

Sau Phase 5: xem [STOP_BUZZER & Real ACK](PHASE8_2_5_STOP_BUZZER_REAL_ACK.md) về
SNTP/UTC, lastCommand và local TEST_ALERT_BUZZER opt-in mới. Plain TEST_ALERT giữ
hành vi không bật còi; mô tả dưới đây ghi baseline Phase 4.

Ngày triển khai: 2026-10-31 (Asia/Bangkok). Nguồn schema/topic là
[DEVICE_BACKEND_CONTRACT.md](DEVICE_BACKEND_CONTRACT.md), `mqtt-v1`.
Không sửa contract, Backend, AI hoặc triển khai STOP_BUZZER/ACK trong phase này.

## 1. Kiến trúc và dữ liệu thật

`device_telemetry` là worker priority 2/core 0, stack 6.144 byte, chu kỳ 100 ms.
Task đọc snapshot MQTT/GNSS và LEDC duty qua API chỉ đọc mới
`alert_manager_get_buzzer_state()`. Sensor Task, timer BMI270 10 ms, BMP388 every
four ticks, ring/CSV, GPIO/UART1/UART2, Wi-Fi và MQTT callbacks giữ nguyên.
GNSS snapshot có mutex timeout 20 ms; chỉ worker thấp ưu tiên chờ, không sensor.

Publisher dùng `mqtt_manager_publish()` với queue hữu hạn Phase 3. Không gọi
network publish từ sensor/callback. JSON dùng buffer tối đa 1.024 byte; chỉ
identifier đã kiểm tra ASCII và hằng firmware vào quoted strings, kiểm tra
truncation. Không thêm JSON library hoặc đổi partition/sdkconfig.

| Topic | QoS | Retain | Khi nào gửi |
| --- | --- | --- | --- |
| `iot/devices/{deviceId}/status` | 1 | true | Sau SUBACK mỗi connection epoch, mỗi 10 s, hoặc LEDC state thay đổi |
| `iot/devices/{deviceId}/event` | 1 | false | Một yêu cầu serial hợp lệ, đã opt-in local và MQTT ready |

Status có `mode=REAL`, `lteReady=false`, không giả LTE online. `alertState` là
`BUZZER_ON` khi driver LEDC báo duty khác 0, `IDLE` khi duty 0, `null` nếu không
đọc được. Đây là trạng thái output của demo hiện tại, không phải kết luận có/
không có người ngã, âm thanh thực tế hoặc full fall-alert state machine. Không
tạo ACK hoặc `lastCommand`. LWT offline envelope Phase 3 được giữ nguyên; online
status sau reconnect thay thế retained offline status.

UTC chỉ dùng từ current GNSS fix thật, với monotonic age từ 0 đến 5 s, epoch
2020..2099; bù age monotonic để tạo UTC hiện tại. Không lấy build time, uptime,
PC clock hoặc dữ liệu GNSS self-test làm UTC. Chưa có clock sync khác; khi không
đủ bằng chứng, `occurredAt`/status `observedAt` là `null`. Location lấy đúng
snapshot CURRENT/LAST_KNOWN thực, lat/lon finite và trong bounds, observedAt là
thời gian của fix; UNAVAILABLE có cả ba trường null. Không sửa GNSS parser.
Nullability status/strict DTO phía Backend vẫn cần xác minh tại Phase 7.

Ví dụ status khi thiết bị online, còi đang idle, chưa có UTC:

```json
{"schemaVersion":1,"deviceId":"waist-esp32s3-001","online":true,"mode":"REAL","lteReady":false,"alertState":"IDLE","observedAt":null}
```

Ví dụ schema TEST_ALERT (UUID minh họa, không phải bằng chứng hardware):

```json
{"schemaVersion":1,"eventId":"123e4567-e89b-42d3-a456-426614174000","deviceId":"waist-esp32s3-001","eventType":"TEST_ALERT","isTest":true,"occurredAt":null,"modelVersion":"firmware-test-v1","confidence":null,"location":{"type":"UNAVAILABLE","lat":null,"lon":null,"observedAt":null}}
```

`firmware-test-v1` định danh generator test của firmware; không phải model AI.
Không tự dùng `mock-v1`, confidence giả, FALL_CONFIRMED hoặc tọa độ mẫu. Backend
phải phân luồng test theo `eventType=TEST_ALERT`/`isTest=true` và dedup bằng
`(deviceId,eventId)` theo contract; không dispatch cứu hộ thật từ các event này.

## 2. Kích hoạt local có kiểm soát

Default trong source/template: `NETWORK_TEST_ALERT_SERIAL_ENABLED=0`. Để demo,
thêm vào **ignored** `main/network_config.local.h`:

```c
#define NETWORK_TEST_ALERT_SERIAL_ENABLED 1
```

Build/flash lại. Worker chỉ cài RX driver UART0 khi opt-in; giữ baud console
115200, không thay UART1/GNSS hoặc UART2/LTE. Nếu UART0 driver đã có owner, hoặc
console không phải UART0, start bị từ chối thay vì chiếm driver. Task creation
fail sẽ gỡ driver vừa cài. UART0 test input không phải production control API.

Gõ đúng `TEST_ALERT` rồi Enter (`CR`, `LF` hoặc `CRLF`) qua serial monitor:

- Chỉ nhận khi MQTT connected/subscribed, không có event đang retry và đã qua
  cooldown 5 s. Mỗi yêu cầu được chấp nhận tạo UUID v4 bằng RNG của ESP32 khi
  Wi-Fi hoạt động. Serial parser hữu hạn 31 ký tự, đọc tối đa 32 byte/vòng.
- Input khác, quá dài hoặc có control/binary byte bị bỏ. CRLF không tạo hai
  event; burst trong cooldown bị từ chối. Không log nội dung input tùy ý.
- Boot, reconnect, button GPIO4 và sensor synthetic CSV không phát TEST_ALERT.
  Offline request không queue để phát sau reconnect. Chỉ một event payload
  pending, không queue lịch sử offline, không tạo event mới từ retry.
- TEST_ALERT chỉ gửi dữ liệu test; không gọi buzzer/vibration, SMS hoặc 115.
  Existing one-shot buzzer boot diagnostic vẫn độc lập và không bị thay đổi.

Sau demo, đặt macro local về 0 và build/flash để tắt input test. Đổi header mà
chưa flash không thay đổi bản firmware đang chạy. Không đưa credentials vào Git.

## 3. Publish failure và giới hạn giao nhận

`ESP_OK` của publish chỉ là accepted vào application queue, không phải broker
delivery. Log ghi rõ `queued (not delivery confirmation)`. Firmware không ACK
thực thi command và không báo buzzer đã dừng từ MQTT PUBACK.

Status queue failure retry sau 1 s. Test-event queue failure tối đa ba lần, cách
1 s, giữ nguyên payload/UUID/timestamp. Mất connection hoặc đổi epoch trước
enqueue hủy pending; không tự replay lúc reconnect. Một khi queue đã nhận,
không retry ứng dụng để tránh tạo bản gửi thứ hai ngoài SDK QoS 1.

Transport enqueue failure/stale epoch/outbox full do MQTT Manager đếm; publisher
log cảnh báo khi counter tăng. Không có receipt từng event hoặc storage bền vững:
event đã vào app queue vẫn có thể thất lạc trước SDK acceptance. Phải xem broker
và event ID để xác nhận delivery; không khẳng định guaranteed delivery. SDK
QoS 1 có thể giao trùng sau reconnect; Backend cần dedup. Phase 6 sẽ kiểm tra
failure/resource campaign rộng hơn.

## 4. Build, test và lặp lại

Trong ESP-IDF v5.5.5 terminal:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
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

Board giữ USB data, điểm phát Wi-Fi bật, broker demo chạy đúng IP LAN local.
Không để monitor khác giữ COM5. Chạy script test với output directory mới:

```powershell
python -B tools\test_phase4_device.py --port COM5 --out-dir build\phase8_2_4\manual_01
if ($LASTEXITCODE -ne 0) { throw 'Hardware test failed; inspect capture' }
python -B tools\extract_sensor_csv.py build\phase8_2_4\manual_01\runtime.log --out-dir build\phase8_2_4\manual_01\csv
```

Script reset board một lần, subscribe broker demo bằng native Mosquitto, đọc
JSON thật, kiểm tra không auto event, input sai/cooldown, gửi hai event, stop/start
**chỉ** container `fall-phase3-broker`, kiểm tra offline request không replay,
online status retained và event không retained, chờ CSV/sampling. Không chạy mock
hoặc gửi STOP_BUZZER. Không in password; dữ liệu tọa độ có thể riêng tư nên log
chỉ dưới ignored build. Broker credentials phải do helper Phase 3 chuẩn bị.
Nếu container chết/start lỗi, script cố start lại khi cleanup. PASS mong đợi:
`First/Second controlled TEST_ALERT`, `Reconnect: fresh online status`, kết quả
`hardware_verified=true`, `events=2`; CSV PASS 4.000 rows. Khi script fail, kiểm
tra log thực tế; không coi mọi nguyên nhân là firmware fail hoặc tự đánh PASS.

Manual monitor thay cho script: `idf.py -p COM5 monitor`, gõ `TEST_ALERT` Enter
sau SUBACK; subscriber độc lập xác nhận JSON/event ID. Không mở đồng thời script
và monitor. Không gửi password qua chat.

## 5. Kết quả và phần chưa xác minh

Host tests: 16 scenario PASS, publisher line coverage 96,18%; SDK/RTOS/GNSS/
actuator boundaries giả, không hardware evidence. Test trước code đã RED; các
kịch bản bao gồm epoch/reconnect, queue retry tối đa ba lần giữ nguyên payload,
serial invalid/overflow/binary/cooldown, status và GNSS UTC/location semantics.
MQTT regression 22 scenario PASS/99,58% coverage.

ESP-IDF build/COM5 flash PASS, hash verified; app 1.028.736 byte (`0xfb280`),
còn 19.840 byte (`0x4d80`, 2%) partition 1 MB. Không đổi partition hoặc SDK. Runtime
ELF prefix `69846a2b8` khớp SHA-256
`69846A2B891DF31DD4FF7A36EE15E34A1E174434FD56D54D1DF8359E0D8742B3`.
Kết quả hardware cuối cùng và artifact được ghi trong progress mục Phase 4.

Final hardware retest PASS: 102,59 s, hai TEST_ALERT/hai UUID khác nhau, 12 frame
status trong subscriber; invalid input/cooldown/offline request và reconnect
không phát event phụ. Kiểm tra event không retained thực hiện trước broker
restart; status retained online đọc lại được sau recovery. 19 cửa sổ diagnostic,
seq/ok 9.508/9.508, không missed tick/outlier/IMU/BMP error, gap 9.689–10.295 us;
CSV extractor PASS 4.000 rows/CRC `1C4EF049`. Broker xác nhận event q1/r0, status
q1/r1 và PUBACK của device thật. Status BUZZER_ON/IDLE khớp driver diagnostic;
event UTC/location thực tế unavailable nên null. Artifact chính:
`build/phase8_2_4/hardware_retest/{runtime.log,mqtt_frames.json,results.json,broker_final.log,additional_verification.json}`.
Không có panic/reset bất thường; cleanup cuối cùng chỉ còn server Mosquitto,
COM5 đã đóng. Firmware trên board giữ serial test enabled theo local opt-in.

Chưa xác minh GNSS fix/UTC/location thật CURRENT/LAST_KNOWN ngoài trời (host
fixtures không thay bằng chứng fix), TLS, Backend persistence/App notification,
ACK/STOP_BUZZER, long soak, heap/resource fault injection. Firmware không thể
chứng minh Backend ngoài phạm vi truy cập sẽ xử lý test đúng; broker này là demo
riêng, không có tích hợp cứu hộ thật trong bài test.

Phase 5 chỉ thực hiện khi có lệnh; cần chốt ACK/expiry semantics với Member 3,
đọc actuator API thực và đánh giá budget flash còn lại.
