# App/Web Handoff — IoT Fall Detection

## 1. Giới thiệu

Dự án xây dựng thiết bị đeo vùng bụng/eo để phát hiện
ngã và gửi cảnh báo cho người thân.

Công nghệ chính:

- Hardware: ESP32-S3 N16R8.
- IMU: BMI270.
- Barometer: BMP388.
- GNSS: NEO-M8N.
- LTE: A7670C.
- Backend: Spring Boot.
- MQTT Broker: Mosquitto.
- Database: PostgreSQL.
- Application: Android.
- Admin: Web.

Repository này chứa firmware và tài nguyên tích hợp
dành cho thành viên Backend/Web/Android.

## 2. Các file cần sử dụng

| File                              | Mục đích                              |
| --------------------------------- | ------------------------------------- |
| `docs/DEVICE_BACKEND_CONTRACT.md` | MQTT topics và JSON schema            |
| `tools/mock_device.py`            | Giả lập thiết bị                      |
| `main/`                           | Source firmware ESP32                 |
| `main/lte_manager.c`              | Mã nguồn LTE hiện tại                 |
| `main/lte_manager.h`              | Interface LTE hiện tại                |
| `docs/SENSOR_MODEL_CONTRACT.md`   | Contract dữ liệu cảm biến dành cho AI |

Thành viên App/Web không cần chỉnh sửa firmware
để bắt đầu phát triển.

## 3. Kiến trúc hệ thống

Device / Mock
|
| MQTT
v
Mosquitto
|
v
Spring Boot
|
+---- PostgreSQL
|
+---- REST API / WebSocket / FCM
|
+---- Android
|
+---- Web Admin

Luồng gửi lệnh:

Android/Web
|
v
Spring Boot REST API
|
v
Mosquitto
|
v
Device / Mock

App/Web không giao tiếp trực tiếp với
MQTT broker của thiết bị.

## 4. MQTT Contract

Device ID thử nghiệm:

`waist-esp32s3-001`

Các topic chính:

- `iot/devices/{deviceId}/event`
- `iot/devices/{deviceId}/status`
- `iot/devices/{deviceId}/location`
- `iot/devices/{deviceId}/command`
- `iot/devices/{deviceId}/health`

Đọc `docs/DEVICE_BACKEND_CONTRACT.md`
để biết đầy đủ cấu trúc JSON và quy tắc xử lý.

Không tự thay đổi schema khi chưa thống nhất
với thành viên Firmware.

## 5. Chạy Mock Device

Yêu cầu:

- Python 3.
- Mosquitto MQTT Broker.
- Thư viện paho-mqtt phiên bản 2.x.

Cài đặt:

```powershell
python -m pip install "paho-mqtt>=2,<3"
```

Khởi động Mosquitto trước.

Chạy từ thư mục gốc repository:

```powershell
python tools/mock_device.py --broker 127.0.0.1 --port 1883 --device-id waist-esp32s3-001
```

Chú ý:

127.0.0.1 chỉ đúng khi broker và mock
chạy trên cùng một máy.

Nếu broker nằm trên máy khác,
sử dụng địa chỉ IP/hostname của broker.

### Mock thực hiện

1. Kết nối MQTT broker.
2. Publish trạng thái MOCK online.
3. Publish TEST_ALERT với isTest=true.
4. Duy trì heartbeat/status.
5. Subscribe command STOP_BUZZER.
6. Kiểm tra eventId của command.
7. Trả ACK_SIMULATED.
8. Cập nhật trạng thái IDLE.

Không sử dụng mock để thực hiện
các cuộc gọi hoặc gửi cảnh báo cứu hộ thật.

## 6. Công việc Backend

### MQTT Integration

- Kết nối Spring Boot với Mosquitto.
- Subscribe các MQTT topic.
- Parse và validate JSON.
- Phân biệt MOCK và REAL.
- Xử lý mất kết nối, reconnect và message trùng.

