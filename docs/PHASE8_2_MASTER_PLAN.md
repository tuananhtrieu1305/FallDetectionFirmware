# Phase 8.2 — Master Plan

Ngày thiết lập: 2026-10-28 (Asia/Bangkok).
Nguồn yêu cầu: master instructions của người dùng cho Phase 8.2.
Đây là kế hoạch điều phối; việc tạo tài liệu không khởi động bất kỳ phase con nào.
Tiến độ và bằng chứng được lưu riêng trong [PHASE8_2_PROGRESS.md](PHASE8_2_PROGRESS.md).

## 1. Tổng quan và phạm vi

Thiết bị wearable đeo vùng bụng/eo dùng cảm biến chuyển động và mô hình AI tại
ESP32-S3 để phân biệt ngã thật với ngồi nhanh, nằm nhanh và chuyển động mạnh.
Hệ thống dự kiến cảnh báo bằng buzzer/vibration, cho phép xác nhận bằng button,
gửi Backend và Android/Web, hỗ trợ vị trí. Cơ chế leo thang cứu hộ là kiến trúc
tương lai với điều kiện an toàn riêng; demo không gọi 115 hoặc cứu hộ thật.

Phân công:

- Member 1: hardware/firmware, driver, Sensor Manager, ring buffer, GNSS/LTE/Wi-Fi/
  MQTT, runtime AI, alert state machine, button/vibration/buzzer và hardware test.
- Member 2: dataset, training, quantization, đánh giá và bàn giao model AI.
- Member 3: Mosquitto, Spring Boot, PostgreSQL, REST/WebSocket, Android và Web Admin.

Phase 8.2 chỉ tích hợp Wi-Fi/MQTT vào firmware và kiểm thử giao tiếp hai chiều.
Không tự viết lại Backend/AI hoặc thay đổi API thuộc Member 2/3.

Môi trường do người dùng cung cấp (cần xác minh ở phase liên quan):

| Hạng mục | Cấu hình |
| --- | --- |
| OS / IDE | Windows 11 / VS Code |
| Project | `C:\Workspace\FallDetectionFirmware` |
| Framework | ESP-IDF v5.5.5 |
| ESP-IDF root | `C:\esp\v5.5.5\esp-idf` |
| Board | ESP32-S3 N16R8; flash 16 MB, PSRAM 8 MB |
| Serial | COM5 |
| BMI270 / BMP388 | I2C SDA GPIO8, SCL GPIO9; 100 Hz / 25 Hz |
| Button | GPIO4; yêu cầu ban đầu ghi active-low, source audit 8.2.1 là active-high (chưa đổi code) |
| Vibration | GPIO5 |
| Buzzer MH-FMD | GPIO6, PWM khoảng 2.5 kHz |
| NEO-M8N GNSS | UART1, GPIO15 RX, 9600 baud |
| A7670C LTE | UART2, GPIO17 TX, GPIO18 RX |
| Wi-Fi | Tích hợp trên ESP32-S3, mạng 2.4 GHz |

Baseline do người dùng báo cáo: bring-up, BMI270 100 Hz, BMP388 25 Hz,
Sensor Manager, CSV/ring buffer, button/vibration/buzzer, GNSS UART/NMEA parser
và self-test đã PASS. Chưa xác minh lại trong bước khởi tạo kế hoạch.
GNSS fix ngoài trời, LTE data/MQTT và model AI hoàn chỉnh chưa PASS.
Phase 7 LTE chỉ PARTIAL PASS: AT OK, SIM được nhận diện, từng có CSQ hợp lệ;
UART chưa ổn định; registration/APN/IP/MQTT/call/SMS chưa xác minh.
Giữ LTE ở `OFFLINE_UNVERIFIED`.

Phase 8.1 đã có tài liệu contract và mock. Phải đọc source thật ở phase được
yêu cầu, đặc biệt `docs/DEVICE_BACKEND_CONTRACT.md` và `tools/mock_device.py`;
không suy ra firmware đã hỗ trợ MQTT từ việc mock tồn tại.

## 2. Mục tiêu và nguồn contract

Luồng dữ liệu: ESP32-S3 → Wi-Fi → Mosquitto → Spring Boot → Android/Web.
Luồng điều khiển: Android/Web → Spring Boot → Mosquitto → ESP32-S3 → actuator → ACK.

