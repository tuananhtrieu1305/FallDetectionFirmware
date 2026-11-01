# Phase 8.2.7 — End-to-End Integration

Ngày: 2026-10-31, Asia/Bangkok. **BLOCKED cho nghiệm thu E2E**: người dùng xác
nhận chưa có Backend/App và yêu cầu chuẩn bị test/tài liệu cho Member3. Firmware
Phase6 đã PASS profile demo; không sửa/build/flash firmware trong Phase7 này.
Không tạo Spring Boot/API/Android giả hoặc dùng native MQTT client làm Backend.

## 1. Môi trường đã xác minh

- Repo firmware, branch main/HEAD `dae70f6`, working tree có thay đổi các phase
  trước, được bảo toàn; không commit/push/merge.
- ESP32 COM5, boot ELF prefix `1840d338d`, đúng image cuối Phase6. BMI270100Hz,
  BMP38825Hz; GNSS parser hoạt động/no-fix; LTE OFFLINE_UNVERIFIED.
- Mosquitto container `fall-phase3-broker`, image `eclipse-mosquitto:2`, digest
  `sha256:860aeb5d63ce509508f6dcfb2bc8a1c1dd2bc60555b562b45ce90e52d8dabb0f`,
  Mosquitto2.1.2 theo phase trước. Bind duy nhất `192.168.0.3:1883`, không TLS,
  `allow_anonymous false`, password và ACL per-device. IP này là snapshot,
  kiểm tra lại khi laptop đổi mạng/DHCP; ESP32 không dùng localhost.
- Backend chạy cùng laptop có thể dùng `mqtt://192.168.0.3:1883`; container
  Backend phải kiểm tra route đến endpoint này. Không mặc định127.0.0.1 vì broker
  không bind loopback host. CLI chạy **bên trong** container Mosquitto dùng
  127.0.0.1 của container, không chứng minh Backend host/container đã truy cập.
- Native probe từ chối anonymous CONNACK135; device account publish command bị
  Denied PUBLISH/PUBACK135; backend account publish status cũng bị từ chối.
  `mosquitto_pub` exit0 trong hai trường hợp sau là **không đủ để đánh quyền**;
  log broker theo clientID mới là evidence. Không thay ACL/credentials.
- Không thấy Backend/Web/Android Fall Detection trong repo hoặc qua kiểm tra
  metadata dự án ở C:\Workspace; user xác nhận chưa có. Service8080 hiện là
  OnlineBidFlowSystem/auction_backend, không sử dụng hoặc chỉnh sửa service đó.

Private credentials hiện ở ignored
`build/phase8_2_3/broker/client_secrets.json`, firmware local header cũng ignored.
Member3 cấu hình backendUsername/backendPassword bằng cơ chế secret local của
Backend; không chép password vào docs/Git/chat hoặc nhúng broker credentials vào
Android/Web. Không tự gửi credentials/file cho thành viên khác bằng email/chat.
Demo cần LAN kiểm soát; production TLS/per-user authorization chưa được nghiệm thu.

## 2. Contract cần Member3 đồng bộ

Đọc [mqtt-v1](DEVICE_BACKEND_CONTRACT.md) và
[profile ACK/TTL demo đã được user duyệt](PHASE8_2_5_DEMO_COMMAND_CONTRACT.md).
Không cần chốt lại proposal firmware; việc Member3 adoption vẫn chưa được xác minh.

| Topic dưới `iot/devices/waist-esp32s3-001/` | Publisher / subscriber | QoS / retain |
| --- | --- | --- |
| `event` | ESP32 → Spring Boot | 1 / false |
| `status` | ESP32 → Spring Boot, gồm lastCommand ACK | 1 / true |
| `command` | Spring Boot → ESP32 | 1 / false |
| `location`, `health` | Đã có trong contract; chưa publish độc lập trong firmware này | 1,false / 0,false tương ứng |

App/Web qua Spring Boot. Không direct MQTT từ App/Web, không dùng MQTT broker
credentials của Backend trên client và không tự đặt REST/WebSocket endpoint chưa
có trong source. Lấy endpoint, auth, device ownership và push transport từ Member3.