### Database

Thiết kế PostgreSQL cho:

- Users.
- Devices.
- Caregivers.
- FallEvents.
- AlertAcknowledgements.
- DeviceLocations.

Phải chống trùng sự kiện bằng
(deviceId, eventId).

### REST API

Xây dựng API để:

- Quản lý thiết bị.
- Quản lý người thân.
- Truy vấn cảnh báo.
- Xác nhận đã nhận cảnh báo.
- Yêu cầu STOP_BUZZER.
- Đánh dấu cảnh báo đã xử lý.

### Real-time

Sử dụng WebSocket/FCM để đẩy cảnh báo
từ Backend đến Android/Web.

## 7. Công việc Android

Các chức năng cần có:

- Đăng nhập.
- Liên kết thiết bị với người đeo.
- Quản lý danh sách người thân.
- Nhận cảnh báo.
- Hiển thị thông tin sự kiện.
- Hiển thị vị trí nếu có.
- Xác nhận đã nhận cảnh báo.
- Gửi yêu cầu dừng còi.
- Xem lịch sử cảnh báo.
- Kiểm tra quyền thông báo.
- Chế độ Test Alert.

Chú ý:

Không thể bảo đảm ứng dụng vượt qua
mọi cấu hình Silent/DND của điện thoại.

Cần có kiểm tra quyền và phương án
liên hệ người thân thay thế.

## 8. Công việc Web Admin

- Quản lý users.
- Quản lý devices.
- Quản lý caregivers.
- Theo dõi trạng thái thiết bị.
- Xem lịch sử cảnh báo.
- Xem trạng thái xử lý.
- Phân biệt MOCK và REAL.
- Giám sát hoạt động hệ thống.

## 9. Trạng thái phần cứng

Đã hoàn thành:

- BMI270 acquisition 100 Hz.
- BMP388 acquisition 25 Hz.
- Sensor Manager.
- Button.
- Vibration motor.
- Buzzer.
- GNSS NMEA parser.
- Last Known Location logic.

Chưa hoàn thành hoặc chưa xác minh:

- GNSS outdoor fix.
- LTE data connection.
- MQTT qua A7670C.
- AI inference phát hiện ngã thực tế.
- End-to-end real emergency workflow.

Không được trình bày mock online
thành trạng thái online của wearable thật.

## 10. Tiêu chí nghiệm thu

### Test 1: Receive Event

Mock gửi TEST_ALERT.

Backend nhận được event.

### Test 2: Database

Backend lưu sự kiện.

Gửi trùng eventId không được tạo thêm cảnh báo.

### Test 3: Notification

Android/Web nhận được cảnh báo thử nghiệm.

### Test 4: Acknowledge

Caregiver xác nhận đã nhận cảnh báo.

Backend lưu trạng thái ACK.

### Test 5: STOP_BUZZER

Android gửi yêu cầu qua Backend.

Backend publish MQTT command.

Mock nhận command và trả ACK_SIMULATED.

### Test 6: Safety

Sự kiện isTest=true không được
kích hoạt liên hệ cứu hộ thật.

## 11. Quy tắc phát triển

- Nhánh bàn giao chính thức: main.
- MQTT contract: mqtt-v1.
- Không commit secret/password.
- Không gửi command trực tiếp từ App.
- Không coi kết quả mock là kết quả thiết bị thật.
- Khi thay đổi contract cần thống nhất với Firmware.

## 12. Thứ tự thực hiện đề xuất

1. Chạy Mosquitto.
2. Chạy mock_device.py.
3. Tích hợp MQTT trong Spring Boot.
4. Lưu event vào PostgreSQL.
5. Tạo REST API/WebSocket.
6. Hiển thị cảnh báo trên Android/Web.
7. Tích hợp STOP_BUZZER.
8. Kiểm thử end-to-end bằng mock.
9. Chuyển sang thiết bị thật khi firmware sẵn sàng.
