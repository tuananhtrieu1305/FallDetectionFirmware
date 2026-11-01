# Phase 8.2.5 — Demo STOP_BUZZER / real execution ACK

Ngày: 2026-10-31, Asia/Bangkok. Người dùng đã chọn **"Dùng đề xuất cho demo
firmware; ghi rõ Backend cần đồng bộ"** cho ACK/TTL profile này. Đây là phụ lục
demo, không phải xác nhận Member 3 đã triển khai/chấp thuận API production.
Contract mqtt-v1 gốc và mock ACK_SIMULATED được giữ riêng; không dùng mock ACK
làm kết quả thực thi ESP32. Backend phải đồng bộ phụ lục trước integration.

## 1. Transport, identity và schema command

- Topic duy nhất: `iot/devices/{deviceId}/command`, QoS 1, không retained.
- Device ID được ràng buộc bởi topic exact-match và broker per-device ACL,
  không thêm deviceId bắt buộc vào JSON gốc.
- Chỉ profile demo opt-in `NETWORK_COMMANDS_ENABLED=1` mới xử lý command.
  Default source/template là 0. TLS/production authorization chưa được xác minh.
- Command phải là object JSON phẳng, đúng bốn key không lặp, không extra key:
  `commandId`, `eventId`, `command`, `issuedAt`. Tất cả là string; không escape,
  không NUL/binary/nested value; tối đa 512 byte (transport cap vẫn 1.024).
- commandId: 1..64 ASCII letters/digits/underscore/hyphen. eventId: UUID lowercase
  36 ký tự, phải khớp event đang được arm local. command: identifier ASCII tối đa
  32 ký tự; chỉ STOP_BUZZER được hỗ trợ.
- issuedAt: UTC RFC3339 seconds chính xác `YYYY-MM-DDTHH:MM:SSZ`, năm 2020..2099,
  calendar hợp lệ; profile không nhận fractional seconds/timezone offsets.
- Invalid/unparseable schema không có correlation tin cậy: drop + bounded log,
  không actuator và không tự dựng ACK success từ JSON lỗi.

```json
{"commandId":"b4faf61c-4ae4-4655-b3dc-496bb8b17e36","eventId":"123e4567-e89b-42d3-a456-426614174000","command":"STOP_BUZZER","issuedAt":"2026-10-31T11:00:00Z"}
```

Đây là ví dụ, không phải lệnh có hiệu lực hoặc event thật đang active.

## 2. TTL, UTC và replay

TTL: reject nếu `nowUTC-issuedAt > 30.000 ms`; reject future nếu
`issuedAt-nowUTC > 5.000 ms`. Chưa có UTC hợp lệ: REJECTED/CLOCK_UNAVAILABLE.
Không dùng build time, uptime hoặc hard-coded test time làm UTC thực.

Nguồn giờ: SNTP response thật, giữ anchor UTC + monotonic tối đa một giờ; hoặc
current GNSS fix thật còn tươi tối đa 5 s. SNTP demo không authenticated, cần
LAN được kiểm soát; không hứa chống giả mạo giờ trên mạng thù địch. Mặc định
NTP server `pool.ntp.org`, có thể đổi ở local header. SNTP init/alloc trước
acquisition, start bất đồng bộ khi có network; không chờ sync trong sensor path.

Dedup RAM 16 command gần nhất, giữ qua MQTT reconnect, mất khi reboot; cùng ID
và cùng bốn field trả lại **kết quả/processedAt đã lưu**, không gọi actuator
lại. Cùng ID nhưng đổi nội dung: REJECTED/COMMAND_ID_REUSED, không ghi đè cache
gốc. Khi cache đầy, thay entry cũ nhất; không hứa dedup vĩnh viễn hoặc qua reboot.
Mỗi local event có UUID mới, active event không persist/reuse qua reboot; command
tham chiếu old event bị từ chối. Sau CLOCK_UNAVAILABLE/rejection, Backend phải
tạo commandId mới nếu người dùng yêu cầu thử lại.

Cached success chỉ xác nhận lần xử lý trước của commandId/eventId đó; nếu một
event mới đang bật còi, replay ACK của event cũ không chứng minh còi mới đã dừng.
Backend luôn đối chiếu eventId/commandId/processedAt và trạng thái hiện tại.
MQTT DUP flag không được dùng thay cho application dedup.