Payload event dưới đây **đã nhận từ thiết bị thật** ở lượt Phase7, dùng để đọc
schema; không phát lại thành event mới hoặc dùng UUID này để arm còi tương lai:

```json
{
  "schemaVersion": 1,
  "eventId": "b7e84db8-da12-47e3-b912-00e396e99330",
  "deviceId": "waist-esp32s3-001",
  "eventType": "TEST_ALERT",
  "isTest": true,
  "occurredAt": "2026-10-31T12:00:25Z",
  "modelVersion": "firmware-test-v1",
  "confidence": null,
  "location": {"type":"UNAVAILABLE","lat":null,"lon":null,"observedAt":null}
}
```

Backend cho phép UTC null khi firmware chưa có giờ, confidence/location null;
không bù tọa độ mẫu, không gọi model test là AI inference. Ghi riêng thời điểm
server nhận. Status `mode=REAL`, `lteReady=false`, `alertState` phản ánh output
driver (IDLE/BUZZER_ON/null), không chứng minh trạng thái fall workflow hoàn chỉnh.

Command đúng bốn string key `commandId,eventId,command,issuedAt`; không thêm
deviceId/TTL/extra key vào JSON, identity ở exact topic/ACL. command=STOP_BUZZER,
eventId khớp local armed event mới; issuedAt UTC seconds `YYYY-MM-DDTHH:MM:SSZ`,
không milliseconds hoặc timezone offset. TTL30s, future skew5s, thiếu UTC bị
CLOCK_UNAVAILABLE. Lấy giờ UTC **lúc Backend gửi**; không dùng timestamp tĩnh
trong tài liệu. Payload tối đa512 byte; xem appendix về identifier/schema.

ACK `status.lastCommand` có commandId,eventId,command,result,reason,processedAt.
Chỉ `EXECUTED/STOPPED` sau driver verified off xác nhận thực thi. `REJECTED` và
`FAILED` không phải success; ACK_SIMULATED chỉ dành mock. PUBACK/HTTP success
không xác nhận còi đã dừng. UI có trạng thái pending đến ACK đúng cả commandId
và eventId; timeout giữ chưa xác minh, không tự đổi sang thành công.

Status retained có thể chứa lastCommand **cũ** khi subscribe/reconnect, kể cả
cached EXECUTED của event trước. So sánh correlation/processedAt/current context;
không dùng ACK cũ xác nhận request mới. Dedup RAM16 giữ qua MQTT reconnect, mất
khi reboot; resend cùng ID/phần nội dung trả original ACK, không actuator lại.
Cùng ID đổi nội dung bị COMMAND_ID_REUSED. QoS1 có thể giao trùng; Backend dedup
event theo `(deviceId,eventId)`, lưu command/ACK theo correlation riêng. STOP chỉ
dừng còi, giữ event, không tự cancel fall hay cứu hộ workflow.

## 3. Bộ test có sẵn và giới hạn công cụ

- Shared recorder `tools/phase6_capture.py` thêm `--observe-command` opt-in, chỉ
  thêm subscription command, không publish MQTT command. Giữ default Phase6.
  Serial local control whitelist và cleanup subscriber riêng giữ nguyên.
- `tools/phase7_check_capture.py` kiểm tra raw SHA của capture đã đóng, boot ELF/
  SUBACK, sampling, status REAL live, test event có serial trigger cùng UUID,
  schema/null/location/QoS. Khi có command và driver log cùng ACK live correlation
  đúng, báo chặng command-device-ACK đạt. Cần reset lúc bắt đầu để có boot evidence.
- Công cụ **luôn trả `end_to_end=NOT_VERIFIED`**, kể cả chặng broker PASS; quan
  sát command không chứng minh publisher là Spring Boot hoặc request từ App.
  Đây không phải audit auth/per-user, wire JSON escape/duplicate-key đầy đủ,
  database hay UI. JSON frames là dạng decoded; firmware parser mới là nơi
  kiểm tra bytes/schema command gốc. Driver readback không thay người nghe còi.
