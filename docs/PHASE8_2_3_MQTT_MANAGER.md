# Phase 8.2.3 — MQTT Manager

Ghi chú sau Phase 4: [Status & TEST_ALERT](PHASE8_2_4_STATUS_TEST_ALERT.md) đã bổ
sung publisher vào firmware. Các mô tả "chưa publish status/TEST_ALERT" dưới đây
ghi phạm vi/baseline riêng Phase 3; xem progress để biết trạng thái hiện tại.

2026-10-31 (Asia/Bangkok). Status: **CODE_DONE_NEEDS_HARDWARE_TEST**.
Wi-Fi Phase 8.2.2 đã PASS. Phase này chỉ thêm transport MQTT; chưa triển khai
normal status/TEST_ALERT, JSON command validation, STOP_BUZZER hoặc execution ACK.

## 1. Kiến trúc và contract

ESP-MQTT dùng trực tiếp component `mqtt` của ESP-IDF v5.5.5 đã cài trên máy,
không tải hay sửa SDK. `mqtt_manager_start()` được gọi sau Wi-Fi preparation,
trước acquisition để cấp tài nguyên boot. URI trống trả `ESP_ERR_NOT_FOUND`,
không tạo client/task/queue; file local hiện chưa cấu hình MQTT nên mặc định tắt.

Worker priority 3/core 0 chờ Wi-Fi có IPv4 rồi mới start client. ESP-MQTT dùng
MQTT 3.1.1, clean session, keepalive 30 s, timeout/reconnect 5 s. Client ID là
`real-{deviceId}`; device ID chỉ nhận 1–48 ký tự ASCII chữ/số/`_`/`-` để tránh
JSON/topic injection. Không chạy mock và board cùng device ID đồng thời.

Callback chỉ cập nhật trạng thái, ghép message trong buffer hữu hạn và enqueue
với timeout 0. Subscribe, publish và logging do worker thực hiện; không gọi
actuator hoặc gửi ACK. Callback không in URI, username/password hoặc payload.

Subscribe QoS 1: `iot/devices/{deviceId}/command`. Trạng thái `subscribed=true`
chỉ sau SUBACK có packet ID/connection epoch khớp và granted QoS 1. ACK đến trước
khi subscribe API trả về vẫn được lưu/match. Enqueue subscribe lỗi thử tối đa
3 lần trong một connection; SUBACK bị từ chối/mất sau 10 s giữ ready=false,
cần sửa broker/ACL hoặc reconnect. Snapshot phản ánh mất Wi-Fi ngay cả trước
khi TCP/MQTT phát hiện disconnect.

Publish API chọn channel, không cho caller tự đặt topic/QoS/retain:

| Channel | Topic suffix | QoS | Retain |
| --- | --- | --- | --- |
| STATUS | status | 1 | true |
| EVENT | event | 1 | false |
| LOCATION | location | 1 | false |
| HEALTH | health | 0 | false |

`mqtt_manager_publish()` chỉ copy vào queue, ESP_OK không phải broker delivery
hoặc actuator execution. Worker dùng `esp_mqtt_client_enqueue`, không gọi network
publish từ sensor/callback. QoS 1 có thể giao trùng khi reconnect; event ID/dedup
được xử lý ở các phase tiếp theo. Payload cũ còn trong application TX queue bị
drop khi connection epoch thay đổi. SDK outbox QoS 1 có thể retransmit sau reconnect.

Last Will trên status, QoS 1/retained, chỉ chứa envelope offline đã biết:

```json
{"schemaVersion":1,"deviceId":"waist-esp32s3-001","online":false,"mode":"REAL","lteReady":false}
```

Không đoán alertState hoặc thời điểm disconnect khi tạo LWT. Backend cần xử lý
envelope này như offline update; compatibility với strict full-status DTO chưa
được kiểm tra và phải thống nhất khi làm Phase 4/7. Không publish online status
ở Phase 3; retained offline LWT có thể vẫn còn sau reconnect cho đến Phase 4.
Không sửa `DEVICE_BACKEND_CONTRACT.md` hoặc Backend API trong lượt này.

## 2. Giới hạn và error handling

- RX/TX application queue: mỗi queue 4 entry; payload tối đa 1.024 byte.
- ESP-MQTT RX buffer 512, output buffer 1.400 byte; outbox limit cấu hình 8.192
  byte. SDK kiểm tra limit khi enqueue; không phải queue offline vô hạn.