MQTT 3.1.1 forward live publish retain=true với retain=false tới subscriber đang
online. Transport chỉ nhận biết/chặn retained replay có flag trong delivery;
không thể suy ra retain intent của publisher từ live frame. Backend phải publish
command retain=false; TTL/context/dedup vẫn bắt buộc, không dùng retain filter
làm authorization hoặc bảo đảm replay đầy đủ.

## 3. ACK trong status

Topic status/QoS 1/retained giữ nguyên mqtt-v1. Thêm object `lastCommand` vào
full status REAL, gồm đúng các field sau:

```json
{
  "commandId":"b4faf61c-4ae4-4655-b3dc-496bb8b17e36",
  "eventId":"123e4567-e89b-42d3-a456-426614174000",
  "command":"STOP_BUZZER",
  "result":"EXECUTED",
  "reason":"STOPPED",
  "processedAt":"2026-10-31T11:00:01Z"
}
```

| result | reason | Ý nghĩa |
| --- | --- | --- |
| EXECUTED | STOPPED | Checked LEDC operation hoàn tất và readback duty 0 trước khi tạo ACK |
| REJECTED | CLOCK_UNAVAILABLE | Không có nguồn UTC đủ điều kiện; processedAt=null |
| REJECTED | EXPIRED / FUTURE_ISSUED_AT | TTL/skew không hợp lệ |
| REJECTED | EVENT_NOT_ACTIVE | Event không đúng context active của demo |
| REJECTED | NOT_BUZZING | Event vẫn được giữ nhưng còi đã off; không phải thực thi mới |
| REJECTED | STALE_CONNECTION | Frame thuộc MQTT epoch cũ/offline |
| REJECTED | UNSUPPORTED_COMMAND | Không hỗ trợ command |
| REJECTED | COMMAND_ID_REUSED | ID đã có nội dung khác trong dedup cache |
| FAILED | ACTUATOR_UNAVAILABLE / STOP_FAILED | Không xác minh được output/driver operation; không ACK success |

processedAt lấy UTC tại lúc xử lý (độ phân giải seconds), null nếu không biết.
SDK MQTT PUBACK chỉ là transport acknowledgement, không phải command execution.
Không dùng ACK_SIMULATED, không ACK success trước khi driver/readback hoàn tất.
Một ACK đang chờ được giữ trước khi nhận command tiếp theo; queue broker/frame
và cache đều hữu hạn. Heartbeat/reconnect status giữ lastCommand mới nhất.

Publish ESP_OK chỉ nghĩa đã vào application queue. Có thể mất ACK khi reset/
enqueue SDK failure; status heartbeat nhắc lại lastCommand mới nhất, không có
durable history từng ACK. Backend giữ command pending đến ACK đúng correlation,
có thể resend cùng payload/ID để lấy cached result. QoS 1 có thể giao trùng.

## 4. Controlled physical demo

Plain `TEST_ALERT` giữ hành vi Phase 4: chỉ gửi event test, không bật còi.
Khi cả serial test và command profile được bật local, `TEST_ALERT_BUZZER` tạo
TEST_ALERT mới, queue event rồi arm còi bằng checked API; phải qua boot 10 s,
còi đang off và event UUID chưa dùng lại. Arm failure được log, không báo còi on
giả. Event vẫn `isTest=true`; không gửi FALL_CONFIRMED hoặc gọi/SMS/cứu hộ.

Còi tự off sau 30 s monotonic kể cả mất mạng/chưa có UTC; lỗi driver thì cleanup
best-effort mỗi giây và log lỗi, không giả thành công. STOP hợp lệ chỉ dừng còi,
giữ active event/context; không hủy ngã hoặc quy trình alert tương lai. Các API
void/boot diagnostic/GPIO inversion/tần số 2,5 kHz và button behavior giữ nguyên.
Command xử lý trong worker priority thấp, không từ MQTT callback/ISR.

ACK success chỉ xác minh trạng thái driver điện; xác nhận module phát âm rồi
im cần người dùng nghe hoặc thiết bị đo. Không thay thế bằng kết quả mock.

## 5. Authorization của broker demo

Broker riêng có password ngẫu nhiên và ACL per-device. Device chỉ đọc command
của mình và publish topic của mình; tài khoản backend demo mới được publish
command. Android/Web production phải qua Spring Boot authorization. Bất kỳ ai
có backend demo credentials đều có thể gửi command trong quyền ACL; firmware
không có chữ ký command, per-user authorization, TLS/secure time hoặc immutable
replay journal. Không dùng cấu hình demo như security architecture production.