Kết quả cần đạt: kết nối/reconnect Wi-Fi và MQTT; status thực tế; TEST_ALERT với
`isTest=true`; subscribe/validate STOP_BUZZER; dừng còi thật và ACK sau thực thi;
reliability/regression; end-to-end thật; tài liệu bàn giao.

[DEVICE_BACKEND_CONTRACT.md](DEVICE_BACKEND_CONTRACT.md) là nguồn chuẩn `mqtt-v1`.
Không tự tạo topic, field, command hoặc ACK ngoài contract. Theo tài liệu hiện có,
event/status/location/command dùng QoS 1, health QoS 0; chỉ status retained.
Thiết bị thật phải phân biệt với mock; không chạy đồng thời cùng device ID.

Các điểm cần giải quyết khi audit/thiết kế, không tự mở rộng contract:

- Contract mô tả ACK mock trong status (`lastCommand.result=ACK_SIMULATED`),
  chưa định nghĩa đầy đủ schema/result cho ACK thực thi thiết bị thật.
- Command có `issuedAt`, yêu cầu kiểm tra expiration nhưng chưa nêu TTL/field
  expiry/quy tắc khi chưa có UTC. Chưa chốt mức bảo đảm replay qua reboot.
- Quy tắc authorization, event correlation, alertState sau khi dừng còi và
  cách biểu diễn dữ liệu unavailable phải được đối chiếu source thật và thống
  nhất với Member 3 nếu contract chưa đủ; không đơn phương sửa API.
- Broker `localhost:1883` trong tài liệu là cho development trên máy tính;
  thiết bị thật cần địa chỉ LAN có thể truy cập. Chưa có cấu hình broker thật.

Cập nhật 2026-10-31: người dùng đã chấp thuận
[profile command/ACK demo Phase 5](PHASE8_2_5_DEMO_COMMAND_CONTRACT.md), gồm
EXECUTED/REJECTED/FAILED, TTL 30 s/skew 5 s, thiếu UTC từ chối và dedup RAM 16
lệnh. Đây là authorization cho demo firmware, không cần hỏi lại cùng đề xuất;
Member 3/Backend vẫn cần đồng bộ trước integration. Xem progress về bằng chứng.

## 3. Điều phối và dependency

| Lệnh | Phase | Tên | Dependency chính |
| --- | --- | --- | --- |
| `làm phase 1` | 8.2.1 | Repository Audit & Baseline | Lệnh người dùng, repository hiện tại |
| `làm phase 2` | 8.2.2 | Wi-Fi Manager | Kết quả audit và vị trí tích hợp từ 8.2.1 |
| `làm phase 3` | 8.2.3 | MQTT Manager | Wi-Fi/API 8.2.2; broker/config cho test thật |
| `làm phase 4` | 8.2.4 | Status & TEST_ALERT Publishing | MQTT 8.2.3; contract và trạng thái firmware |
| `làm phase 5` | 8.2.5 | STOP_BUZZER & Real ACK | 8.2.3–4; actuator API; ACK/expiry đã thống nhất |
| `làm phase 6` | 8.2.6 | Reliability & Regression | Các chức năng 8.2.2–5 sẵn sàng kiểm thử |
| `làm phase 7` | 8.2.7 | End-to-End Integration | 8.2.4–6; broker, Backend và App/Web thật |
| `làm phase 8` | 8.2.8 | Documentation, Handoff & Git | Source/kết quả 8.2.1–7, kể cả phần chưa xác minh |

Chỉ làm phase được chỉ định, không tự chuyển sang phase kế tiếp. Nếu dependency
chưa hoàn tất, giải thích ảnh hưởng và chỉ xử lý phần cần thiết trong phạm vi
được phép. Có thể chuẩn bị code khi hardware test trước còn thiếu nếu khả thi,
nhưng phải ghi rõ dependency chưa xác minh và không suy diễn PASS.

## 4. Công việc và acceptance criteria từng phase

### Phase 8.2.1 — Repository Audit & Baseline

Công việc:

1. Kiểm tra Git branch/status/commit, cấu trúc repository và thay đổi local.
2. Đọc app_main, CMakeLists, sensor sampling/ring buffer, GNSS/LTE Manager,
   button/vibration/buzzer và alert state machine nếu tồn tại.
3. Đọc đầy đủ contract và mock; kiểm tra SDK config và Git ignore.
4. Build baseline khi môi trường cho phép; ghi lỗi/blocker nếu có.
5. Đề xuất vị trí tích hợp Wi-Fi/MQTT, danh sách file cần sửa/tạo tương thích
   source thật và giữ các chức năng đã PASS.