- Ghép fragment kiểm tra topic/length/offset/total/message ID, kể cả fragment
  đầu chưa có payload; chỉ xuất complete frame và thêm NUL sau length thực.
- Sai topic, retained command, QoS khác 1, quá cỡ hoặc fragment bất thường bị
  drop. `rx_dropped` đếm rejected fragment/queue operation, không phải số command
  duy nhất. Mất kết nối xóa assembly đang dở.
- Command queue chứa raw bytes/length, DUP flag, message ID và connection epoch.
  Consumer tương lai phải kiểm tra JSON/device/event/expiry/replay/authorization
  và epoch trước thực thi. Transport acceptance không phải command success.
- Phase 3 chưa có consumer; sau 4 complete frame chưa đọc, frame tiếp theo drop.
  Log chỉ báo counters; không thực thi STOP_BUZZER hoặc ACK_SIMULATED.
- Init/queue/task lỗi được cleanup; client task start lỗi unregister callback
  trước khi xóa worker, giữ queues hữu hạn đến reboot để tránh concurrent teardown.
- Broker auth/transport errors và publish enqueue/full-outbox failure có counters.
  SUBACK/PUBACK của MQTT không phải ACK thực thi firmware.

`mqtt://` chỉ dành cho mạng demo được kiểm soát. `mqtts://` yêu cầu CA PEM có
lifetime suốt boot, không bỏ hostname verification. TLS handshake/CA/clock thực
chưa được test; production cần TLS và authorization/ACL đã được xác minh.

## 3. Broker demo đã chuẩn bị

`tools/start_phase3_broker.ps1` dùng image chính thức `eclipse-mosquitto:2`, lưu
digest đã pull vào `build/phase8_2_3/broker/image_digest.txt`. Bản đã chạy báo
Mosquitto 2.1.2; digest:
`sha256:860aeb5d63ce509508f6dcfb2bc8a1c1dd2bc60555b562b45ce90e52d8dabb0f`.
Nguồn phát hành Mosquitto: <https://mosquitto.org/download/>.

Broker chạy trong container `fall-phase3-broker`; ban đầu chỉ bind localhost,
đã chuyển sang IP Wi-Fi LAN laptop để test ESP32 ngày 2026-10-31 (mục 7).
Có password ngẫu nhiên riêng cho `phase3-device` và
`phase3-backend`; anonymous bị tắt. ACL device chỉ subscribe command và publish
event/status/location/health của chính device; backend đọc các topic device và
publish command. Không có persistence; không dùng broker demo làm production.

Files private trong ignored build:

- `broker/client_secrets.json`: mật khẩu client, không paste/chat/commit.
- `broker/config/passwords`: salted password file; owner container UID 1883.
- `broker/config/mosquitto.conf`, `broker/config/acl`: runtime config.

Chỉ mount `config/` vào broker, không mount JSON plaintext credentials. Script
không thay container cùng tên đã có; giữ container startup lỗi để chẩn đoán.

Đã xác minh bằng native Mosquitto clients trong container:

- Backend publish QoS 1/retain=false → device subscriber nhận nguyên JSON command.
- Anonymous CONNECT bị từ chối, client exit 5.
- Device publish topic device khác bị từ chối: broker log `Denied PUBLISH`,
  MQTT 5 PUBACK reason 135. CLI vẫn có thể exit 0 nên không dùng exitcode đơn lẻ.

Đây chỉ là broker/client fixture trên laptop, **không phải ESP32 PASS**. Test
STOP_BUZZER trong fixture không có actuator/thiết bị kết nối, không gửi ACK.
Log không chứa password: `build/phase8_2_3/broker_validation.log`.

## 4. Chuẩn bị LAN và local firmware config khi có board