- Exit0 chỉ nghĩa chặng device→broker đạt (và thêm command leg nếu dùng
  `--require-command`), không phải Phase7 PASS. Exit1 khi thiếu evidence hoặc
  lỗi, exit2 khi device ID không hợp lệ. Không sửa raw/log để vượt test.
- Template [E2E evidence index](PHASE8_2_7_E2E_EVIDENCE_TEMPLATE.json) là hồ sơ
  thủ công. Copy vào ignored build cho từng run; mỗi evidence phải chỉ ra file,
  timestamp/correlation và revision thật. Điền JSON không tự biến E2E thành PASS.

## 4. Chạy trên laptop hiện tại

ESP32 giữ USB data COM5, AP_DEMO bật, đóng idf monitor/terminal đang chiếm COM5.
Các bước serial/STOP yêu cầu profile local `NETWORK_TEST_ALERT_SERIAL_ENABLED=1`
và `NETWORK_COMMANDS_ENABLED=1` như image demo đã test; tracked defaults vẫn0.
Backend/App chưa có thì không chạy buzzer/App/command suite bên dưới.
Terminal PowerShell ESP-IDF có Python/pyserial như các phase trước:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
docker ps --filter name=fall-phase3-broker --format '{{.Names}} {{.Status}} {{.Ports}}'
Test-NetConnection -ComputerName 192.168.0.3 -Port 1883
# Chỉ nếu container đã có nhưng đang stopped:
# docker start fall-phase3-broker
python -B tools\phase6_capture.py --port COM5 --out-dir build\phase8_2_7\member3_run01 --duration 600 --reset --observe-command
```

Không chạy start_phase3_broker.ps1 khi container đã tồn tại; script cố ý từ chối
replace container/credentials. Không mở toàn bộ interfaces/tắt firewall để
chữa route. Backend ở máy Member3 cần route/firewall rule giới hạn đúng IP/port,
theo môi trường thực tế; chưa có remote machine để xác minh ở lượt này.

Terminal thứ hai: chờ log GOT_IP/SUBACK, rồi gửi **plain test** không arm còi:

```powershell
$capture = 'build\phase8_2_7\member3_run01'
Get-Content "$capture\status.json"
if (Test-Path "$capture\control.json") { throw 'Một control action đang chờ' }
Set-Content -Encoding Ascii "$capture\control.json" '{"serial":"TEST_ALERT"}'
```

Mong đợi event TEST_ALERT/isTest=true với UUID mới và status modeREAL/lteReadyfalse.
Backend chưa có thì kết quả chỉ device→broker. Khi recorder hết600s hoặc chủ động
dừng (sau khi test đã xong), chạy kiểm tra capture đã đóng:

```powershell
New-Item -ItemType File "$capture\stop"
# Chờ terminal recorder kết thúc, trả prompt rồi mới chạy:
python -B tools\phase7_check_capture.py $capture
python -B tools\extract_sensor_csv.py "$capture\runtime.log" --out-dir "$capture\csv"
```

Nếu recorder đã hết giờ thì không cần tạo stop file. Out-dir mỗi run phải mới.
Không mở serial bằng công cụ khác hoặc gửi các control từ nhiều producer; không
chạy wifi_cycles song song trong E2E. Recorder sẽ reset một lần có kiểm soát;
tiếng selftest ngắn lúc boot không phải còi alert do Backend.

## 5. Checklist thực thi cùng Member3 khi Backend/App sẵn sàng

Trước lượt có Backend thật, Member3 cung cấp revision/source hoặc URL demo,
endpoint thực/auth local, đường dẫn log và xác nhận adoption ACK profile. Review
isTest guard/config để TEST_ALERT không thể gọi/SMS/115/cứu hộ thật; không chỉ
dựa vào thiết bị gửi isTest=true. Không chạy mock cùng deviceID này.

1. Chạy recorder mới với command observation. Spring Boot kết nối broker bằng
   backend account/clientID riêng (không dùng `real-waist-...`), subscribe event/
   status QoS1. Lưu CONNACK/SUBACK và log nhận statusREAL với deviceID đúng.
2. Gửi plain TEST_ALERT local. Lưu eventId ở raw/MQTT; Spring Boot log/schema
   validation phải có cùng ID và isTest=true, server receipt time riêng.
3. Nếu persistence đã có: truy vấn bằng chính eventId, lưu evidence row/query;
   kiểm tra dedup trên test dataset/transport-redelivery được kiểm soát, không
   tạo ngã thật giả. Nếu chưa có DB, ghi NOT_IMPLEMENTED với lý do, không fake
   PostgreSQL PASS; không suy ra DB dedup từ việc firmware gửi một lần.
4. Android **hoặc** Web hiển thị cùng deviceID/eventId và nhãn test, location
   unavailable đúng; lưu screenshot/log/revision. Chưa thử cả hai thì ghi rõ
   client nào được xác minh, client kia NOT_TESTED.
5. Với lượt điều khiển: chuẩn bị người nghe gần board và App đã ready. Sau boot
   >10s/UTC ready và cách lần TEST_ALERT trước ít nhất5s, gửi local
   TEST_ALERT_BUZZER một lần, **UUID mới**, bằng control:

   ```powershell
   if (Test-Path "$capture\control.json") { throw 'Pending control' }
   Set-Content -Encoding Ascii "$capture\control.json" '{"serial":"TEST_ALERT_BUZZER"}'
   ```

   Chờ raw TEST_BUZZER_ARMED và statusBUZZER_ON; còi tự off sau30s. Nếu hết30s
   trước khi thao tác, tạo local event mới sau khi còi off, không dùng auto-off
   làm bằng chứng remote STOP. Không có remote START_BUZZER trong contract.
6. App/Web dùng endpoint **thật của Member3** gửi yêu cầu STOP. Spring Boot
   xác thực user/device ownership, tạo commandId mới/issuedAtUTC hiện tại và
   publish bốn field đúng eventId mới, QoS1/retainfalse. Lưu App request trace →
   Backend audit trace → MQTT command, không log token/password. Không dùng
   `phase6_command_probe.py`/mosquitto_pub làm bước App/Backend.
7. ESP32 log STOP_BUZZER EXECUTED/output verified off trước ACK; người nghe xác
   nhận còi dừng trước deadline tự tắt. Broker có status.lastCommand EXECUTED/
   STOPPED đúng commandId/eventId; Spring Boot nhận/correlate rồi App/Web hiển
   thị kết quả thực thi. Giữ fall/event context. Nếu REJECTED/FAILED/timeout,
   ghi outcome thật và sửa đúng lớp, không chuyển UI success từ HTTP200.
8. Resend cùng command payload qua **Backend đã triển khai** để kiểm tra cached
   ACK, không actuator lần nữa. Test mismatch/expired/unauthorized qua test
   interface thực của Backend; không tự thêm production API hoặc bypass auth.
9. Dừng recorder, kiểm tra thêm command leg và điền evidence index:

   ```powershell
   python -B tools\phase7_check_capture.py $capture --require-command
   Copy-Item docs\PHASE8_2_7_E2E_EVIDENCE_TEMPLATE.json "$capture\e2e_evidence.json"
   ```

   Mẫu copy một lần trước khi điền, không copy đè hồ sơ đã ghi. Checker command
   leg PASS vẫn cần review Backend/App/DB/UI thật và test-safety evidence độc lập.
   Lưu chỉ dẫn evidence bằng path/correlation, không nhét secrets vào template.

## 6. Kết quả thực hiện lượt này

| Điểm kiểm thử | Kết quả / evidence dưới `build/phase8_2_7/` |
| --- | --- |
| Broker endpoint/auth/ACL | PASS trong demo local: config inspected, anonymous/role-denial log reason135; `acl_probes.json`, `acl_broker_evidence.log` (giữ CLI-inconclusive attempt riêng) |
| ESP32 → broker status | PASS mới: serial boot ELF1840d338d, GOT_IP/CONNACK/SUBACK, status REAL live, không dùng retained status cũ thay evidence |
| ESP32 → broker TEST_ALERT | PASS mới: một local plain event b7e84db8-da12-47e3-b912-00e396e99330, isTesttrue/modeltest/confidencenull/locationUNAVAILABLE; `device_broker/` |
| Sampling/CSV | 130,28s/25 sensor windows,0 missed/outlier/IMU/BMP error/diag drop/reset bất thường, gaps9.948–10.051us; CSV4.000/CRC32 `6F3A56A0` |
| Command observer | Đã subscribe command, không ghi nhận command hợp lệ trong run này; hai publish ACL probe `{}` bị broker chặn; không phát STOP thay Member3 |
| App → Backend → device → ACK | **NOT_TESTED**, chưa có App/Backend; STOP thật các phase5/6 chỉ là evidence lớp device/broker trước đó |
| Spring Boot subscriber/schema | **NOT_TESTED**, chưa có service/source Fall Detection |
| PostgreSQL/persistence/dedup | **NOT_TESTED**, không coi database của ứng dụng khác là Fall Detection |
| Android/Web notification/ACK UI | **NOT_TESTED**, chưa có client; không mock kết quả |
| Test safety phía Backend | **NOT_VERIFIED**, chưa có code/config/egress evidence của Backend; bản ESP32 chỉ phát isTesttrue và không gọi/SMS |
| New checker host | 10 tests PASS, stdlib trace line coverage97,20% (104/107 executable lines), fake fixture không phải E2E evidence; `host_results.json` |
| Firmware build/flash | Không thực hiện vì firmware/sdkconfig không đổi; image trên board vẫn ELF1840d338d; kiểm tra preservation hash |

Raw SHA-256:
`f2a45dc587449654acea5e191e9fff842af379c45629f3daa812210e3042d385`.
Checker `device_to_broker=PASS`, `command_device_ack=NOT_OBSERVED`, mọi chặng
Backend/App và `end_to_end=NOT_VERIFIED`. Test self-fixture không phải evidence
thiết bị; evidence mới là serial/MQTT capture trên COM5 và broker log độc lập.

**Phase status: BLOCKED** bởi thiếu Backend/App theo xác nhận người dùng; công
việc chuẩn bị và test độc lập khả thi đã hoàn tất. Khi Member3 sẵn sàng, tiếp tục
Phase7; chưa tự chuyển Phase8 hoặc tạo tài liệu bàn giao cuối Phase8 thay phase đó.

## 7. Files changed và cách chạy host tests

| File | Thay đổi trong Phase7 |
| --- | --- |
| `tools/phase6_capture.py` | Thêm flag opt-in observe-command; giữ default/serial whitelist/cleanup |
| `tools/phase7_check_capture.py` | Mới: offline checker chặng broker và correlation, không tự chứng nhận E2E |
| `tests/test_phase7_capture.py` | Mới: guards chống MOCK/retained/mismatch/simulated ACK, thiếu command/raw hash/sampling, CLI và invalid schema |
| Tài liệu này | Mới: môi trường thật, checklist Member3, từng điểm PASS/NOT_TESTED, lệnh kiểm thử |
| `docs/PHASE8_2_7_E2E_EVIDENCE_TEMPLATE.json` | Mới: index evidence từng run, chưa điền kết quả |
| `docs/APP_WEB_HANDOFF.md` | Thêm link profile thiết bị thật, phân biệt hướng dẫn mock Phase8.1 cũ |
| `docs/PHASE8_2_PROGRESS.md` | Cập nhật phase7/dependency/evidence và trạng thái chưa nghiệm thu |

```powershell
python -B -m unittest discover -s tests -p test_phase7_capture.py
```

Mong đợi10 tests/OK; output fixture là host test, không hardware/E2E. Coverage
97,20% được đo bằng stdlib trace + executable line table ở lượt phát triển này,
không cài thêm package và không chạy SDK/Backend giả trong test. Initial checker
chưa nhận double-space của app_init ELF hash được sửa theo log thật và có RED/
GREEN regression fixture; raw capture không thay đổi. JSON report có thể chạy
lại, chỉ ghi report của chính checker, không sửa input runtime/status/MQTT.