PASS: hiểu kiến trúc; xác định file tích hợp; không mất thay đổi local; baseline
build thành công hoặc có blocker môi trường được ghi rõ; có kế hoạch phù hợp
source thật. Không thêm Wi-Fi/MQTT ở phase này.

### Phase 8.2.2 — Wi-Fi Manager

Công việc:

1. Thiết kế module phù hợp source; dùng esp_wifi, esp_netif, esp_event, nvs_flash.
2. Station mode, SSID/password cấu hình an toàn, mạng 2.4 GHz, DHCP.
3. Xử lý disconnect/reconnect với backoff, tránh vòng lặp quá mức; cung cấp API
   connection status; tích hợp app_main giữ nguyên trình tự init cần thiết.
4. Không commit credentials; kiểm thử sensor tiếp tục hoạt động.

PASS: build thành công; ESP32 kết nối Wi-Fi thật, nhận IP hợp lệ, reconnect sau
mất mạng; sensor vẫn hoạt động bình thường. Thiếu credentials hoặc hardware test:
`CODE_DONE_NEEDS_HARDWARE_TEST` nếu phần code đã hoàn thành.

### Phase 8.2.3 — MQTT Manager

Công việc:

1. Tích hợp ESP-MQTT tương thích ESP-IDF v5.5.5; cấu hình broker URI, credentials
   an toàn và client ID/device ID phù hợp.
2. Quản lý connected/disconnected/error, reconnect; subscribe theo contract;
   tổ chức API publish và Last Will cho status offline theo contract.
3. Kiểm soát message length, fragmentation, buffer/queue hữu hạn và lỗi tài nguyên.
4. Không block sensor task; không thực thi actuator từ MQTT callback.

PASS: thiết bị thật kết nối broker, broker xác nhận client, subscribe đúng topic,
reconnect hoạt động, không lỗi nghiêm trọng/regression. Chưa triển khai đầy đủ
TEST_ALERT hoặc STOP_BUZZER trong phase này.

### Phase 8.2.4 — Status & TEST_ALERT Publishing

Công việc:

1. Đọc lại contract/mock; publish status từ trạng thái thật (`mode=REAL`),
   phân biệt dữ liệu thật/test/unavailable; không báo LTE online hoặc GNSS fix giả.
2. Implement TEST_ALERT với `isTest=true`, cơ chế kích hoạt có kiểm soát;
   không tự phát liên tục khi boot/reconnect.
3. Đảm bảo event ID/correlation và JSON đúng contract; xử lý publish failure.
4. Nếu chưa có UTC, tuân thủ null theo contract; không giả timestamp/model/location.
5. Dùng MQTT subscriber kiểm tra payload từ ESP32 thật và quy tắc retained/QoS.

PASS: broker nhận status và TEST_ALERT từ ESP32 thật; JSON đúng contract;
`isTest=true`; không kích hoạt cứu hộ thật. Không tạo FALL_CONFIRMED giả, gọi
115 hoặc phát cảnh báo cứu hộ thật.

### Phase 8.2.5 — STOP_BUZZER & Real ACK

Công việc:

1. Subscribe command, parse JSON, validate command và target device/topic,
   eventId, commandId, current alert state và authorization.
2. Xử lý duplicate/replay, expiration theo contract đã thống nhất; ghi rõ mức
   bảo đảm và giới hạn xác thực/ủy quyền của demo broker, kể cả khi thiếu UTC.
3. Dispatch sang worker/actuator API hiện có; dừng buzzer thật, lấy kết quả.
4. ACK theo contract sau khi thực thi thành công; correlation đúng; xử lý
   invalid command, duplicate và failure một cách xác định.

PASS: command hợp lệ dừng còi thật; ACK success có correlation đúng sau thực thi;
command sai bị từ chối; duplicate/replay đúng mức bảo đảm contract; không crash
hoặc regression. Không thao tác GPIO6 từ MQTT callback; không ACK_SIMULATED;
không ACK success sớm. STOP_BUZZER chỉ dừng còi, không mặc nhiên hủy ngã hoặc
quy trình cảnh báo. Thiếu thỏa thuận ACK/expiry phải ghi blocker cho phần phụ thuộc.

### Phase 8.2.6 — Reliability & Regression

Công việc:

1. Thử Wi-Fi/MQTT disconnect/reconnect, broker restart, boot khi broker offline.
2. Kiểm tra heap/task/error handling, publish failure, duplicate command/event,
   queue hữu hạn và recovery.
3. Kiểm tra sensor jitter/sampling, button/vibration/buzzer, GNSS parser và LTE
   safe mode. Ghi thời lượng, kịch bản, log và kết quả thực tế.

PASS: không reset/crash bất thường; network recovery hoạt động; không có queue
vô hạn hoặc lỗi tài nguyên nghiêm trọng; hardware cũ vẫn PASS; có bằng chứng
regression phù hợp. Không thay timing BMI270 100 Hz bằng vTaskDelay.

### Phase 8.2.7 — End-to-End Integration

Công việc:

1. Chuẩn bị Mosquitto local, kiểm tra IP/port/credentials/ACL trong mạng kiểm soát.
2. Test status và TEST_ALERT từ thiết bị thật; kiểm tra Spring Boot subscriber,
   schema, persistence nếu có và Android/Web hiển thị cảnh báo test.
3. Test App/Web gửi STOP_BUZZER qua Backend, broker chuyển command, ESP32 dừng
   còi, ACK trở về Backend/App; ghi kết quả từng điểm và correlation.
4. Không giả định Backend/Android/Web source có trong repo firmware. Khi thiếu
   quyền truy cập/hệ thống, chuẩn bị test scripts/instructions và ghi chưa hoàn tất.

PASS: xác minh thật cả device → Backend → App/Web và command → device → ACK.
Không dùng kết quả mock làm bằng chứng thiết bị thật đã PASS.

### Phase 8.2.8 — Documentation, Handoff & Git

Công việc:

1. Rà soát source, contract compatibility và secrets trong Git diff.
2. Hoàn thiện `docs/PHASE8_WIFI_MQTT_HANDOFF.md`: kiến trúc, topics, payload
   examples đúng contract; Backend subscribe/xử lý TEST_ALERT; App/Web gửi
   STOP_BUZZER qua Backend; ACK/error handling và giới hạn bảo đảm.
3. Tổng kết từng mục PASS/PARTIAL/NOT TESTED, các lỗi còn lại, hướng dẫn
   PowerShell build/flash/test và bàn giao cho Member 3.
4. Kiểm tra working tree, chuẩn bị commit message và merge checklist.

PASS: tài liệu khớp firmware; không có credentials trong repository; test yêu
cầu có bằng chứng hoặc nêu rõ phần chưa đạt; working tree được kiểm tra; có
hướng dẫn bàn giao. PASS của tài liệu không biến các phase chưa test thành PASS
và không đồng nghĩa toàn bộ Phase 8.2 đã nghiệm thu.
Không tự commit, push hoặc merge.

## 5. Safety constraints và bảo toàn baseline

- Đọc source thật trước khi viết; không ghi đè firmware đã PASS. Nếu cần sửa
  module đã PASS, giải thích lý do kỹ thuật, giữ diff tối thiểu và test regression.
- Giữ BMI270 100 Hz, BMP388 25 Hz, GPIO/UART mapping, GNSS parser; không đổi
  cách định thời BMI270 sang vTaskDelay.
- LTE luôn `OFFLINE_UNVERIFIED` đến khi có xác minh riêng; không gọi/SMS thật,
  không gọi 115, không dùng TEST_ALERT để kích hoạt cứu hộ thật.
- Không commit SSID/password/MQTT credentials; không đưa secrets vào log hoặc
  ví dụ. Demo broker chỉ dùng mạng kiểm soát; production cần TLS, authorization,
  broker ACL và phân quyền theo thiết bị.
- Mọi topic/JSON/command/ACK theo contract; thay đổi contract cần thống nhất
  Firmware và Member 3 trước triển khai, không tự đổi API Member 2/3.
- Callback quan trọng không blocking; MQTT callback không điều khiển actuator.
  ACK success chỉ sau thành công thực thi thật, không dùng ACK_SIMULATED.
- Không dùng git reset --hard, git clean -fd, force push hoặc thao tác phá hủy
  thay đổi local; không tự commit/push/merge.
- Ưu tiên module rõ ràng, dễ bảo trì và demo ổn định; không đánh dấu PASS khi
  chưa có bằng chứng; không coi mock online là wearable online.

## 6. Workflow, kiểm thử và bằng chứng

Mỗi lệnh `làm phase n`:

1. Load AGENTS.md, master plan, progress, contract/source liên quan; kiểm tra Git.
2. Kiểm tra dependencies, thay đổi chưa commit, cấu hình thiếu và nguy cơ regression.
3. Triển khai trực tiếp trong phạm vi phase; không để code demo tạm bị bỏ quên.
4. Build khi môi trường cho phép, xem warnings, diff, contract; chạy test tự động
   khả thi và xác định hardware test còn thiếu. Không tự bịa log PASS.
5. Cập nhật progress: files changed, build/test, bằng chứng, blocker, quyết định,
   hardware test chưa làm, trạng thái và phase tiếp theo được phép theo dependency.
6. Báo cáo tiếng Việt theo mẫu bên dưới; dừng, không tự chuyển phase.

Mỗi test ghi môi trường/phiên bản, commit hoặc working tree liên quan, thao tác,
kết quả thật, log/artifact đã kiểm tra và phần chưa xác minh. Che secrets khi ghi
bằng chứng. Phân biệt compile/static check, mock test, hardware test và end-to-end.
Log có sẵn nhưng chưa đọc không phải bằng chứng mới. Khi người dùng gửi log,
phân tích, sửa trong phase nếu cần, kiểm thử lại phần ảnh hưởng và cập nhật tiến độ.

Trạng thái phase chỉ dùng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `NOT_STARTED` | Chưa bắt đầu phase theo lệnh người dùng |
| `IN_PROGRESS` | Đang triển khai/kiểm thử trong phase |
| `CODE_DONE_NEEDS_HARDWARE_TEST` | Code đã xong, còn test phần cứng/hệ thống thật |
| `PASS` | Đủ acceptance criteria với bằng chứng, kể cả ngoại lệ baseline ở 8.2.1 |
| `BLOCKED` | Có dependency/cấu hình/môi trường cản công việc, ghi rõ điều kiện gỡ |

Mẫu báo cáo cuối phase: `PHASE 8.2.n — [Tên phase]`, gồm 7 mục: (1) Đã thực
hiện; (2) Files changed và lý do; (3) Build/Test thật; (4) Hướng dẫn thủ công với
lệnh PowerShell chính xác, thao tác hardware và log PASS mong đợi; (5) Chưa xác
minh; (6) Phase status (`PASS`, `CODE_DONE_NEEDS_HARDWARE_TEST` hoặc `BLOCKED`
khi chốt kết quả); (7) Next phase và điều kiện thực hiện.
Nếu người dùng cần thay source thủ công, cung cấp toàn bộ từng file, không gửi
diff rời rạc hoặc ZIP.

## 7. Lệnh điều khiển

| Lệnh | Hành vi |
| --- | --- |
| `làm phase n` | Triển khai riêng 8.2.n sau kiểm tra dependency |
| `tiếp tục phase n` | Tiếp tục phần còn thiếu của 8.2.n |
| `kiểm tra phase n` | Audit, không tự triển khai thêm |
| `trạng thái phase 8.2` | Đọc progress, tóm tắt toàn bộ tiến độ |
| `test phase n` | Chạy/hướng dẫn test phù hợp |
| `sửa lỗi phase n` | Phân tích log, sửa trong phạm vi phase |
| `chuẩn bị commit` | Kiểm tra Git, đề xuất commit; không commit |
| `chuẩn bị merge` | Kiểm tra điều kiện merge vào main; không merge |

n từ 1 đến 8 luôn là 8.2.n trừ khi người dùng nói rõ phạm vi khác.
Bước khởi tạo chỉ xem sơ bộ repository và tạo tài liệu; không audit Phase 1,
không sửa firmware, build/flash hoặc commit/push/merge. Chờ `làm phase 1`.

## 8. Kết quả audit source cần giữ cho phase sau

Audit 2026-10-28: xem [PHASE8_2_1_REPOSITORY_AUDIT.md](PHASE8_2_1_REPOSITORY_AUDIT.md)
và progress để biết trạng thái/build cuối cùng. Source thật cấu hình button
active-high/pull-down; LTE chỉ diagnostic GPIO18, UART/AT disabled; không có fall
alert state machine hoặc caller polling button; buzzer_off trả void. Sensor
capture synthetic/CSV là đường riêng, không được biến thành MQTT TEST_ALERT tự
phát. Giữ source hiện tại, xác minh polarity trên hardware trước khi dùng button
ở phase sau; real ACK cần API actuator trả kết quả và contract đã thống nhất.