Trong PowerShell của người dùng, Docker Desktop đã chạy:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object InterfaceAlias,IPAddress
$brokerLanIp = Read-Host 'Nhap IPv4 cua laptop tren mang Wi-Fi dang cap cho ESP32'
```

Để đổi binding của đúng container demo localhost đã tạo, lưu log rồi tạo lại
container; cấu hình/credentials trên host được giữ nguyên:

```powershell
docker logs fall-phase3-broker *> build\phase8_2_3\broker_before_lan.log
docker stop fall-phase3-broker
docker rm fall-phase3-broker
.\tools\start_phase3_broker.ps1 -ListenAddress $brokerLanIp
.\tools\configure_phase3_device.ps1 -BrokerAddress $brokerLanIp
```

Helper chỉ thêm/cập nhật block MQTT trong ignored `main/network_config.local.h`,
giữ nội dung Wi-Fi và không in credentials. Nếu đã có macro MQTT ngoài block,
helper dừng để tránh ghi đè. Dùng IP LAN cụ thể, không `localhost`, 127.0.0.1
hoặc 0.0.0.0 cho ESP32. Với broker Member 3, cấu hình URI/credentials của broker
đó riêng ở file local, không dùng helper credentials demo.

## 5. Build/flash và cách lặp lại hardware acceptance

Terminal đã kích hoạt ESP-IDF v5.5.5:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
idf.py --no-ccache -D CCACHE_ENABLE=0 build
if ($LASTEXITCODE -ne 0) { throw 'Build failed; do not flash' }
idf.py --no-ccache -D CCACHE_ENABLE=0 -p COM5 flash monitor
```

Monitor logging Ctrl+T rồi Ctrl+L, reset EN sau khi bật logging; thoát Ctrl+].
Theo dõi từ startup đến CSV và ít nhất một broker restart:

1. `WIFI_MANAGER: GOT_IP`, sau đó `MQTT_MANAGER: connected: client=real-...`.
2. `SUBACK confirmed: topic=iot/devices/.../command qos=1` và broker log xác nhận
   client ID tương ứng. Chỉ tạo task chưa có CONNACK/SUBACK không được tính PASS.
3. Gửi command MQTT-v1 bằng tài khoản backend; frame được enqueue, không có
   actuator action/ACK ở phase này. Payload >512 byte kiểm tra fragmentation;
   >1.024 byte/retained/wrong-topic phải bị drop.
4. `docker restart fall-phase3-broker`; ESP32 phải tự CONNACK/SUBACK lại, không
   reset. Kiểm tra mất AP/reconnect nếu điều kiện cho phép.
5. Sensor 100 Hz/25 Hz, missed_ticks/errors/outliers không tăng; CSV extractor
   PASS 4.000 dòng/CRC. GNSS/LTE/actuator regression theo baseline.

Lệnh gửi command đúng MQTT-v1 bằng tài khoản backend demo (chỉ dùng ở Phase 3,
thiết bị hiện chỉ enqueue bytes; event ID dưới đây là test ngẫu nhiên):

```powershell
$secrets = Get-Content -Raw build\phase8_2_3\broker\client_secrets.json | ConvertFrom-Json
$commandTopic = 'iot/devices/' + $secrets.deviceId + '/command'
$command = @{
    commandId = [guid]::NewGuid().ToString()
    eventId = [guid]::NewGuid().ToString()
    command = 'STOP_BUZZER'
    issuedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
} | ConvertTo-Json -Compress
$command | docker exec -i fall-phase3-broker mosquitto_pub -h 127.0.0.1 `
    -u $secrets.backendUsername -P $secrets.backendPassword -t $commandTopic -q 1 -s
```

Log ESP32 mong đợi `command frame queued: received=...; phase3 transport only`.
Không được diễn giải log enqueue này thành STOP_BUZZER hoặc execution ACK PASS.
Không chạy `mock_device.py` cùng device ID để lấy ACK thay thiết bị thật.

Đọc broker logs bằng `docker logs --tail 100 fall-phase3-broker`; không in
client_secrets.json. Dừng broker demo khi không dùng: `docker stop fall-phase3-broker`.

## 6. Kết quả code/build và giới hạn

Host runner: `python -B tools/test_mqtt_manager.py`. 22 scenario PASS, manager
line coverage khoảng 99,6%; tests dùng fake SDK/RTOS, không radio/COM/broker.
Đã RED/GREEN cho source chưa có, fragment 1.024 byte có first chunk rỗng và
callback/task cleanup khi client start lỗi. Fake coverage không thay hardware.

ESP-IDF build PASS; app còn khoảng 5% partition 1 MB và có size warning. Không
đổi partition/sdkconfig. Kết quả size/hash chính xác trong progress. Phase 4/5
phải theo dõi size khi thêm JSON/command handling.

Lượt triển khai code ban đầu chưa có board. Lượt test tiếp theo đã flash/monitor
COM5 và xác minh MQTT thật như mục 7. TLS chưa test. Normal status, TEST_ALERT
và real STOP_BUZZER/ACK thuộc các phase sau, chưa được triển khai.

## 7. Hardware verification — 2026-10-31

ESP32 COM5 và laptop cùng LAN, broker bind riêng IPv4 Wi-Fi laptop:1883, không
bind tất cả interfaces. Credentials chỉ ở ignored local header/build. Không đổi
firewall, GPIO, sampling, Wi-Fi Manager, GNSS/LTE hoặc contract trong lượt test.

Build/flash PASS, esptool verify hash. App 997.424 byte (`0xf3830`), còn 51.152
byte (`0xc7d0`, 5%) app partition. Runtime ELF prefix `b874d37ba` khớp ELF SHA-256
`B874D37BA2108B80175D30144D231474ECF5B1055F11F338F0FBFABCAF5A9F65`.
Artifact dưới `build/phase8_2_3/hardware/`:

- `mqtt_lan_01.log/.json`: 182,31 s; initial CONNACK/SUBACK và hai lượt broker
  stop/start hoặc recreate, device tự reconnect/SUBACK lại không reset. Session
  1/2/3 tại uptime 4.111/72.921/149.411 ms. Lỗi transport khi chủ động dừng broker
  là expected; sampling tiếp tục, 35 cửa sổ diagnostic, 0 missed tick/outlier/
  IMU/BMP error/diag dropped, gap 9.711–10.287 us. CSV 4.000 dòng CRC `7F046FC6`.
- `mqtt_retained_02.log/.json`: reset có kiểm soát để có RX queue rỗng. Retained
  command replay bị drop (`received=0 dropped=1`); QoS 0 bị drop; JSON 200/900/
  1.024 byte QoS 1 được enqueue; 1.100 byte bị drop; queue đủ 4 entry từ chối
  entry thứ 5. `publish_exact.py` gửi bytes chính xác qua subprocess stdin,
  `exact_payload_results.json` ghi size/QoS/exit; đối chiếu counters trong log
  thiết bị, không dùng publisher exit code thay bằng chứng nhận.
  Capture 125,08 s, 24 cửa sổ diagnostic, không lỗi sampling/reset bất thường;
  CSV 4.000 dòng CRC `ED126037`. Tổng hai capture 307,39 s/59 cửa sổ.
- `lwt_received.log`, `lwt_retained.log`: broker phát offline envelope của client
  thật khi reset; old TCP session bị thay thế lúc cùng device reconnect. Subscriber
  đang chờ nhận QoS 1; subscriber mới nhận retain=1/QoS 1. Không suy ra Backend
  đã xử lý LWT hoặc thiết bị đã publish status online.
- `broker_before_restart.log`, `broker_before_recreate.log`, `broker_final.log`:
  broker xác nhận client ID, CONNACK/SUBSCRIBE QoS 1/SUBACK, byte sizes, PUBACK
  và retained delivery. Không chạy mock cùng device ID.
- `build.log`, `flash.log`, `runtime_capture/`: kết quả build/flash và CSV.

Mosquitto 2.1 không cho `mosquitto_passwd -c` trên file đã tồn tại; utility update
còn yêu cầu owner root, server dùng owner UID 1883. Script đã sửa dùng update
khi file có sẵn, chuyển owner phù hợp ở từng bước và hạn chế quyền password/ACL
0600. Đã dựng lại broker thành công với credentials cũ, startup không còn cảnh
báo ACL ownership/permissions. Không sửa firmware để vượt bài test.

Giới hạn MQTT 3.1.1: publish retain=true đến subscriber đang online được broker
forward với retain=false. Manager chỉ từ chối retained replay có flag trong
delivery; không thể nhận biết retain intent của live publisher. Phase 5 phải có
validation/expiry/replay đúng contract; không coi retain filter là authorization.
Đã xóa retained command probe sau test. Offline status LWT còn retained sau
reconnect vì Phase 3 chưa publish online status; Phase 4 cần xử lý lifecycle này.

GNSS self-test PASS, live RMC/GGA vẫn parse với no-fix; LTE UART disabled/no AT,
giữ OFFLINE_UNVERIFIED. Driver buzzer self-test báo PASS, chưa xác nhận âm thanh
bằng tai. Không suy ra actuator regression đầy đủ, GNSS fix, TLS, soak test,
AP-loss khi MQTT chạy, Backend/App hoặc ACK thực thi từ các bài test này.

**Phase 8.2.3: PASS** cho broker demo Wi-Fi/MQTT đã kiểm chứng. Chỉ triển khai
Phase 8.2.4 khi người dùng yêu cầu.
