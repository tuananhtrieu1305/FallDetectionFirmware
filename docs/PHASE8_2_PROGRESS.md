# Phase 8.2 — Progress

Cập nhật: 2026-11-01 (Asia/Bangkok).
Tên SSID thật trong tài liệu chuẩn bị Git đã ẩn thành `AP_DEMO`; log/tài liệu
gốc vẫn được giữ local. Đây là nhãn ẩn danh, không phải tên mạng để cấu hình.
Kế hoạch chuẩn: [PHASE8_2_MASTER_PLAN.md](PHASE8_2_MASTER_PLAN.md).
Contract: [DEVICE_BACKEND_CONTRACT.md](DEVICE_BACKEND_CONTRACT.md).

## 1. Trạng thái các phase

| Phase | Tên | Trạng thái | Ngày / ghi chú |
| --- | --- | --- | --- |
| 8.2.1 | Repository Audit & Baseline | `PASS` | 2026-10-28: build và runtime sensor/CSV đã xác minh; GNSS self-test PASS, NMEA thật chưa PASS; chưa test actuator đầy đủ |
| 8.2.2 | Wi-Fi Manager | `PASS` | 2026-10-30: startup/DHCP và 2 lượt mất AP/reconnect thật PASS; 567,59 s, 0 missed tick/outlier/error/reset (mục 22) |
| 8.2.3 | MQTT Manager | `PASS` | 2026-10-31: COM5 flash, CONNACK/SUBACK, 2 lượt broker recovery, RX limits/LWT và sampling/CSV thật PASS (mục 24) |
| 8.2.4 | Status & TEST_ALERT Publishing | `PASS` | 2026-10-31: status/TEST_ALERT thật qua COM5, QoS/retain/reconnect và sensor/CSV PASS (mục 25) |
| 8.2.5 | STOP_BUZZER & Real ACK | `PASS` | 2026-10-31: hai STOP thật/ACK sau readback off, negative/dedup/reconnect và sensor/CSV PASS; người dùng xác nhận âm thanh; Backend cần đồng bộ profile demo (mục 26) |
| 8.2.6 | Reliability & Regression | `PASS` | 2026-10-31: profile demo mới 1.000,19 s/8 Wi-Fi recovery/10 SUBACK, 0 reset bất thường/missed/outlier/error; kiểm tra tổng hợp 27/27 PASS; chưa retest AP power outage (mục 27) |
| 8.2.7 | End-to-End Integration | `BLOCKED` | 2026-10-31: user xác nhận chưa có Backend/App; bộ test/tài liệu Member3 hoàn tất, chặng ESP32→broker mới PASS, E2E chưa xác minh (mục 28) |
| 8.2.8 | Documentation, Handoff & Git | `NOT_STARTED` | 2026-10-28: khởi tạo plan không phải bàn giao cuối phase |

`NOT_STARTED` thể hiện chưa khởi động phase tương ứng theo master plan này;
không phải kết luận source không có bất kỳ chức năng liên quan nào.
Các trạng thái hợp lệ: `NOT_STARTED`, `IN_PROGRESS`,
`CODE_DONE_NEEDS_HARDWARE_TEST`, `PASS`, `BLOCKED`.

## 2. Bằng chứng ban đầu — bước khởi tạo (lịch sử)

Đã xem sơ bộ cấu trúc thư mục, trạng thái Git, README và hai tài liệu hiện có.
Không thực hiện audit Phase 8.2.1, không đọc/audit source firmware hoặc nội dung
mock, không chạy build/test/flash và không giao tiếp COM5.

- Branch quan sát: `main`; HEAD: `dae70f6` — `docs: remove obsolete sensor model contract`.
- Thư mục quan sát: `main/`, `components/`, `docs/`, `tools/`, `build/`,
  `.vscode/`, `captures/`, `.git/`.
- Tài liệu có sẵn: `README.md`, `docs/DEVICE_BACKEND_CONTRACT.md`,
  `docs/APP_WEB_HANDOFF.md`; có `tools/mock_device.py`.
- Chưa có AGENTS.md ở root hoặc các vị trí tổ tiên đã kiểm tra; chưa có hai
  tài liệu Master Plan/Progress trước bước khởi tạo.
- Có thư mục build và log cũ không chứng minh baseline build/test của HEAD hiện tại.
- Contract hiện có là `mqtt-v1`, phân biệt `MOCK`/`REAL`, yêu cầu TEST_ALERT với
  `isTest=true` và cấm emergency escalation thật cho test.

Working tree trước khi tạo tài liệu có các mục untracked sau; giữ nguyên và
chưa dùng làm bằng chứng kiểm thử:

- `captures/`
- `log.fall_detection_firmware.20261024085940.txt`
- `log.fall_detection_firmware.20261024123237.txt`
- `log.fall_detection_firmware.20261024124726.txt`
- `log.fall_detection_firmware.20261024133442.txt`
- `sensor_csv_verified_4000.txt`

Baseline người dùng báo cáo (chưa xác minh lại): bring-up, BMI270 100 Hz,
BMP388 25 Hz, Sensor Manager, CSV/ring buffer, button/vibration/buzzer và
GNSS UART/NMEA/self-test đã PASS. LTE Phase 7 PARTIAL PASS; giữ
`OFFLINE_UNVERIFIED`. GNSS outdoor fix, LTE data/MQTT và AI hoàn chỉnh chưa PASS.

## 3. Nhật ký thay đổi — khởi tạo quản lý phase

Ngày 2026-10-28, theo yêu cầu chỉ thiết lập kế hoạch:

| File | Thay đổi / lý do |
| --- | --- |
| `docs/PHASE8_2_MASTER_PLAN.md` | Tạo kế hoạch 8 phase cố định, dependency, acceptance criteria, safety và workflow |
| `docs/PHASE8_2_PROGRESS.md` | Tạo tiến độ, bằng chứng ban đầu và danh sách kiểm thử còn thiếu |
| `AGENTS.md` | Tạo chỉ dẫn ngắn, duy nhất đến plan/progress/contract cho phiên mới |

Không sửa firmware, contract, mock, README, handoff cũ, SDK config hoặc log/capture.
Không commit, push hoặc merge.

## 4. Build/Test results — bước khởi tạo (lịch sử)

| Kiểm tra | Kết quả / giới hạn |
| --- | --- |
| Xem cấu trúc và Git | Đã chạy read-only; có untracked như liệt kê, không có tracked modification lúc đầu |
| Đọc hướng dẫn/tài liệu | Đã đọc tài liệu nêu trên để lập plan; chưa audit source |
| Kiểm tra tài liệu mới | Đạt: Python kiểm tra UTF-8, whitespace, liên kết Markdown, đủ 8 phase đúng thứ tự, cả 8 NOT_STARTED và chỉ dẫn AGENTS không trùng |
| Kiểm tra Git cuối bước | `git diff --check` không báo lỗi tracked; `git diff --stat` rỗng; `git status --short` chỉ thêm 3 file tài liệu mới, giữ nguyên untracked ban đầu. Nội dung file mới được kiểm tra riêng bằng Python |
| Baseline build / compile warnings | NOT RUN — ngoài phạm vi khởi tạo |
| Test tự động / mock | NOT RUN — ngoài phạm vi khởi tạo |
| Hardware / flash / end-to-end | NOT RUN — ngoài phạm vi khởi tạo |

## 5. Vấn đề và dependency cần làm rõ

- Đã audit môi trường ESP-IDF/toolchain, source timing và điểm tích hợp ở Phase
  8.2.1; baseline build PASS. Sampling/jitter live vẫn cần hardware regression.
- Contract chỉ có ví dụ `ACK_SIMULATED`; chưa chốt schema/result ACK thực thi
  thật. Không được tự thay bằng một giá trị ACK suy đoán.
- Contract yêu cầu expiration, authorization, matching eventId, duplicate
  commandId/current alert state nhưng chưa chốt TTL/expiry, cách xử lý thiếu UTC
  và bảo đảm replay qua reboot. Đã đọc mock/source: mock không validate expiry
  hoặc dedup. Cần thống nhất Member 3 trước phần triển khai phụ thuộc; modelVersion
  test firmware và observedAt status khi thiếu UTC cũng cần định nghĩa rõ.
- Chưa biết SSID/password, broker LAN URI, credentials/ACL hoặc quyền truy cập
  Backend/App. Không ghi secrets vào tài liệu/Git. Địa chỉ localhost của mock
  không phải địa chỉ broker để ESP32 khác máy kết nối.
- `README.md` còn mô tả Phase 0; `APP_WEB_HANDOFF.md` tham chiếu tài liệu
  `docs/SENSOR_MODEL_CONTRACT.md` đã bị xóa. app_main/header còn log/comment cũ
  về BMP388/LTE/ring; audit đã ghi rõ, chưa sửa ngoài phạm vi.
- Source button GPIO4 ACTIVE-HIGH/pull-down, trái yêu cầu ban đầu active-low;
  giữ code đã có, cần xác minh wiring trước phase dùng button làm trigger.
- LTE Manager chỉ GPIO18 TX idle diagnostic, UART/AT disabled; app_main còn log
  AT task cũ. Không có readiness API; giữ OFFLINE_UNVERIFIED/lteReady=false.
- Không có fall alert state machine; button chưa được poll; buzzer_off trả void
  nên cần API checked/state trước real ACK. Sensor synthetic capture không phải
  MQTT TEST_ALERT, không tự đưa lên broker lúc boot.
- Phase 2 đã ignore riêng main/network_config.local.h và có template không secret;
  không dùng .env hoặc sdkconfig.local/secrets. sdkconfig vẫn tracked, không đặt
  credentials vào đó. Application logs không in SSID/password, driver storage RAM.
- Không còn blocker build/audit cho 8.2.1. Các thiếu hụt contract/config là
  dependency phase sau, không cản Wi-Fi Manager.
- Log Wi-Fi mới nhất (mục 14) cho thấy regression startup: missed_ticks=16 và
  gap tối đa 72.413 us trong cửa sổ đầu, khác baseline Phase 1 không mất tick.
  Chưa đủ điều kiện PASS Phase 2; cần xử lý/xác minh lại startup và test reconnect.
- Runtime mới (mục 12): GNSS self-test PASS nhưng RX total chỉ 133 byte không
  tăng và parsed RMC/GGA luôn 0. Luồng NMEA thật chưa được xác minh, ngoài việc
  chưa có outdoor fix. Không sửa parser hoặc coi location unavailable là fix.

## 6. Kiểm thử thực tế chưa thực hiện trong phiên này

- Build baseline ESP-IDF v5.5.5 đã PASS; không thay thế kiểm thử hardware bên dưới.
- Runtime sensor/PSRAM/CSV và GNSS self-test đã có bằng chứng mới ở mục 12;
  chưa xác minh GNSS NMEA liên tục, outdoor fix hoặc actuator action.
- Wi-Fi 2.4 GHz, DHCP, mất mạng/reconnect và sensor chạy đồng thời.
- MQTT client thật, subscribe, Last Will, reconnect, broker restart/offline boot.
- Status REAL và TEST_ALERT thực nhận tại broker, schema/QoS/retain/correlation.
- Dừng còi vật lý, ACK sau thực thi, invalid/expired/duplicate/replay command.
- Soak/reliability sau tích hợp network: heap, task, queue, publish failure,
  event duplication, sensor jitter và button/vibration/buzzer. Baseline sampling/
  jitter, GNSS self-test và LTE diagnostic safe mode đã kiểm tra trong khoảng
  282 giây theo mục 12; chưa phải PASS Phase 8.2.6.
- Hai chiều ESP32 ↔ broker ↔ Spring Boot ↔ Android/Web, persistence và ACK UI.
- GNSS fix ngoài trời/LTE/model AI chưa PASS theo thông tin người dùng; không
  tự mở rộng Phase 8.2 thành triển khai các hạng mục đó.

## 7. Quyết định kỹ thuật và quy tắc cập nhật

- Giữ nguyên 8 phase và scope; chỉ bắt đầu khi có lệnh tương ứng.
- Contract là nguồn chuẩn; điểm thiếu cần thỏa thuận, không tự đổi API Backend/AI.
- Không tự động coi compile, mock hoặc log chưa kiểm tra là PASS phần cứng thật.
- Giữ LTE `OFFLINE_UNVERIFIED`; không emergency call/SMS/cứu hộ thật.
- STOP_BUZZER chỉ dừng buzzer; không mặc nhiên hủy trạng thái ngã/quy trình cảnh báo.
- Không tự commit/push/merge; bảo toàn các thay đổi local có sẵn.
- Khi phase thay đổi: ghi ngày, files changed, lệnh build/test và kết quả thật,
  log/artifact, phần hardware chưa làm, blocker, quyết định và dependency kế tiếp.

## 8. Phase được phép triển khai tiếp theo

**Phase 8.2.2–8.2.5 đã PASS** theo bằng chứng phần cứng mục 22, 24, 25 và 26.
Broker demo bind riêng IP LAN laptop; STOP_BUZZER/real ACK chạy trên COM5.
Chi tiết: [PHASE8_2_5_STOP_BUZZER_REAL_ACK.md](PHASE8_2_5_STOP_BUZZER_REAL_ACK.md).
**Phase kế tiếp:** 8.2.6 — Reliability & Regression, chỉ khi có lệnh.
Profile ACK/TTL demo đã được người dùng chấp thuận; Member 3/Backend vẫn cần đồng
bộ trước Phase 7. App partition đã chuyển preset 1.500 KiB, còn 485.696 byte (32%).
Không tự chuyển phase/commit/push/merge.

## 9. Phase 8.2.1 — kết quả ngày 2026-10-28

Báo cáo chi tiết và lệnh PowerShell:
[PHASE8_2_1_REPOSITORY_AUDIT.md](PHASE8_2_1_REPOSITORY_AUDIT.md).

Đã đọc app_main, tất cả manager/header, ring/sample, root/main/component CMake,
SDK config, Git ignore, contract, mock và extractor. Đã xác định kiến trúc, các
khác biệt với ngữ cảnh ban đầu và bảng file tích hợp cho phase sau.

Files changed của Phase 1:

| File | Lý do |
| --- | --- |
| `docs/PHASE8_2_1_REPOSITORY_AUDIT.md` | Tạo báo cáo kiến trúc/source, baseline evidence, rủi ro, file tích hợp và test instructions |
| `docs/PHASE8_2_MASTER_PLAN.md` | Ghi nhận button polarity/source audit và chỉ dẫn các khác biệt quan trọng |
| `docs/PHASE8_2_PROGRESS.md` | Ghi kết quả thực tế, dependency, trạng thái PASS audit và next phase |

AGENTS.md giữ nguyên nội dung từ bước khởi tạo. Không sửa firmware/contract/mock/
sdkconfig/.gitignore. Artifact build/test chỉ dưới ignored build/.

| Kiểm tra | Kết quả thật |
| --- | --- |
| Git baseline | main, HEAD dae70f6; không tracked modification trước/sau audit |
| ESP-IDF/toolchain | v5.5.5, Xtensa GCC 14.2.0, CMake 3.30.2, Ninja 1.12.1 |
| Fresh baseline build | PASS exit 0, 1.087 bước build chính; log build/phase8_2_1_audit/baseline_build.log |
| Environment warning recovery | Lần đầu thiếu ESP_ROM_ELF_DIR/Git SDK ownership; đã sửa chỉ trong process, không Git global/SDK changes |
| Reconfigure/build sau sửa environment | PASS exit 0, không warning/error/fatal/traceback theo kiểm tra log build/phase8_2_1_audit/baseline_verified.log; tái sử dụng objects của fresh build |
| App size / partition | 307.024 byte (0x4af50), app partition 1 MB, còn 741.552 byte (71%) |
| Python tools / contract | Hai tool AST syntax PASS; cả 4 JSON examples parse PASS |
| Historical verified capture | Existing extractor PASS 4.000 rows, CRC32 D59564EB; artifact trong build/phase8_2_1_audit/historical_capture_validation/ |
| Historical raw log / tracked sample | Raw log 20261024123237 PASS 4.000 rows, CRC32 265827BD; tracked CSV bytes khớp metadata; artifact trong build/phase8_2_1_audit/historical_raw_log_validation/ |
| Bảo toàn source/dữ liệu | SHA-256 cả 40 file tracked/capture/log ban đầu không đổi sau build |
| Hardware/COM5/live GNSS self-test/regression/MQTT/E2E | NOT RUN; không flash hoặc truy cập serial |

Quyết định: network start sau LTE manager và trước idle loop, không đưa network
vào sensor path; worker/callback/queue hữu hạn; giữ timing/GPIO/parser/LTE safe;
chỉ đề xuất API actuator checked cho Phase 5, chưa sửa. Không copy mock expiry/
dedup/ACK behavior sang firmware vì chưa đủ contract/bảo đảm.

**Kết quả audit ban đầu: PASS** cho Repository Audit & Baseline: đã hiểu source, xác định
file/điểm tích hợp, build baseline thật và giữ local data. Không tuyên bố hardware
đã test lại. Các phase 8.2.2–8.2.8 vẫn NOT_STARTED; không commit/push/merge.

## 10. Phân tích log lỗi build người dùng — 2026-10-28

- Người dùng chạy lệnh được hướng dẫn trong chat với ccache bật; CMake có
  `CCACHE_ENABLE=1`. GCC 14.2.0 báo `internal compiler error: Segmentation fault`
  trong RTL pass ira, function rgb_panel_draw_bitmap của ESP-IDF
  esp_lcd_panel_rgb.c:722; Ninja exit 1. Không phải bằng chứng lỗi source firmware.
- Hướng dẫn chat trước thiếu thiết lập tắt ccache giống baseline đã test. Đã sửa
  hướng dẫn audit: `--no-ccache`, `CCACHE_ENABLE=0`, `IDF_PY_BUILD_JOBS=1`.
- Đã đọc source idf_py_actions của SDK cài trên máy để xác nhận hai option/biến
  này được hỗ trợ. Chỉ thay môi trường process và build cache, không Git global.
- Đã chạy reconfigure/build recovery với ccache tắt, một job; chưa kết luận
  nguyên nhân gốc là cache hoặc parallel build. Không xóa cache/fullclean, không
  sửa firmware/SDK/sdkconfig hoặc flash.
- Bản sao log người dùng: build/phase8_2_1_audit/user_build_failure.log và
  user_build_stdout_18724.log. Recovery log: baseline_recovery.log trong cùng thư mục.
- File sửa trong lượt xử lý lỗi: docs/PHASE8_2_1_REPOSITORY_AUDIT.md (lệnh và
  chẩn đoán), docs/PHASE8_2_PROGRESS.md (mở lại trạng thái và ghi bằng chứng).
- Source/config/capture/log cũ: kiểm tra SHA-256 vẫn giữ nguyên 40 file.
- Recovery build PASS exit 0, log baseline_recovery.log, 1.016 bước build chính;
  CMakeCache xác nhận CCACHE_ENABLE=0, Ninja dùng -j1. Không diagnostic
  warning/error/fatal/traceback theo kiểm tra log.
- Phát hiện recovery tái sử dụng LCD object cũ. Đã sao lưu object sinh ra, chỉ
  xóa object tại đúng đường dẫn build được xác minh và buộc compile lại target
  esp_lcd_panel_rgb.c bằng GCC trực tiếp (không ccache): lcd_recompile.log, exit 0.
- Link/build lại sau LCD compile: baseline_recovery_final.log, exit 0, binary
  307.024 byte, app còn 71%. Không compiler diagnostic trong hai log kiểm tra này.
- Tại thời điểm recovery local chưa kiểm tra lại terminal người dùng; sau đó
  đã nhận log build thành công (mục 11). Chưa có hardware test.
- Trạng thái hiện tại `PASS` cho audit/baseline theo recovery local; không bắt đầu phase khác.

## 11. Xác nhận log build thành công từ người dùng — 2026-10-28

- Đã đọc toàn bộ attachment log mới; bản sao giữ nguyên bytes tại
  `build/phase8_2_1_audit/user_build_success.log` (ignored).
- Lệnh `idf.py --no-ccache ... -D CCACHE_ENABLE=0 reconfigure build` đã hoàn tất
  trên terminal người dùng: CMake truyền CCACHE_ENABLE=0, Ninja chạy `-j 1 all`,
  kết thúc `Project build complete`. Không có compiler error/crash trong log này.
- Đây là configure/incremental build, có dùng lại object; không gọi là fresh
  compile toàn bộ. Forced compile LCD và build local đã được ghi riêng ở mục 10.
- Binary 0x4af50 (307.024 byte), app partition 0x100000 (1 MB), còn 0xb50b0 (71%).
  Bootloader 0x5700 byte, còn 32% vùng bootloader.
- Dòng bỏ qua esp_blockdev không có CMakeLists và thông báo giới hạn SoC của
  ESP-TEE là thông tin cấu hình trong log; không làm build thất bại.
- Chưa có flash/serial/runtime/sensor regression hoặc network test; không đánh
  dấu các mục đó PASS từ log build. Chưa khẳng định nguyên nhân gốc GCC ICE.
- Cập nhật docs/PHASE8_2_PROGRESS.md và docs/PHASE8_2_1_REPOSITORY_AUDIT.md để
  ghi nhận retest của người dùng; không sửa firmware/SDK/config, không build lại.
- **Phase 8.2.1: PASS**. Chờ lệnh `làm phase 2`; các phase còn lại NOT_STARTED.

## 12. Xác minh runtime từ thiết bị thật — 2026-10-28

Người dùng cung cấp kết quả extractor PASS 4.000 mẫu, CRC32 83E4CCDE.
Đã đọc trực tiếp log/capture trong workspace và chạy lại hàm extract hiện có:

- Log: `log.fall_detection_firmware.20261028182729.txt`.
- CSV: `build/phase8_2_1_audit/runtime_capture/fall_event_synthetic_20261028_183231.csv`.
- Metadata: cùng tên với đuôi `.metadata.json`.
- Phân tích: `build/phase8_2_1_audit/runtime_capture/runtime_analysis.json` (ignored).
- Log có một reset POWERON sớm, sau đó đến monotonic 282.142 ms (~4 phút 42 giây)
  không có reset tiếp/panic/watchdog/brownout/error-level được quan sát. Không
  suy diễn thành long-run soak test. ELF SHA prefix a21f0180b trong log khớp ELF
  local của baseline, version dae70f6, ESP-IDF v5.5.5.

| Hạng mục | Kết quả và giới hạn |
| --- | --- |
| Sensor init / PSRAM | BMI270/BMP388 init PASS; PSRAM 8 MB memory test OK, event payload allocation 504.000 byte thành công |
| Sampling | 56 cửa sổ: IMU 99,9–100,0 Hz; BMP 24,9–25,1 Hz; seq/ok cuối 28.007/28.007 |
| Lỗi tài nguyên/timing được log | imu_err, missed_ticks, bmp_err, diag_dropped, lt8ms, gt12ms, outliers đều 0 trong các cửa sổ |
| Jitter | Toàn phiên diagnostics gap 9.981–10.022 us; riêng capture CSV 9.985–10.015 us, trung bình 10.000 us |
| PRE/POST / CSV | event_verify PASS fail_checks=0; 3.000 PRE + 1.000 POST, seq 1500–5499, đúng một marker đầu POST; CRC32 83E4CCDE; CSV khớp nguyên bytes output extract; 4.000/4.000 dòng pressure valid |
| GNSS self-test | PASS; test state synthetic tách riêng; không phải outdoor fix hoặc live NMEA PASS |
| GNSS thật | CHƯA PASS: 56 báo cáo đều RX total=133, parsed RMC/GGA=0; LOCATION UNAVAILABLE, không CURRENT |
| LTE safe mode | Có UART disabled/no AT commands; GPIO18 diagnostic hoàn tất; không xác minh LTE registration/data/MQTT |
| Button/vibration/buzzer | Chỉ init log được xác minh; chưa kiểm tra nút nhấn/polarity vật lý hoặc bật/tắt actuator thật |

Synthetic capture chỉ là kiểm thử sensor, không phải ngã thật hoặc MQTT TEST_ALERT.
Không có bằng chứng GNSS NMEA thật đang chạy liên tục; nên kiểm tra nguồn/GND
chung và GNSS TX → GPIO15 trước bài test riêng, giữ parser hiện tại.
Điểm này không chặn Wi-Fi Manager với location UNAVAILABLE đúng contract.

Files changed: docs/PHASE8_2_PROGRESS.md và docs/PHASE8_2_1_REPOSITORY_AUDIT.md
để bổ sung kết quả thật. Không sửa firmware/SDK/config hoặc flash/build lại.
Log mới là file untracked do người dùng tạo, giữ nguyên nội dung.
**Phase 8.2.1: PASS**, các phase 8.2.2–8.2.8 vẫn NOT_STARTED; chờ `làm phase 2`.

## 13. Phase 8.2.2 — triển khai ngày 2026-10-28

Dependency: Phase 1 audit/build và baseline runtime sensor PASS. GNSS thật
NMEA chưa PASS không chặn Wi-Fi; giữ location unavailable, không sửa parser.
Đã đọc lại source app/CMake/config/contract và các API/source ESP-IDF v5.5.5 liên quan.
Áp dụng tdd-workflow cho host test-first, security-review cho credential/config handling.

| File thay đổi/tạo | Mục đích |
| --- | --- |
| main/wifi_manager.c, main/wifi_manager.h | STA worker, async init, snapshot, event handling, DHCP timeout/backoff và cleanup |
| main/network_config.h, main/network_config.example.h | Defaults tắt Wi-Fi và template local không secret |
| main/app_main.c | Thêm include và gọi start sau các manager cũ, không chờ kết nối |
| main/CMakeLists.txt | Register Wi-Fi source/dependencies và theo dõi thêm/xóa header local |
| .gitignore | Ignore main/network_config.local.h trước khi có credentials |
| tests/wifi_manager/host_sdk.h, tests/wifi_manager/host_test.c | Fake SDK/clock để test source manager thật, không nằm trong firmware build |
| tools/test_wifi_manager.py | Runner GCC/gcov và report coverage trong ignored build/ |
| docs/PHASE8_2_2_WIFI_MANAGER.md | Kiến trúc, cấu hình private, build/flash/test/reconnect/regression instructions |
| docs/PHASE8_2_PROGRESS.md | Trạng thái, kết quả và hardware tests còn thiếu |

Quyết định:

- Start chỉ tạo worker, không chờ Wi-Fi/DHCP; worker priority 3, stack 6.144 byte.
  Callback copy hữu hạn/notify; worker gọi driver và log. Snapshot critical section ngắn.
- Kết nối chỉ true sau nonzero IPv4 đúng interface. Disconnect/lost-IP làm false ngay.
- Backoff 1/2/4/8/16/30 giây, cap 30 giây, reset sau GOT_IP; mỗi attempt timeout
  30 giây bao gồm DHCP. Repeated down events không tạo retry burst/queue vô hạn.
- Không tự erase NVS hoặc dùng helper netif có assert/abort; init error ERROR,
  cleanup tài nguyên manager và cần reboot sau xử lý nguyên nhân. Shared loop/stack giữ lại.
- Credentials chỉ file local ignored, validate độ dài, WPA2 trở lên, WIFI_STORAGE_RAM;
  không in SSID/password; binary chứa cấu hình thật phải giữ riêng như secret.
- Không thêm MQTT, TEST_ALERT hoặc STOP_BUZZER. Giữ nguyên GPIO, sampling,
  sensor/ring/CSV, GNSS parser, alert APIs và LTE OFFLINE_UNVERIFIED.

| Build/Test | Kết quả / bằng chứng |
| --- | --- |
| Test-first RED | Runner fail vì thiếu wifi_manager.c trước triển khai; build/phase8_2_2/tests_red.log |
| Host tests | 28 kịch bản PASS: validation/boundaries, lifecycle, event loss, IP validation, disconnect/lost-IP, backoff/reset, DHCP timeout, duplicate down, init-failure cleanup và startup timeout |
| Coverage | wifi_manager.c 210/213 executable lines = 98,59%; gcov branches executed 98,86%, taken at least once 85,23%; build/phase8_2_2/host_tests/results.json và host_tests.log |
| Fresh ESP32 build | PASS exit 0, ESP-IDF v5.5.5, ccache off, một job; 1.089 bước build chính; build/phase8_2_2/firmware_build.log |
| Compile diagnostics | Không warning/error/fatal/traceback trong firmware build được kiểm tra |
| App size | 0xd0dd0 = 855.504 byte, app partition 1 MB, còn 0x2f230 = 193.072 byte (18%); không đổi partition |
| Header add/remove | Hai build PASS tự phát hiện header, recompile app_main; build-only marker có trong binary khi header tồn tại, biến mất khi xóa; config_present_build.log/config_removed_build.log, config_rebuild.exitcode=0 |
| Git/secret checks | Local header ignore/untracked; template/defaults SSID/password rỗng; file test đã xóa; không có credentials thật được tạo/đọc |
| Preservation | 41 file gốc được hash; chỉ .gitignore/main CMake/app_main đổi có chủ đích; 38 file còn lại gồm sensor/GNSS/LTE/alert/sdkconfig/captures/logs giữ nguyên |
| Hardware Wi-Fi/DHCP/reconnect/sensor với radio | NOT RUN; không flash/serial hoặc kết nối AP trong lượt triển khai |

Header test dùng giá trị synthetic build-only, không credentials thật; `-- GLOB
mismatch!` trong hai build là tín hiệu CMake regenerate, không phải compiler error.
Firmware cuối trở về SSID rỗng (Wi-Fi disabled). Cần người dùng tạo file local
và điền credentials, build/flash/test theo tài liệu trước khi đánh dấu PASS.

Chưa xác minh: Wi-Fi 2.4 GHz thật, IP DHCP, AP offline lúc boot, ít nhất hai lần
mất AP/reconnect, sensor jitter/CSV/PSRAM/heap/task với radio, GNSS/LTE safe-mode
trong phiên Wi-Fi. GNSS NMEA thật vẫn có vấn đề từ baseline Phase 1.
Host coverage không thay thế kiểm thử hardware/E2E.

**Phase 8.2.2: CODE_DONE_NEEDS_HARDWARE_TEST**. Các phase 8.2.3–8.2.8 vẫn
NOT_STARTED. Không tự commit/push/merge hoặc bắt đầu Phase 3.

## 14. Audit log Wi-Fi thật mới nhất — 2026-10-28

Theo yêu cầu đọc log/xác định PASS, chỉ phân tích và cập nhật tài liệu; không
tự sửa firmware, build, flash, mở COM hoặc triển khai phase khác.

- Log mới nhất: `log.fall_detection_firmware.20261028190530.txt`, 393.370 byte,
  SHA-256 `7291a8a684f25ef14421eb03b2c59591fd9505b64ad9c98e0e940399c3d561f3`.
- Chi tiết phân tích và CSV/metadata đã validate:
  `build/phase8_2_2/log_review/latest_runtime_analysis.json`,
  `capture_20261028190530.csv`, `capture_20261028190530.metadata.json`.
- Chỉ ghi dữ liệu cần kiểm thử; không đọc/in nội dung credentials local.
  File cấu hình local vẫn được ignore và không nằm trong git ls-files.

| Tiêu chí / mục kiểm tra | Kết quả thật |
| --- | --- |
| Wi-Fi STA/DHCP | PASS cho kết nối ban đầu: station start t=2.221 ms, GOT_IP 192.168.0.11 t=6.451 ms, connected=true attempts=1 |
| Reconnect | CHƯA TEST: chỉ một GOT_IP, không có dòng offline/retry hoặc lần mất mạng/phục hồi; chưa có hai chu kỳ AP off/on hoặc boot AP offline |
| Sensor startup | CHƯA PASS: cửa sổ đầu seq=500, ok=484, missed_ticks=16, imu_hz=96,7, bmp_hz=24,3; gap 3.638/10.331/72.413 us, 7 jitter outliers |
| Sensor sau startup | 19 cửa sổ sau IMU 99,9–100,0 Hz; missed_ticks giữ ở 16 không tăng thêm, jitter outliers=0; không có imu_err/bmp_err/diag_dropped trong đoạn log |
| CSV / PRE-POST | PASS: extractor hiện có chạy lại với log mới, 4.000 rows CRC32 40A38A5D, seq 1500–5499, 4.000 pressure valid; gap capture 9.355–10.654 us; event_verify PASS fail_checks=0 |
| Quan hệ CSV/startup | Capture bắt đầu seq=1500 nên không chứa cửa sổ đầu bị mất 16 tick; CSV PASS không chứng minh không regression lúc boot |
| Độ ổn định quan sát | 20 cửa sổ diagnostics, log tới monotonic 102.171 ms (~102 giây); không panic/watchdog/reset/error-level được quan sát trong đoạn đã ghi; chưa đủ phiên 5 phút đã hướng dẫn |
| GNSS/LTE | GNSS self-test PASS nhưng RX/parsed đều 0, chưa có dữ liệu NMEA thật; vấn đề live GNSS có trước Phase 2. LTE vẫn UART disabled/no AT |

Ngữ cảnh startup: PHY báo không tải được RF calibration (0x1102), chuyển full
calibration và lưu dữ liệu mới ở t=2.171–2.211 ms; đây là manh mối cùng giai đoạn
init Wi-Fi, chưa đủ bằng chứng kết luận nguyên nhân trực tiếp gây mất tick.
Không đổi timer/chu kỳ BMI270, parser hoặc âm thầm bỏ qua mẫu lỗi để đạt PASS.

**Kết luận: Phase 8.2.2 CHƯA PASS; trạng thái IN_PROGRESS.** Mở lại từ trạng thái
bàn giao code vì hardware log có regression cần xử lý/xác minh. Cần kiểm tra
startup không mất tick và bổ sung reconnect thật trong khi sensor tiếp tục chạy.
Files changed trong lượt audit: docs/PHASE8_2_PROGRESS.md và
docs/PHASE8_2_2_WIFI_MANAGER.md; source/config/log gốc được giữ nguyên.

## 15. GNSS RAW DIAGNOSTIC riêng — 2026-10-29

Theo yêu cầu riêng của người dùng: chỉ bổ sung chẩn đoán dữ liệu UART1 thật;
không bắt đầu/chuyển phase và không sửa Wi-Fi/LTE/Sensor Manager. Người dùng
báo RX tăng khoảng 240 byte/5 giây, self-test PASS nhưng parsed RMC/GGA=0;
chưa thu/kiểm tra log phần cứng mới trong lượt triển khai này.

| File thay đổi/tạo trong lượt này | Mục đích |
| --- | --- |
| `main/gnss_manager.c` | Bật GNSS_RAW_DIAGNOSTIC; lấy tối đa 128 byte từ chunk UART hiện có, log ASCII escaped/HEX mỗi >=5 giây, đếm event lỗi UART và lý do loại/bỏ qua câu |
| `docs/GNSS_RAW_DIAGNOSTIC.md` | Giới hạn mẫu/log, giải thích counters và hướng dẫn build/flash/monitor COM5 |
| `docs/PHASE8_2_PROGRESS.md` | Ghi bằng chứng build/static và hardware test còn thiếu |

Quyết định và bảo toàn:

- Giữ một `uart_read_bytes()` duy nhất trong GNSS task; không task/reader mới,
  không flush RX hoặc thay dữ liệu thật bằng self-test. RAW được lấy trước lọc
  ký tự/tách câu, không chỉ log câu đã qua parser. Byte vượt giới hạn log vẫn
  được xử lý bởi luồng parser hiện có.
- UART1 RX GPIO15, 9600 8N1, RX ring 2048 byte; task GNSS stack 4096/priority 3
  giữ nguyên. Thêm event queue 32 phần tử, đọc metadata không chờ trong GNSS
  task. SDK v5.5.5 chưa bật framing interrupt mặc định nên bật thêm riêng bit
  framing, giữ các ngưỡng/cấu hình RX khác. Không thêm recovery/flush khi lỗi.
- UART errors báo tổng mỗi cửa sổ (WARN khi có lỗi); queue hữu hạn có thể mất
  event khi bão hòa, không coi counter 0 là chứng minh tín hiệu không lỗi.
- Hàm checksum/parser, self-test, snapshot/current/stale/last-known giữ nguyên.
  Chỉ phân loại lại câu khi parser trả false; không thêm tiêu chí chấp nhận.
  Counters diagnostic reset sau báo cáo; RX total/parsed cũ vẫn tích lũy.
- `GNSS_RAW_DIAGNOSTIC=0` rồi build/flash lại sẽ tắt diagnostic/event queue.
  Không đổi GPIO/baud, logic location, Wi-Fi, LTE hoặc sensor 100 Hz.

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| ESP-IDF build | PASS exit 0: `idf.py --no-ccache -D CCACHE_ENABLE=0 build`, SDK v5.5.5, Ninja -j1, build mặc định `build/`; log `build/gnss_raw_diagnostic/build.log`, exitcode tại `build.exitcode` cùng thư mục |
| Compile/link/partition | Có compile gnss_manager.c.obj, link và Project build complete; app 0xd16a0 = 857.760 byte, còn 0x2e960 = 190.816 byte (18%) trong app partition 1 MB |
| Diagnostics build | Không compiler warning/error; có warning môi trường Python venv do cách ghi đường dẫn slash/backslash, build vẫn hoàn tất với đúng Python venv v5.5.5; không sửa SDK hoặc Git global |
| Static preservation | So sánh trực tiếp với HEAD: toàn bộ khối numeric/checksum/parser/self-test/snapshot không đổi; một UART reader; hash 37 file ngoài GNSS giữ nguyên, gồm sensor/Wi-Fi/LTE/app/CMake/sdkconfig và local network config (chỉ hash, không in nội dung). Bằng chứng `build/gnss_raw_diagnostic/static_checks.json`, `preserved_hashes.json` |
| Diff/encoding | `git diff --check -- main/gnss_manager.c` PASS; source và hướng dẫn UTF-8, không trailing whitespace |
| Flash/monitor/UART RAW thật | NOT RUN; không mở COM5 hoặc flash |
| GNSS live NMEA/fix và sensor timing | NOT VERIFIED; cần log mới với RAW_RX/UART_RX_DIAG/NMEA_RX_DIAG và sensor diag_5s; build/static không thay hardware test |

Trạng thái riêng của diagnostic: **CODE_DONE_NEEDS_HARDWARE_TEST**. Chưa kết
luận nguyên nhân GNSS không parse; chưa xác nhận NMEA thật/outdoor fix hoặc
sensor regression PASS. Hướng dẫn chính xác tại
[GNSS_RAW_DIAGNOSTIC.md](GNSS_RAW_DIAGNOSTIC.md). Giữ trạng thái các phase ở
mục 1; không triển khai phase tiếp theo, không commit/push/merge.

## 16. BUTTON GPIO4 DIAGNOSTIC riêng — 2026-10-29

Theo yêu cầu riêng của người dùng: chỉ bổ sung quan sát mức logic button GPIO4;
không bắt đầu/chuyển phase và không nối thao tác thử vào alert/actuator/network.

Source trước thay đổi cấu hình GPIO4 input, pull-up disable, pull-down enable,
interrupt disable, `BUTTON_ACTIVE_LEVEL=1` và debounce 40 ms. Comment cũ khẳng
định đã test active-high nhưng không có caller cho `button_pressed()` và không có
runtime evidence mới; Phase 4 từng dùng active-low. Vì vậy active level giữ nguyên
để đo trước, và comment/log được làm rõ là cấu hình đang tồn tại.

| File thay đổi/tạo trong lượt này | Mục đích |
| --- | --- |
| `main/alert_manager.c` | Log mức ban đầu và chuyển GPIO4 đã debounce, thời điểm monotonic/cạnh raw; không đổi active level/pull/debounce |
| `main/alert_manager.h` | Làm rõ ACTIVE-HIGH là cấu hình cần đo, không phải kết luận mới |
| `main/app_main.c` | Main loop có sẵn poll 20 ms và bỏ event; không thêm task, không dispatch action |
| `docs/BUTTON_GPIO4_DIAGNOSTIC.md` | Cách đọc log, quy trình nhấn/thả và lệnh build/flash/monitor |
| `docs/PHASE8_2_PROGRESS.md` | Ghi phạm vi, bằng chứng và phần hardware chưa xác minh |

Thiết kế: chỉ log lúc init và chuyển mức ổn định sau 40 ms; không log liên tục.
Main task thấp ưu tiên poll 20 ms (2 tick với `CONFIG_FREERTOS_HZ=100`), không
thêm task/ISR. Kết quả `button_pressed()` được cast void, và đây là caller duy
nhất; không gọi vibration/buzzer/MQTT/emergency/call. Sensor Manager priority 12,
GNSS/Wi-Fi/LTE và GPIO5/GPIO6 không sửa.

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| ESP-IDF build | PASS exit 0: `idf.py --no-ccache -D CCACHE_ENABLE=0 build`, ESP-IDF v5.5.5, ccache off, Ninja `-j 1`; log `build/button_gpio4_diagnostic/build.log`, exit code trong `build.exitcode` cùng thư mục |
| Compile/link/partition | `app_main.c` và `alert_manager.c` compile thành công; `Project build complete`; app 0xd1990 = 858.512 byte, còn 0x2e670 = 190.064 byte (18%) trong partition 1 MB |
| Compiler diagnostics | Không có warning/error/fatal/FAILED trong build log được kiểm tra |
| GPIO/static scope | `BUTTON_ACTIVE_LEVEL=1`, debounce 40.000 us, pull-up disable/pull-down enable/interrupt disable giữ nguyên; đúng một caller runtime `(void)button_pressed()`; không caller nào dispatch event |
| Preservation | Hash 11 file ngoài button/app/docs giữ nguyên trước/sau: Sensor Manager, GNSS, Wi-Fi, LTE, network config, main CMake và sdkconfig; artifact `build/button_gpio4_diagnostic/preserved_hashes.json` |
| Diff formatting | `git diff --check` PASS cho source/docs của diagnostic |
| Flash/monitor/nhấn-thả GPIO4 thật | NOT RUN; chưa mở COM5, chưa kết luận polarity |
| Sensor timing và no-action runtime | NOT VERIFIED trên board; cần đối chiếu sensor `diag_5s` và xác nhận không có actuator/network alert khi thử nút |

Trạng thái riêng: **CODE_DONE_NEEDS_HARDWARE_TEST**. Build/static không phải đo
GPIO4 thật. Trạng thái các phase ở mục 1 giữ nguyên; không commit/push/merge.

## 17. MOTOR GPIO5 DIAGNOSTIC riêng — 2026-10-29

Theo yêu cầu riêng của người dùng: chỉ bổ sung kiểm thử motor GPIO5 sau khi đi
dây lại; không bắt đầu/chuyển phase và không phát alert/network action.

Source trước thay đổi đã dùng GPIO5 output, pull-down, active-high; gọi LOW trước
và sau `gpio_config`, nhưng bỏ qua kết quả `gpio_set_level`. Diagnostic giữ nguyên
mapping/active level và bổ sung kiểm tra lỗi OFF.

| File thay đổi/tạo trong lượt này | Mục đích |
| --- | --- |
| `main/alert_manager.c` | Chế độ `MOTOR_GPIO5_DIAG`, one-shot task chờ 5 s, ON 500 ms, cleanup OFF không điều kiện; kiểm tra OFF khi init |
| `main/alert_manager.h` | Khai báo API start diagnostic một lần mỗi boot |
| `main/app_main.c` | Schedule diagnostic sau các manager; lỗi không dừng sensor/GNSS/Wi-Fi/LTE |
| `docs/MOTOR_GPIO5_DIAGNOSTIC.md` | Trình tự, log, giới hạn và hướng dẫn flash/monitor |
| `docs/PHASE8_2_PROGRESS.md` | Ghi phạm vi và bằng chứng; không đổi trạng thái phase |

Task diagnostic priority 2, stack 3.072 byte, không loop/poll; static guard chặn
lần start thứ hai và task tự xóa sau test. GPIO5 được giữ LOW trong 5 giây chờ.
Đường thành công log `MOTOR TEST START`, `MOTOR ON`, `MOTOR OFF`,
`MOTOR TEST COMPLETE`; đường lỗi luôn thử OFF và log nếu OFF thất bại.

So sánh với snapshot ngay trước lượt sửa xác nhận toàn bộ Button runtime/init và
Buzzer runtime/init không đổi. GPIO4 polling 20 ms vẫn chạy; motor test không gọi
button/buzzer/MQTT/emergency/call.

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| ESP-IDF build | PASS exit 0: `idf.py --no-ccache -D CCACHE_ENABLE=0 build`, ESP-IDF v5.5.5, ccache off, Ninja `-j 1`; log `build/motor_gpio5_diagnostic/build.log`, exit code trong `build.exitcode` cùng thư mục |
| Compile/link/partition | `app_main.c` và `alert_manager.c` compile thành công; `Project build complete`; app 0xd2030 = 860.208 byte, còn 0x2dfd0 = 188.368 byte (18%) trong partition 1 MB |
| Compiler diagnostics | Không có warning/error/fatal/FAILED trong build log được kiểm tra |
| One-shot/static | GPIO5 active-high/OFF=0, delay 5.000 ms, ON 500 ms, priority 2; task không có loop, có guard một lần/boot và cleanup OFF không điều kiện |
| Button/Buzzer preservation | So sánh snapshot trước sửa: Button runtime/init và Buzzer runtime/init giống nguyên bytes theo từng section |
| Module preservation | Hash 11 file Sensor Manager, GNSS, Wi-Fi, LTE, network config, main CMake và sdkconfig giữ nguyên; artifact `build/motor_gpio5_diagnostic/preserved_hashes.json` |
| Static artifact / diff | `build/motor_gpio5_diagnostic/static_checks.json`; `git diff --check` PASS cho source/docs diagnostic |
| Flash/monitor/motor thật | NOT RUN; chưa xác minh motor rung 500 ms, OFF/no-repeat hoặc ảnh hưởng sensor 100 Hz trên board |

Trạng thái riêng: **CODE_DONE_NEEDS_HARDWARE_TEST**. Build/static không chứng
minh motor vật lý đã rung/tắt. Trạng thái các phase ở mục 1 giữ nguyên; không
commit/push/merge.

## 18. BUZZER GPIO6 DIAGNOSTIC riêng — 2026-10-29

Theo yêu cầu riêng của người dùng: chỉ bổ sung kiểm thử Buzzer MH-FMD GPIO6 bằng
LEDC PWM; không bắt đầu/chuyển phase và không phát alert/network action.

Source trước thay đổi dùng LEDC low-speed timer 0/channel 0, 2.500 Hz, 10-bit,
duty 512 và `output_invert=1`; `buzzer_off()` dùng duty 0. Diagnostic giữ nguyên
cấu hình này, không thay PWM bằng kéo GPIO LOW/HIGH cố định.

| File thay đổi/tạo trong lượt này | Mục đích |
| --- | --- |
| `main/alert_manager.c` | `BUZZER_GPIO6_DIAG`, one-shot PWM 500 ms, checked OFF và `ledc_stop` fallback; đặt `MOTOR_GPIO5_DIAG=0` |
| `main/alert_manager.h` | Khai báo API start buzzer diagnostic một lần mỗi boot |
| `main/app_main.c` | Schedule buzzer diagnostic thay cho motor diagnostic sau các manager |
| `docs/BUZZER_GPIO6_DIAGNOSTIC.md` | Trình tự, log, cleanup lỗi và hướng dẫn flash/monitor |
| `docs/PHASE8_2_PROGRESS.md` | Ghi phạm vi và bằng chứng; không đổi trạng thái phase |

Task diagnostic priority 2, stack 3.072 byte, không loop/poll; chờ 5 s, PWM
2.500 Hz/duty 512 trong 500 ms, cleanup OFF không điều kiện, thử lại OFF một lần
và tự xóa. Static guard chặn lần start thứ hai. Motor diagnostic implementation
giữ nguyên nhưng compile-time disabled và không còn caller trong app startup.

So sánh snapshot ngay trước lượt sửa xác nhận Button runtime/init và public motor
control/diagnostic implementation không đổi. Buzzer public `buzzer_on/off` giữ
nguyên; init chỉ bổ sung checked OFF.

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| ESP-IDF build | PASS exit 0: `idf.py --no-ccache -D CCACHE_ENABLE=0 build`, ESP-IDF v5.5.5, ccache off, Ninja `-j 1`; log `build/buzzer_gpio6_diagnostic/build.log`, exit code trong `build.exitcode` cùng thư mục |
| Compile/link/partition | `app_main.c` và `alert_manager.c` compile thành công; `Project build complete`; app 0xd2280 = 860.800 byte, còn 0x2dd80 = 187.776 byte (18%) trong partition 1 MB |
| Compiler diagnostics | Không có warning/error/fatal/FAILED trong build log được kiểm tra |
| One-shot/static | GPIO6 LEDC PWM 2.500 Hz/duty 512, delay 5.000 ms, ON 500 ms, priority 2; task không loop, không dùng `gpio_set_level`, có guard một lần/boot và cleanup OFF không điều kiện |
| Error safety | Checked duty 0/update; có `ledc_stop(..., idle=0)` fallback và một lần retry OFF; build xác nhận API hợp lệ với ESP-IDF v5.5.5 |
| Motor disabled | `MOTOR_GPIO5_DIAG=0`; app startup có 0 caller `motor_gpio5_diag_start`; không thể chạy đồng thời từ luồng tự động hiện tại |
| Preservation | Buzzer public API, Button runtime/init, motor public/diagnostic implementation không đổi; hash 11 file Sensor/GNSS/Wi-Fi/LTE/config/CMake/sdkconfig giữ nguyên |
| Static artifact / diff | `build/buzzer_gpio6_diagnostic/static_checks.json`; `git diff --check` PASS cho source/docs diagnostic |
| Flash/monitor/buzzer thật | NOT RUN; chưa xác minh âm thanh 500 ms, OFF/no-repeat, motor không rung hoặc ảnh hưởng sensor 100 Hz trên board |

Trạng thái riêng: **CODE_DONE_NEEDS_HARDWARE_TEST**. Build/static không chứng
minh buzzer vật lý đã phát/tắt. Trạng thái các phase ở mục 1 giữ nguyên; không
commit/push/merge.

## 19. LTE TX ADC DIAGNOSTIC riêng — 2026-10-30

Yêu cầu riêng: đo thụ động A7670C TX tại GPIO18/ADC2_CHANNEL_7; không bắt đầu
phase mới. Nguồn modem 5V/3A riêng, GND chung, TX → GPIO18, GPIO17 chưa nối RX
là wiring người dùng cung cấp; firmware không đổi wiring hoặc drive GPIO17.

Source baseline là 7.12e digital NO_PULL/PULLDOWN, không UART/AT. Git history
hiện có chỉ có một commit cho LTE Manager; không tìm thấy bản 7.12c để khôi phục.
Các số HIGH=285/LOW=215/transitions=404, pull-down LOW=500 và điện áp cũ khoảng
1,8 V do người dùng báo, chưa được xác minh lại trong lượt này. Kết quả tương tự
khi tháo modem chưa chứng minh tín hiệu TX thực sự được drive.

| File thay đổi/tạo | Mục đích |
| --- | --- |
| `main/lte_manager.c` | Nhánh ADC oneshot/calibration, thống kê 5 s, saturation/error handling; 7.12e loại bằng compile-time khi ADC bật |
| `main/lte_manager.h` | Switch chung `LTE_TX_ADC_DIAG=1`; sửa mô tả API không còn khẳng định UART2/AT |
| `main/app_main.c` | Bỏ startup Wi-Fi cả boot khi ADC diagnostic bật; sửa log LTE UART2/AT cũ |
| `docs/LTE_TX_ADC_DIAGNOSTIC.md` | Cấu hình/giới hạn đo, denominator dải điện áp, flash/monitor và cách trở lại baseline |
| `docs/PHASE8_2_PROGRESS.md` | Ghi bằng chứng theo scope riêng, không đổi trạng thái phase |

Thiết kế: một task LTE có sẵn, priority 3/stack 4096; chờ 8 s, xác minh Wi-Fi
NOT_INIT và mapping ADC2 channel 7, tắt hai pull/digital IO GPIO18. ADC 12-bit,
attenuation 12 dB, calibration curve-fitting theo ESP32-S3/SDK. Thu tối đa 500
mẫu, delay khoảng 10 ms, deadline khoảng 5 s; không log từng mẫu. Buffer tĩnh,
sort cuối phiên; median chẵn lấy trung bình hai giá trị giữa.

RAW min/median/max gồm các read thành công; lỗi read có count/error cuối. Mẫu
raw>=4090 đếm saturation/near-rail và loại khỏi mV; raw<=5 cảnh báo ADC floor.
Calibration không khả dụng: RAW ONLY. Lỗi conversion: suppress mV/bands toàn
phiên. mV min/median/max và tỷ lệ các dải [0,200), [200,1000), [1000,1600),
[1600,2000), [2000,3000), [3000,+inf) chỉ dùng mẫu calibrated/unsaturated và
in rõ mẫu số. Không suy diễn điện áp chính xác từ ADC bão hòa hoặc calibration
lỗi. Cleanup calibration/ADC2 có kiểm tra lỗi; task tự xóa, không lặp lại.

Wi-Fi Manager/config giữ nguyên; switch chung bỏ caller init Wi-Fi ở app_main,
không tự khôi phục radio. `LTE_TX_ADC_DIAG=0` + build/flash trở lại 7.12e và
startup Wi-Fi cũ. Source Button/Motor/Buzzer và lịch GPIO4/GPIO6 hiện tại giữ
nguyên; không có action actuator/MQTT/call trong LTE diagnostic.

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| ESP-IDF build | PASS exit 0: `idf.py --no-ccache build`, ESP-IDF v5.5.5, ccache off, Ninja -j1; `build/lte_tx_adc_diagnostic/build.log`, `build.exitcode` cùng thư mục |
| Compile/link/partition | Compile LTE/app thành công, Project build complete; app 0x50460 = 328.800 byte, còn 0xafba0 = 719.776 byte (69%) trong partition 1 MB; không đổi partition |
| Compiler diagnostics | Không warning/error/fatal/FAILED trong build log được kiểm tra |
| ELF/object inspection | Có `adc_oneshot_read`, `adc_cali_create_scheme_curve_fitting`, `esp_wifi_get_mode`; không có `wifi_manager_start`, `esp_wifi_start`, `configure_input`, `sample_gpio`; LTE object không tham chiếu hàm `uart_*` |
| Binary mode strings | Có LTE_TX_ADC_DIAG/Wi-Fi startup skipped; không có NO_PULL HIGH=/PULLDOWN HIGH= của 7.12e |
| Preservation | Hash 11 file Sensor/GNSS/alert/Wi-Fi/config/CMake/sdkconfig không đổi trước/sau build; `build/lte_tx_adc_diagnostic/preserved_hashes.xml` |
| Diff | `git diff --check` PASS cho LTE/app thay đổi; tài liệu diagnostic tạo mới |
| Flash/monitor/calibration thực/điện áp/sensor timing | NOT RUN; build/link/static không xác minh ADC/eFuse, voltage, saturation hoặc sampling trên board |

Binary nhỏ hơn vì bỏ đường Wi-Fi startup và các phần linker không còn cần dùng;
không coi đó là bằng chứng radio/ADC đã test thật. Hướng dẫn:
[LTE_TX_ADC_DIAGNOSTIC.md](LTE_TX_ADC_DIAGNOSTIC.md).

Trạng thái riêng: **CODE_DONE_NEEDS_HARDWARE_TEST**. LTE vẫn offline/unverified,
không xác nhận mức TX 1,8 V, UART ổn định, đăng ký mạng hoặc MQTT. Trạng thái
các phase giữ nguyên; không commit/push/merge.

## 20. Retest Phase 8.2.2 trực tiếp qua COM5 — 2026-10-30

Người dùng đã cấp nguồn USB và yêu cầu tự kiểm thử nếu khả thi. Đã dùng Python
ESP-IDF/pyserial trực tiếp, không điều khiển terminal qua UI. COM5 mở thành công;
đã đóng sau mỗi capture. Không thay đổi Wi-Fi credentials hoặc đọc/in file local.

Phát hiện board đang chạy ELF `2f8e26700...`, mode LTE ADC; log startup xác nhận
`Wi-Fi startup skipped`. Capture thụ động 25,20 s và reset/capture 22,08 s ở
`build/phase8_2_2/live_probe/`; sensor sạch trong bản ADC không chứng minh
sampling khi radio chạy. Đã sao lưu header, hash source và binary/ELF ADC trước
khi chuyển `LTE_TX_ADC_DIAG` từ `1` về `0` để khôi phục đường startup Wi-Fi.
Giữ implementation ADC, GNSS/actuator diagnostic và Sensor Manager hiện có.
LTE trở về GPIO diagnostic 7.12e, UART2/AT vẫn disabled, OFFLINE_UNVERIFIED.

| Kiểm tra | Kết quả thật / giới hạn |
| --- | --- |
| Build | PASS exit 0, ESP-IDF v5.5.5, ccache off, Ninja -j1; `wifi_retest_build.log`; không compiler warning/error được quan sát |
| App/partition | 860.816 byte (0xd2290), còn 18% trong app partition 1 MB; không đổi partition/sdkconfig |
| Flash | PASS exit 0; chỉ app offset 0x10000, esptool hash verified; `wifi_retest_flash.log`; không erase NVS |
| Firmware identity | ELF SHA-256 `55c2e17077f36574cbd7e63ea5ccc0f59fc518dbd09ffc2ff1fa9fd7be6725a7`, runtime prefix khớp `55c2e1707` |
| Startup/DHCP | Station started tại 2.247 ms; GOT_IP 192.168.0.5 tại 3.387 ms, attempts=1 |
| Sensor startup | seq=500, ok=485, missed_ticks=15, IMU 96,9 Hz; gap min/avg/max=3.495/10.309/72.979 us; 7 jitter outliers; bmp_max_read_us=69.746 |
| Chạy tiếp | Capture 421,80 s, 83 diagnostic windows; missed_ticks giữ 15 ở toàn bộ các cửa sổ, imu_err/bmp_err/diag_dropped=0; không brownout/panic/watchdog reset được quan sát sau reset chủ động |
| CSV | Existing extractor PASS 4.000 dòng, CRC32 44A31E64; seq 1500–5499, pressure valid 4.000; không bao quát startup mất tick |
| Reconnect | NOT VERIFIED: chỉ 1 GOT_IP, 0 offline/retry; người dùng xác nhận đã tắt Wi-Fi laptop, không tắt AP cấp mạng cho ESP32; không tính thao tác này là AP loss/reconnect |
| Nguồn/mạng | Người dùng mô tả USB ESP32 và USB Type-C A7670C nối laptop; USB không chứng minh đường Wi-Fi/LTE. ESP32 tự kết nối theo cấu hình firmware; cần xác định AP thực trước test mất mạng |

Log chính: `build/phase8_2_2/live_probe/wifi_runtime_20261030_083741.log`, SHA-256
`8d8c5de4ff4b8537f855df860e15a45cb8709aa4513bef2277847d61e5f86d63`.
Summary: `wifi_retest_summary.json`; CSV/metadata: `runtime_capture/` cùng thư mục.
Raw logs/artifacts chỉ nằm trong ignored build; không đưa credentials lên Git/chat.

Đã xem thêm log lịch sử `log.fall_detection_firmware.20261028191729.txt`: nhiều
brownout và TG1WDT reset, chưa có diag_5s; khác phiên retest hiện tại không ghi
nhận reset bất thường. Không suy diễn nguồn đã ổn định trong mọi điều kiện.

Files changed trong lượt retest: `main/lte_manager.h` (chỉ switch 1 → 0),
`docs/LTE_TX_ADC_DIAGNOSTIC.md` (mode hiện tại),
`docs/PHASE8_2_2_WIFI_MANAGER.md` (bằng chứng mới), và progress này. Hash các
source còn lại/sdkconfig so với đầu lượt không đổi; giữ nguyên các local changes
có sẵn. Firmware hiện trên board và switch source đều là Wi-Fi enabled/ADC off.

**Phase 8.2.2 vẫn IN_PROGRESS**: cần sửa/xác minh regression startup, sau đó test
mất AP/reconnect ít nhất 2 lượt và AP offline lúc boot. Không khẳng định root
cause từ số đo, không thay timing/counters để che lỗi. Chưa chuyển Phase 3,
không commit/push/merge.

## 21. Phase 11.11 — A7670C UART AT diagnostic — 2026-10-30

Yêu cầu riêng Phase 11.11, không triển khai LTE MQTT/registration/call/SMS và
không đổi trạng thái các phase 8.2. Source đầu lượt thực tế ADC=0/7.12e sau retest
mục 20, khác mô tả bản ADC trong yêu cầu. Wiring do người dùng cung cấp: TX modem
→ GPIO18, GPIO17 → RX modem, nguồn riêng 5V/3A, GND chung; shop xác nhận board
hỗ trợ UART logic 3.3V. Không tác động PWRKEY/3.8EN/NET/DTR hoặc đổi mapping.

| File sửa/tạo | Mục đích |
| --- | --- |
| `main/lte_manager.c` | Nhánh UART2 115200/8N1/no-flow, đọc boot/drain, gửi đúng AT CR tối đa 5 lần, deadline/read/log budget hữu hạn và cleanup driver |
| `main/lte_manager.h` | Chọn UART=1/ADC=0, guard compile error nếu đồng thời bật; Wi-Fi skip chỉ theo mode diagnostic |
| `main/lte_at_response.h` | Parser stream nguyên dòng OK, giữ state giữa UART chunks, từ chối nhiễu/overlong/substrings |
| `main/app_main.c` | Log mode đúng, Wi-Fi isolation có chủ đích trong UART mode; bỏ caller auto-test buzzer riêng mode UART |
| `tests/lte_at_response_test.c` | Host test parser thật; không tham gia firmware hoặc tạo phản hồi modem giả |
| `docs/PHASE11_11_LTE_UART_AT_DIAGNOSTIC.md` | Thiết kế, giới hạn, mode switching, log và flash/monitor |
| `docs/LTE_TX_ADC_DIAGNOSTIC.md` | Cập nhật hướng dẫn khôi phục ADC khi có switch UART mới |
| `docs/PHASE8_2_PROGRESS.md` | Ghi bằng chứng/giới hạn Phase 11.11 riêng |

UART2 driver cài trước khi chờ 10 giây, boot RX được log và không đưa vào parser.
Drain thêm 200 ms, báo buffered snapshot rồi flush trước AT. Chỉ gửi 3 byte
41 54 0D, tối đa 5 lần; 2 s response window tạo spacing khoảng 2 s, TX completion
timeout 200 ms. PASS chỉ khi nguyên dòng OK kết thúc CR/LF; echo không PASS.
ASCII escaped/HEX cho byte bất thường; tối đa 256 byte log mỗi window nhưng
parser nhận mọi byte đọc, summary có suppressed. Deadline và giới hạn 32.768
byte/window chống flood. Không xóa UART driver nếu đã thuộc module khác.

ADC/7.12e giữ nguyên implementation dưới nhánh compile loại trừ nhau. Wi-Fi skip
có chủ đích riêng UART (SKIP_WIFI=1); tắt mode/isolation sẽ có lại startup Wi-Fi,
không sửa Wi-Fi Manager/config. Motor auto disabled sẵn, buzzer auto caller bị
bỏ trong mode UART; alert_manager code và GPIO4 polling 20 ms giữ nguyên.

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| Build | PASS exit 0, `idf.py --no-ccache build`, ESP-IDF v5.5.5, ccache off, Ninja -j1; `build/phase11_11/build.log`, `build.exitcode` |
| App/partition | 0x4cbe0 = 314.336 byte, còn 70% app partition 1 MB; sdkconfig/partition không đổi |
| Compiler diagnostics | Không warning/error/fatal/FAILED trong build log |
| Parser host test | PASS: echo-only, OK chia chunks/thiếu terminator, substring/whitespace/lowercase, NUL/DEL, overlong và phục hồi sau newline; `parser_test.log` cùng thư mục |
| ELF/static | UART read/write/flush linked; ADC read/7.12e/Wi-Fi start/buzzer auto-test không có trong ELF; source ADC/GPIO body nguyên trạng |
| Preservation | Hash source ngoài LTE/app và sdkconfig giữ nguyên; `source_hashes.before.xml`, `protected_hashes.xml`, `verification.xml` dưới build/phase11_11 |
| Formatting | git diff --check PASS cho source thay đổi |
| Flash/monitor/AT modem thật/regression | NOT RUN; chưa gửi lệnh từ bản mới ra modem, chưa có AT RESPONSE PASS thật hoặc bằng chứng timing sensor |

**Phase 11.11: CODE_DONE_NEEDS_HARDWARE_TEST**. AT OK chỉ chứng minh phản hồi
UART/AT, không chứng minh LTE network/data/MQTT readiness. Hướng dẫn chi tiết:
[Phase 11.11](PHASE11_11_LTE_UART_AT_DIAGNOSTIC.md). Chưa chuyển phase,
không commit/push/merge.

## 22. Phase 8.2.2 PASS — startup/reconnect/sensor regression — 2026-10-30

Theo lệnh tiếp tục Phase 2, đã xác định SSID local và đối chiếu với association
log thật mà không đọc/in password hoặc ghi tên mạng vào tracked docs. Người dùng
tắt/bật đúng AP; ESP32 giữ nguồn USB và không reset trong hai chu kỳ.

Fix được triển khai theo hai lớp bằng chứng. Radio/PHY/NVS init chuyển lên trước
`sensor_manager_start()`, còn association/DHCP/reconnect vẫn ở worker. Sau khi
hardware test cho thấy retry vẫn dồn 1–2 tick khi `esp_timer` cùng Wi-Fi ở core 0,
đã pin Wi-Fi worker/driver core 0, Sensor Task priority 12 core 1 và `esp_timer`
task core 1; timer ISR giữ core 0. Không đổi 10 ms period, I2C sampling, ring,
BMP every-four-ticks, counters hoặc ngưỡng jitter.

| Kiểm tra | Kết quả thật |
| --- | --- |
| TDD host | RED trước fix; GREEN 30/30 scenario; source Wi-Fi manager line coverage 98,67% (222/225) |
| Build | ESP-IDF v5.5.5 PASS, ccache off, Ninja -j1; retry sau GCC ICE SDK `esp_lcd_panel_rgb.c`; không sửa SDK |
| Binary | 860.928 byte (`0xd2300`), app partition 1 MB còn 18%; ELF SHA-256 `F11052067FDD94CD92A5EF6B910FC880CDCC08D8045822BB42DA8C71FA9881C7` |
| Flash | App offset 0x10000 PASS, esptool hash verified; runtime ELF prefix khớp `f11052067` |
| Wi-Fi/DHCP | Startup GOT_IP tại 3.277 ms, attempts=1; cấu hình local đúng, không lộ secret |
| Reconnect thật | Hai lần AP loss tại 143.327/365.297 ms; GOT_IP lại tại 317.767/538.677 ms; backoff 1/2/4/8/16/30/30 s và reset về 1 s sau IP |
| Sensor regression | 567,59 s, 112 cửa sổ; seq/ok 56.035/56.035; missed_ticks/imu_err/bmp_err/diag_dropped/outliers đều 0; gap toàn phiên 9.918–10.077 us |
| CSV | Existing extractor PASS 4.000 dòng, CRC32 A7B13734, seq 1500–5499, pressure valid 4.000 |
| Safety/regression | GNSS self-test PASS; LTE UART disabled/no AT/OFFLINE_UNVERIFIED; không brownout/panic/watchdog; không MQTT/call/SMS |

Artifact chính: `build/phase8_2_2/startup_fix/timer_core1_retry.log`, SHA-256
`4ed04c2bc255f74c0ad14445523a96b89ebb34f29c19fe0c9fa1043ceab1e760`;
summary cùng basename `.json`; CSV/metadata trong `timer_core1_runtime_capture/`.
Các artifact ở ignored build, không commit credentials.

Một boot reset kép ngay sau flash bị BMI270 probe fail và app_main dừng, bị loại
khỏi evidence vì không có acquisition/Wi-Fi runtime. Reset lại cùng binary tạo
phiên 567,59 s PASS; theo dõi probe rời rạc ở Phase 8.2.6. AP-off-at-boot hợp lệ
chưa ghi riêng, nhưng acceptance Phase 2 về DHCP, reconnect và sensor đã đạt.

Files source/config sửa trong lượt hoàn tất: `main/wifi_manager.c/.h`,
`main/app_main.c`, `main/sensor_manager.c`, `main/lte_manager.h`, `sdkconfig`,
`tests/wifi_manager/host_test.c`, `tests/wifi_manager/host_sdk.h`,
`tools/test_wifi_manager.py`; tài liệu Wi-Fi/progress/Phase 11.11 được đồng bộ.
Không commit/push/merge; local changes khác giữ nguyên.

**Phase 8.2.2: PASS.** Phase được phép tiếp theo là 8.2.3, chỉ khi có lệnh
`làm phase 3`; chưa triển khai MQTT trong lượt này.

## 23. Phase 8.2.3 — MQTT Manager — 2026-10-31

Đã đọc plan/progress/contract, mock và source thật. Wi-Fi Phase 2 PASS được giữ
nguyên. ESP-MQTT có sẵn trong component `mqtt` của ESP-IDF v5.5.5; không tải/sửa
SDK hoặc viết lại Backend/AI. Người dùng chọn broker demo laptop và xác nhận
chưa thể test board; serial enumeration không có COM5.

| File sửa/tạo | Mục đích |
| --- | --- |
| `main/mqtt_manager.c`, `main/mqtt_manager.h` | Worker core 0/priority 3, MQTT 3.1.1 clean session, snapshot, reconnect, SUBACK matching, bounded fragment assembly/command queue và publish queue |
| `main/CMakeLists.txt` | Register manager và component `mqtt` |
| `main/app_main.c` | Chuẩn bị MQTT sau Wi-Fi/before acquisition; worker chờ IPv4, MQTT lỗi không dừng sensor |
| `main/network_config.h`, `.example.h` | Macro URI/device ID/auth/CA; defaults URI trống để MQTT disabled |
| `tests/mqtt_manager/host_sdk.h`, `host_test.c` | Fake SDK/RTOS tests của source thật; không giả kết quả hardware |
| `tools/test_mqtt_manager.py` | Host compile/run/gcov và results.json |
| `tools/start_phase3_broker.ps1` | Broker Docker có auth/ACL, credentials ngẫu nhiên trong ignored build, default bind localhost; kiểm tra startup thực |
| `tools/configure_phase3_device.ps1` | Cấu hình block MQTT local từ IP LAN và secrets demo, giữ Wi-Fi, không in password |
| `docs/PHASE8_2_3_MQTT_MANAGER.md` | Kiến trúc/API/limits, broker/config/build/flash/test, giới hạn bằng chứng |
| `docs/PHASE8_2_PROGRESS.md` | Kết quả và dependency hiện tại |

Callback MQTT không gọi network publish/subscribe hoặc actuator. Worker subscribe
đúng `iot/devices/{deviceId}/command` QoS 1 và chỉ ready sau matched SUBACK QoS 1.
RX/TX queue 4 entry, max payload 1.024 byte, input/output buffer 512/1.400 byte,
SDK outbox limit 8.192 byte. Retained/wrong-topic/QoS/malformed/oversize fragments
bị drop. Consumer raw command chỉ là API cho Phase 5, chưa parse/thực thi/ACK.

Last Will status QoS 1/retained là envelope offline gồm schemaVersion/deviceId/
online=false/mode=REAL/lteReady=false. Không đoán alertState hoặc timestamp.
Strict full-status DTO/merge semantics của Backend chưa có bằng chứng; phải
thống nhất khi làm Phase 4/7. Không publish online status hoặc TEST_ALERT trong
Phase 3. `mqtts://` yêu cầu CA PEM, không bỏ hostname verification; TLS thật chưa test.

| Kiểm tra | Kết quả / giới hạn |
| --- | --- |
| TDD | RED khi chưa có manager; RED/GREEN cho first empty fragment ở boundary 1.024 byte và callback cleanup khi client task start lỗi |
| Host tests | 22/22 PASS, line coverage 99,58% (source 239 executable lines); fake SDK/RTOS, hardware_verified=false; `build/phase8_2_3/tests_verified.log`, `host_tests/results.json` |
| Final ESP-IDF build | PASS exit 0, ccache off/Ninja -j1; `build/phase8_2_3/build_verified.log`, `build_verified.exitcode`; không compiler diagnostic lỗi |
| Size | 997.328 byte (`0xf37d0`), còn 51.248 byte (`0xc830`, 5%) của app partition 1 MB; build có Warning gần đầy; không thay partition/sdkconfig |
| ELF identity | SHA-256 `98BAC46B17F298BE09EFCF9EC5EDEF954C6BFE9CC9867EAEDAC526E8D38E1DB5` |
| Binary identity | SHA-256 `F9E85E3327875E873D7EAEBDC8197EC101185545369236A7F3BFEAA174632DB4` |
| Broker demo | Mosquitto 2.1.2 trong Docker, container `fall-phase3-broker`, running, chỉ bind 127.0.0.1:1883; hai tài khoản password riêng, per-device ACL |
| Broker publish/subscribe | Native backend publisher → device fixture subscriber nhận nguyên JSON MQTT-v1, QoS 1/retain=false; không có ESP32 kết nối |
| Broker auth/ACL | Anonymous CONNECT bị từ chối (exit 5); cross-device PUBLISH bị deny/PUBACK reason 135 (CLI có thể exit 0); log `broker_validation.log` |
| Scripts | Cả hai PowerShell script parse syntax PASS; broker startup thực được xác minh; config helper append/update fixture PASS, giữ Wi-Fi và một managed block; chưa áp dụng vào local header thật vì chưa có IP LAN test |
| Preservation | Hash source/config/contract ban đầu: chỉ app_main/CMake/network_config.h/example.h thay đổi; sensor/Wi-Fi/GNSS/LTE/alert/sdkconfig/contract giữ nguyên |
| Hardware | NOT RUN: không flash/monitor; ESP32 CONNACK/SUBACK/reconnect/LWT và sensor khi MQTT chạy chưa được chứng minh |

Broker image digest đã ghi:
`eclipse-mosquitto@sha256:860aeb5d63ce509508f6dcfb2bc8a1c1dd2bc60555b562b45ce90e52d8dabb0f`.
Private credentials ở `build/phase8_2_3/broker/client_secrets.json`; chỉ mount
subdir `config/` vào container, không mount plaintext client JSON. Broker startup
lần đầu lỗi quyền password file; đã sửa owner UID 1883, bỏ đúng container lỗi
và giữ config host. Bản hiện tại kiểm tra running trước khi báo thành công.
Không cài Mosquitto service hoặc đổi firewall; Docker Desktop đã được khởi động.

Nguồn native Mosquitto không tải được từ terminal dù đã thử quyền mạng; fallback
Docker official image hoạt động. Tên tag Windows release không có trên registry,
nên dùng major tag `2` và lưu digest/version thực để đối chiếu. Không coi broker
fixture là wearable PASS hoặc ACK thực thi.

**Phase 8.2.3: CODE_DONE_NEEDS_HARDWARE_TEST.** Trước khi flash phải chọn IP LAN
và chạy helper local config, build lại; URI hiện trống nên MQTT disabled theo
defaults. Cần kiểm tra client/subscribe/reconnect thật và sampling; theo dõi size
trước Phase 4/5. Phase 4–8 vẫn NOT_STARTED. Không commit/push/merge.

## 24. Phase 8.2.3 PASS — ESP32 MQTT hardware test — 2026-10-31

Theo yêu cầu "đã kết nối esp32, test đi", đã nhận CH343 COM5, xác minh laptop
cùng mạng Wi-Fi local với thiết bị và chuẩn bị broker demo truy cập qua LAN.
Không cần người dùng thao tác tắt AP trong lượt này. Không sửa firmware hoặc
contract; chỉ cập nhật cấu hình ignored local header, build/flash firmware Phase 3
đã triển khai, sửa lỗi script broker phát hiện khi chạy và ghi tài liệu/bằng chứng.

| Kiểm tra | Kết quả thật |
| --- | --- |
| Local config | Helper thêm MQTT URI LAN/auth từ private broker JSON, giữ nguyên Wi-Fi; header và credentials vẫn Git ignored |
| Build | ESP-IDF v5.5.5 exit 0, ccache off/Ninja -j1; `build/phase8_2_3/hardware/build.log` |
| Size/hash | App 997.424 byte (`0xf3830`), free 51.152 byte (`0xc7d0`, 5%); ELF SHA-256 `B874D37BA2108B80175D30144D231474ECF5B1055F11F338F0FBFABCAF5A9F65`; BIN SHA-256 `D92BE7F2734A58B31E83D121A455926115F781A2B39016E5DD0CA07D2846D2E7` |
| Flash | COM5 PASS exit 0, esptool hash verified; runtime ELF prefix `b874d37ba` khớp; không thay partition/sdkconfig |
| Wi-Fi/MQTT startup | IPv4 lúc uptime 3.521 ms, MQTT connected 4.111 ms, SUBACK QoS 1 4.121 ms; broker xác nhận `real-waist-esp32s3-001`, đúng command topic |
| Broker recovery | Hai lượt chủ động stop/start và recreate; MQTT session 2/3 connected 72.921/149.411 ms, SUBACK 72.941/149.421 ms; không reset board trong phiên; transport errors trong khoảng broker offline là expected |
| First capture | `mqtt_lan_01.log/.json`: 182,31 s, 35 diag windows, seq/ok 17.517/17.517; 0 missed_ticks/IMU/BMP error/diag_dropped/outlier, gap 9.711–10.287 us; CSV 4.000 rows CRC `7F046FC6` |
| Second capture | `mqtt_retained_02.log/.json`: 125,08 s, 24 diag windows; 0 missed_ticks/IMU/BMP error/diag_dropped/outlier; CSV 4.000 rows CRC `ED126037`; reset đầu phiên là có kiểm soát |
| RX size/fragmentation | Exact JSON 200/900/1.024 byte QoS 1 enqueue thành công; 1.100 byte bị drop; broker ghi đúng byte sizes, device counters đối chiếu từng bước |
| RX safety/bounds | Retained replay sau subscribe bị từ chối khi queue rỗng (`received=0 dropped=1`), QoS 0 bị từ chối; queue 4 entry từ chối entry thứ 5, không crash |
| Last Will | Reset có kiểm soát; broker thay thế old TCP session lúc device reconnect, phát offline envelope thực của ESP32. Subscriber live nhận QoS 1; subscriber mới nhận retain=1/QoS 1; `lwt_received.log`, `lwt_retained.log` |
| GNSS/LTE | GNSS self-test PASS, live RMC/GGA vẫn parse nhưng no-fix; LTE UART disabled/no AT, giữ OFFLINE_UNVERIFIED; không call/SMS/rescue |
| Buzzer | Existing one-shot báo `CONFIRMED_BY_LEDC_DRIVER`/PASS; chưa xác nhận âm thanh trực tiếp, chưa test STOP_BUZZER qua MQTT |
| Evidence verification | `hardware/verify_capture.py` PASS, `hardware/verification.json` ghi hardware_verified=true dựa trên hai capture, broker sizes và LWT; không dùng mock |

Tất cả artifact trên dưới `build/phase8_2_3/hardware/`, ignored. CSV và metadata
ở `runtime_capture/` và `retained_runtime_capture/`. First raw capture SHA-256
`72ffd8a7e02c65c1abc71ca04346952368513d9c9ca504b7551d983b3422c751`;
hash các log còn lại lưu trong `verification.json`.

Files changed trong lượt test:

- `tools/start_phase3_broker.ps1`: sửa recreate với password file có sẵn:
  không dùng `-c` khi đã có file; đổi owner root trước utility update và về UID
  1883 trước server; password/ACL quyền 0600. Đã tái hiện lỗi thật và chạy lại
  thành công với credentials cũ; `broker_recreate_fixed.log`. Không còn warning
  ACL permissions/ownership khi startup. Không đổi firewall hoặc tạo service.
- `docs/PHASE8_2_3_MQTT_MANAGER.md`: cập nhật broker LAN, hardware evidence và
  giới hạn retained delivery/LWT; progress này cập nhật bảng trạng thái/next phase.
- Ignored `main/network_config.local.h`: cấu hình MQTT thật; không đưa secret
  vào tracked files. Artifact scripts/capture/build/CSV chỉ nằm dưới ignored build.

Giới hạn kỹ thuật: MQTT 3.1.1 forward live publish retain=true với retain=false;
retain filter chỉ chặn retained replay được broker đánh dấu, không chứng minh
authorization/replay protection. Retained probe command đã xóa. LWT offline
status vẫn retained sau reconnect vì normal online status thuộc Phase 4.
Chưa test TLS, AP-loss khi MQTT chạy, boot broker-offline riêng, soak/heap/task
campaign, regression actuator đầy đủ, Backend/App hoặc real ACK. Các mục này
không được ghi PASS nhờ transport test; theo dõi đúng phase liên quan.

**Phase 8.2.3: PASS** theo acceptance MQTT Manager trên broker demo thật.
Phase tiếp theo được phép: **8.2.4**, chỉ khi người dùng nhập `làm phase 4`.
Không triển khai Phase 4–8, không commit/push/merge; broker demo hiện chạy trên
IP Wi-Fi LAN laptop đã cấu hình, board giữ firmware Phase 3.

## 25. Phase 8.2.4 PASS — Status & TEST_ALERT — 2026-10-31

Đã đọc AGENTS/plan/progress/contract, mock, source manager và API SDK v5.5.5
thực tế trước khi sửa. Wi-Fi/MQTT đã hardware PASS; COM5 và broker demo vẫn sẵn
sàng. Không mở rộng sang command execution/ACK, Backend/AI hoặc Phase 5–8.

| File sửa/tạo | Mục đích |
| --- | --- |
| `main/device_telemetry.c/.h` | Worker priority 2/core 0, bounded JSON/status/event, UUID v4, local serial parser/cooldown, bounded retry và UTC/location từ GNSS thật |
| `main/app_main.c`, `main/CMakeLists.txt` | Register/start publisher sau GNSS/actuator init; không đưa publish vào Sensor Task/callback |
| `main/alert_manager.c/.h` | Thêm API chỉ đọc LEDC duty với init/error check; cần để status phản ánh output thật; không đổi control/timing/diagnostic/GPIO |
| `main/network_config.h`, `.example.h` | Test serial opt-in default 0; không thay credentials template |
| `tests/device_telemetry/host_sdk.h`, `host_test.c` | Test real publisher/encoder với SDK/RTOS boundaries giả; JSON/UTC/location, serial safety, reconnect và failure scenarios |
| `tools/test_device_telemetry.py` | Host compile/run/JSON/gcov, không giả hardware evidence |
| `tools/test_phase4_device.py` | Bài test COM5 + native broker subscriber, input có kiểm soát, broker recovery, retain và capture/results; secrets timeout redacted, subscriber cleanup theo unique client ID/PID |
| `docs/PHASE8_2_4_STATUS_TEST_ALERT.md` | Kiến trúc, semantics, payload examples, safety/failure limits, build/flash/manual test và bằng chứng |
| `docs/PHASE8_2_3_MQTT_MANAGER.md`, progress này | Liên kết implementation Phase 4, trạng thái và next phase |
| Ignored `main/network_config.local.h` | Bật `NETWORK_TEST_ALERT_SERIAL_ENABLED=1` riêng cho hardware demo; credentials vẫn ignored, không in/chat/commit |

Thiết kế: status QoS 1/retained sau SUBACK/reconnect, mỗi 10 s hoặc LEDC state
thay đổi. `mode=REAL`, `lteReady=false`; alertState là output driver BUZZER_ON/
IDLE, không phải full fall state machine; read failure trả null. Không có UTC
trusted thì timestamps null; không dùng PC/build time, uptime hoặc self-test
GNSS làm UTC. CURRENT/LAST_KNOWN chỉ lấy từ snapshot thật đã kiểm tra bounds.
`modelVersion=firmware-test-v1` định danh generator test, confidence=null.

TEST_ALERT chỉ từ exact local serial command khi opt-in/MQTT ready, cooldown
5 s; một payload pending, UUID v4 mới mỗi yêu cầu được chấp nhận. Không tự phát
khi boot, button, CSV synthetic hoặc reconnect; offline request không replay.
Retry application queue tối đa ba lần/1 s, cùng UUID/payload; connection epoch
thay đổi sẽ hủy pending trước enqueue. Queue accepted không đồng nghĩa delivery;
transport publish failures được log, không có per-event delivery receipt hoặc
durable offline storage. SDK QoS 1 vẫn có thể retransmit; Backend phải dedup.
Không thao tác buzzer/motor từ TEST_ALERT, không command ACK/call/SMS/115.

| Kiểm tra | Kết quả thực tế / artifact |
| --- | --- |
| TDD | Host test trước source RED (missing module), sau implementation GREEN; giữ retry payload/UUID, UTC stale/future/range, status/location/serial invalid/overflow/binary/cooldown/init failure |
| Host publisher | 16/16 scenario PASS, source line coverage 96,18%; `build/phase8_2_4/tests_verified.log`, `host_tests/results.json`, hardware_verified=false |
| MQTT regression | 22/22 PASS, coverage 99,58%; `build/phase8_2_4/mqtt_regression.log`; MQTT Manager source không đổi |
| Build | ESP-IDF v5.5.5 PASS exit 0, ccache off/Ninja -j1; `build/phase8_2_4/build.log`; không compiler diagnostic lỗi; warning partition gần đầy và CMake không lấy được Git describe do sandbox ownership, không đổi global Git config |
| Size/identity | App 1.028.736 byte (`0xfb280`), còn 19.840 byte (`0x4d80`, 2%); ELF SHA-256 `69846A2B891DF31DD4FF7A36EE15E34A1E174434FD56D54D1DF8359E0D8742B3`; BIN `FD593503AB1751D716F3EA432F76D16CF96D7786AE657AEC6AA845D6F1B3CB38` |
| Flash | COM5 PASS, esptool hash verified; runtime prefix `69846a2b8` khớp; `build/phase8_2_4/flash.log` |
| First hardware run | 102,28 s, hai TEST_ALERT, 13 status frames, reconnect/retained online PASS; 19 diag windows không lỗi sampling; CSV 4.000 rows CRC `34871B79`; `hardware/` |
| Final hardware retest | 102,59 s, hai TEST_ALERT/hai UUID riêng, 12 status frames gồm retained/live; kiểm tra event không retained **trước** broker restart PASS, input sai/cooldown/offline request không sinh thêm event; status online được gửi lại sau reconnect; `hardware_retest/results.json` |
| Actual payload/transport | `mode=REAL`, lteReady=false, status LEDC BUZZER_ON rồi IDLE; hai event TEST_ALERT/isTest=true, occurredAt=null/confidence=null/location UNAVAILABLE null fields. Broker log xác nhận device PUBLISH event q1/r0, status q1/r1 và PUBACK; `hardware_retest/mqtt_frames.json`, `broker_final.log`, `additional_verification.json` |
| Final sensor regression | 19 diag windows, seq/ok 9.508/9.508; missed_ticks/IMU/BMP error/outlier/diag_dropped đều 0, gaps 9.689–10.295 us; không panic/brownout/watchdog/reset bất thường |
| Final CSV | Extractor PASS 4.000 rows, CRC32 `1C4EF049`; `hardware_retest/runtime_capture/` |
| Safety/preservation | Hash GNSS/LTE/Wi-Fi/MQTT/sensor source, sdkconfig và contract giữ nguyên; buzzer boot diagnostic vẫn độc lập, không test command execution. GNSS no-fix, LTE UART disabled/no AT/OFFLINE_UNVERIFIED |
| Test harness cleanup | Script ban đầu kill Docker CLI còn để lại subscriber; đã dọn đúng PID test, sửa PID/client-ID checked cleanup + native deadline, retest xong `docker top` chỉ còn server Mosquitto; COM5 được giải phóng |
| Security/format | Timeout credential redaction fault-injection PASS; config local/build vẫn Git ignored; kiểm tra secrets/diff trước kết thúc, không commit/push/merge |

Final raw capture SHA-256:
`573d0a739f7b21601aadcda2d235c60d3ab086bbfab65ce7117063a8c643fb29`.
Hardware artifacts dưới ignored `build/phase8_2_4/hardware_retest/`; first run
giữ tại `hardware/`. Retest sửa độ chặt của harness, không sửa/reflash firmware.
Các log/parser fixture không thay hardware evidence hoặc Backend integration.

Chưa xác minh: GNSS fix/UTC/CURRENT/LAST_KNOWN ngoài trời, TLS, Backend strict
DTO/nullability/persistence/App và việc downstream phân luồng test, heap/resource
fault campaign, long soak, real STOP_BUZZER/ACK. Không coi driver duty là chứng
nhận âm thanh, không coi queued/PUBACK là command execution. Demo broker riêng
không tích hợp cứu hộ thật. Local serial demo vẫn enabled trong binary trên board;
muốn tắt phải đặt macro 0 và build/flash theo tài liệu.

**Phase 8.2.4: PASS.** Phase được phép kế tiếp: **8.2.5**, chỉ khi có lệnh
`làm phase 5`; ACK/expiry semantics cần thống nhất, budget flash chỉ còn 2%.
Không tự triển khai tiếp, không commit/push/merge; broker LAN vẫn running.

## 26. Phase 8.2.5 PASS — STOP_BUZZER & Real ACK — 2026-10-31

Theo lệnh Phase 5, đã đọc plan/progress/contract/source thật, bảo toàn working
tree có sẵn. Contract gốc chỉ có mock ACK và thiếu TTL; người dùng chấp thuận:
"Dùng đề xuất cho demo firmware; ghi rõ Backend cần đồng bộ". Đề xuất cụ thể là
status.lastCommand commandId/eventId/command/result/reason/processedAt, results
EXECUTED/REJECTED/FAILED, TTL 30 s, skew tương lai 5 s, thiếu UTC từ chối, dedup
RAM 16 lệnh, UUID event mới sau reboot, STOP chỉ tắt còi/giữ event. Phụ lục demo
đã được liên kết từ contract; không suy ra Member 3/production đã đồng bộ.

| File sửa/tạo | Mục đích |
| --- | --- |
| `main/command_processor.c/.h` | Flat JSON parser có cap/depth/schema/ID/date validation, demo context, TTL/epoch/state checks, cache 16, ACK sau checked execution và local auto-off |
| `main/device_clock.c/.h` | Real SNTP UTC/monotonic anchor tối đa 1 h hoặc current GNSS fix tối đa 5 s; không hard-code/set UTC từ test |
| `main/alert_manager.c/.h` | Thêm checked on/off với init/error guard, chờ PWM update và readback; fallback best-effort không biến failure thành success; giữ void APIs/diagnostic/mapping |
| `main/device_telemetry.c/.h` | Consume command ở worker, ghép ACK vào full status/heartbeat/reconnect, serial TEST_ALERT_BUZZER opt-in; plain TEST_ALERT giữ nguyên; stack 8.192 byte/high-water logging |
| `main/app_main.c`, `main/CMakeLists.txt` | Register modules/json SDK; init clock trước acquisition khi Wi-Fi chuẩn bị thành công; không đưa logic blocking vào sensor/callback |
| `main/network_config.h`, `.example.h` | Commands default 0/NTP server config; demo cần opt-in local |
| `sdkconfig` | App vượt 1 MB thực tế; chọn ESP-IDF single_app_large 1.500 KiB, giữ NVS/PHY/app offsets và flash size |
| `tests/command_processor/*`, `tests/device_clock/*`, `tests/buzzer_checked/*` | Actual source với fake driver/network boundaries, cJSON dùng code SDK thật, parser/state/failure/time/readback tests |
| `tools/test_command_processor.py`, `test_device_clock.py`, `test_buzzer_checked.py` | Host runners, coverage parser/processor và fault tests |
| `tests/device_telemetry/host_sdk.h`, `host_test.c` | Thêm fake boundaries cho command/clock disabled để giữ regression Phase 4 và kiểm tra source thật hiện tại |
| `tools/test_phase5_device.py` | Real COM5/native broker suite, hai buzzer arms, negative/cached/replay/ACK/reconnect/CSV và bounded subscriber cleanup; không tự xác nhận âm thanh |
| `docs/PHASE8_2_5_DEMO_COMMAND_CONTRACT.md`, `PHASE8_2_5_STOP_BUZZER_REAL_ACK.md` | Profile đã được người dùng duyệt, authorization/delivery limits và handoff/build/test thực tế |
| `docs/DEVICE_BACKEND_CONTRACT.md`, master plan, Phase 4 doc, progress | Link phụ lục demo, giữ mock contract riêng, trạng thái/evidence/next phase |
| Ignored `main/network_config.local.h` | Enable demo commands + serial test, chọn IPv4 NTP đã xác minh; không thay/in credentials |

Worker priority 2/core 0 là owner của processor/actuator commands; MQTT callback
chỉ đưa raw frame vào queue. Parser nhận đúng bốn string, ≤512 byte, không extra/
duplicate key, escaped/NUL/binary/nested value; topic exact/device ACL ràng buộc
target. Validation UTC/TTL/epoch/active UUID/LEDC state trước stop. Cache duplicate
trả original result/processedAt không thực thi lại; cùng ID khác payload bị từ
chối. Dedup chỉ 16 entry/RAM, không hứa persistent/exactly-once. Cached success
cho event cũ không chứng minh còi của event mới đã dừng. STOP không clear UUID/
cancel event/motor/alert workflow. Demo arm local qua serial, không remote START.

| Kiểm tra | Kết quả / artifact dưới `build/phase8_2_5/` |
| --- | --- |
| Command TDD | RED missing module trước implementation; GREEN real parser/processor source + bundled cJSON, coverage 99,25%; invalid schema/calendar/epoch/TTL/skew/clock/context/state, duplicate/collision/cache capacity, failure và timeout cases; `tests_green.log`, `host_tests/results.json` |
| Checked actuator | Actual alert_manager.c APIs với fake LEDC failures PASS; init/set/update/readback/stuck/fallback không ACK success giả; `buzzer_tests.log` |
| Clock | Init failure/invalid server/invalid response/real-callback anchor semantics/holdover expiry/fresh GNSS fallback host PASS; `clock_tests.log` |
| Regression | Publisher 16/16 PASS, source coverage 89,17% (`telemetry_verified.log`); MQTT 22/22/99,58% (`mqtt_regression.log`) |
| Initial app budget | Build fail: app `0x100560` > 1 MB, overflow `0x560` = 1.376 bytes; `build_initial_overflow.log` |
| Partition change | Preset factory 1.024→1.500 KiB, app offset 0x10000, NVS 0x9000/24K và PHY 0xf000/4K không đổi; `partition_before.csv`, `partition_after.csv`; không erase-all/custom filesystem/OTA changes |
| Final build/flash | ESP-IDF v5.5.5 ccache off/Ninja -j1 PASS exit 0, COM5 hash verified; `build.log`, `flash.log`; không compiler error/warning hoặc size warning cuối; CMake Git describe ownership sandbox warning không sửa global Git config |
| Final size/hash | App 1.050.304 byte (`0x1006c0`), free 485.696 (`0x76940`, 32%); ELF `890D4BB95752ECCA86CEB5B3AADA0C8C807BDCDD08BD4817E83C692946261725`, BIN `747E85F45BA18C3345154B55642CAD3D8D4A982B02D3093D98BD3D2833AD718E`; runtime prefix `890d4bb95` |
| Missing-clock real test | Hostname NTP chưa sync sau 100 s; native probe command được ESP32 từ chối REJECTED/CLOCK_UNAVAILABLE/processedAt=null; `hardware_test.log`, `hardware/`, `clock_unavailable_status.log`; không bật còi test hoặc gửi success giả |
| NTP path | Laptop nhận response thật từ 3 public servers; sau đổi riêng local server sang IPv4 đã DNS/response-verify, ESP32 UTC sync PASS; `ntp_public_probe.json`. Chưa kết luận root cause DNS/peer/network, không set giờ giả/bỏ TTL |
| Final hardware suite | 100,17 s; `hardware_ipv4/results.json`, `mqtt_frames.json`, `runtime.log`, `additional_verification.json`; hai TEST_ALERT_BUZZER + một plain TEST_ALERT, cả ba isTest=true, không auto event boot/reconnect |
| Two real stops | Arm uptime 12.090/28.500 ms; STOP verified off 19.380/32.260 ms; ACK enqueue/actual subscriber sau driver success; **chỉ hai** actuator executions dù nhận lại cached EXECUTED ACK nhiều lần; không auto-timeout trong run thay cho command |
| Negative hardware cases | Extra-target/malformed không thực thi; EXPIRED/FUTURE_ISSUED_AT/EVENT_NOT_ACTIVE/UNSUPPORTED_COMMAND/COMMAND_ID_REUSED/NOT_BUZZING bị từ chối, giữ đúng output state; duplicate và old-event replay không tắt còi new event; new valid command mới tắt |
| Correlation/reconnect | commandIds `0fd30c9c-024d-4fbf-b5b0-47189c415d44`, `74513d67-e380-4c72-b40d-ce28733723aa`; eventId/processedAt đúng/cached stable; reconnect giữ dedup/lastCommand và không phát event phụ |
| Acoustic verification | Người dùng xác nhận: "Có, nghe hai lượt còi bật rồi dừng"; lưu `hardware_ipv4/acoustic_confirmation.json`; results đánh dấu USER_CONFIRMED, không lấy mock hoặc driver thay cho nghe thật |
| Sensor regression | 19 diag windows, seq/ok 9.506/9.506, missed_ticks/IMU/BMP error/outlier/diag_dropped đều 0, gaps 8.332–11.689 us; worker minimum free stack 3.500 bytes; không panic/brownout/watchdog/reset bất thường |
| CSV | Extractor PASS 4.000 rows, CRC32 `C3E22E3D`; `hardware_ipv4/runtime_capture/` |
| Safety/preservation | Hash sensor/Wi-Fi/MQTT/GNSS/LTE source giữ nguyên; GNSS self-test/parser chạy/no-fix; LTE UART disabled/no AT/OFFLINE_UNVERIFIED; không call/SMS/rescue |
| Cleanup | COM5 đóng, Docker top chỉ còn Mosquitto server, broker bind riêng IP LAN laptop; không commit/push/merge |

Final raw SHA-256:
`88d3699ad57d17ccd823a8b096287ca2aac26a3f846f433298f922a193f42313`.
Artifact trước IPv4 được giữ làm evidence attempt chưa sync, không coi đó là
PASS. New source/credentials scan và diff được kiểm tra trước chốt phase.

Chưa xác minh: Member 3/Backend/App adoption, production TLS/per-user authorization/
secure time, dedup bền vững qua reboot, long soak/heap/resource fault campaign,
GNSS fix và hardware auto-off 30 s khi mất mạng (logic/driver failure đã host-test).
MQTT 3.1.1 live retain intent không phân biệt được từ delivery r0; Backend bắt
buộc retain=false, không coi retain filter là authorization. ACK transport có
thể mất khi reset/outbox failure; không hứa durable per-command history.

**Phase 8.2.5: PASS cho profile demo đã được người dùng chấp thuận.** Phase tiếp
theo là **8.2.6 — Reliability & Regression**, chỉ khi có lệnh `làm phase 6`.
Không chuyển phase, không commit/push/merge. Binary trên board bật local serial/
command demo; muốn tắt cần sửa local flags về 0 và build/flash theo tài liệu.

## 27. Phase 8.2.6 — reliability campaign — PASS demo — 2026-10-31

Đã đọc context, giữ contract/profile demo Phase 5. **Kết quả cuối: PASS cho
profile demo được đo ở phần chốt bên dưới.** Các đoạn IN_PROGRESS/chưa PASS
trong diễn biến sau là lịch sử thử nghiệm: baseline dài chưa đủ vì fault Wi-Fi
đã phát hiện lỗi cần sửa/xác minh. Không xóa hoặc đổi kết quả capture lỗi.

- Thêm resource logs heap/task/stack, MQTT queue/outbox/counters mỗi 10 s; local
  TEST_MOTOR 500 ms với auto-off và interlock còi, TEST_PUBLISH_OFFLINE. Không đổi
  timer/counters/threshold sensor, GNSS parser, GPIO/UART hoặc LTE mode.
- Host RED/GREEN motor case; publisher 18/18/92,22%, MQTT 22/22/99,59%, command
  parser 99,25%, clock/checked actuator tests PASS. Wi-Fi 30-case baseline PASS.
- Build/COM5 flash baseline PASS. ELF
  `4FA252585532CE28CB0E7F935DCE4A69D2168F7B1E4F826599FE8156C1F3FD6D`.
  `build/phase8_2_6/campaign/`: 1.042,64 s (17m22s), 207 sensor windows, 0 missed/
  outlier/error/reset bất thường, gap 9.212–10.806 us; CSV 4.000/CRC `A4759656`.
  Boot broker offline >60 s, hai offline publish rejections thật, broker recovery
  và restart/cached duplicate ACK PASS; queue burst 32 → received 7/drop 25, drain
  về 0. Heap tail về 190.679 bytes internal, tasks 16, stack telemetry 3.316/MQTT
  2.956 bytes free. Snapshot/log chỉ chứng minh workload và thời lượng đã đo.
- User đã giữ button và nhả/bấm nhiều lượt; GPIO idle0→held1 đủ debounce, confirms
  active-high thực tế. Motor rung 500 ms rồi dừng được user xác nhận. Auto-off
  còi khi broker offline khoảng30 s được user xác nhận. Không tạo event từ button/
  motor. Người dùng **chưa thể tắt/bật AP AP_DEMO**, không ghi AP outage test PASS.
- Để đo Wi-Fi mà không cần AP control, thêm API task-only
  wifi_manager_test_disconnect và serial TEST_WIFI_DROP (demo opt-in). Worker/
  callback/backoff có sẵn xử lý disconnect thật, không giả event, không reset ESP.
  Host RED thiếu API, GREEN Wi-Fi 31/31/98,68% với local-drop recovery case.
- Binary diagnostic ELF
  `9E93ED46155D1F35A4AAAE9C3E424BF820A5E17F3EC42B66102D4B87D0F3F1D4`:
  `wifi_fault/` nhận SDK disconnect reason8, GOT_IP lại rồi **TG1WDT_SYS_RST** trước
  MQTT recovery. Không Guru register dump; Saved PC0x4038d4de giải ra
  _xt_context_save:159, chưa đủ root cause. Giữ nguyên raw/hash/failure_record.json.
- `wifi_repro/` cùng binary: reconnect/SUBACK được nhưng 1 missed tick, 4 outlier,
  gap 4.313–17.777 us; cũng FAIL regression, không dùng để đánh PASS.
- Xác định cấu hình TCP/IP không pin core (priority cao hơn Sensor Task) và SDK
  MQTT task không pin core; đang build thay đổi affinity cả hai sang core0 để
  cô lập network khỏi acquisition core1. Đây là fix cần kiểm thử, chưa kết luận
  giải thích watchdog. Không tắt/kéo dài watchdog, đổi ISR stack hoặc hạ ngưỡng
  sensor; không sửa SDK. Config trước lưu sdkconfig.before_network_pin.

Files đang đổi/tạo: device_telemetry.c, mqtt_manager.c, wifi_manager.c/.h,
sdkconfig (network affinity), tests/runner Wi-Fi/MQTT/telemetry; tools
phase6_capture.py, phase6_command_probe.py, analyze_phase6_capture.py và
docs/PHASE8_2_6_RELIABILITY_REGRESSION.md. Artifact dưới ignored build/phase8_2_6.
Không commit/push/merge, không sang Phase 7. Cần build/flash và lặp fault/capture
sau fix; nếu vẫn watchdog phải lấy thêm diagnostic evidence, không báo đã sửa.

Cập nhật tiếp trong cùng lượt: pin network-only ELF
`FBBA40C9B03980608048270F969D7BB87C8281D0119F3A959D36854BC7538C85` build/flash
PASS nhưng **network_pinned/** FAIL sau cycle2: 2 missed tick, 10 outlier, gap
3.382–25.758 us; không reset trong run đó. Không chốt pinning là fix hoàn chỉnh.
SDK I2C cấp interrupt trên core khởi tạo, app_main đang tạo bus core0 trong khi
Sensor Task core1; BMP read latency trong fault tới 9.393 us. Đang thử helper
boot-only `sensor_bus.c/.h` cấp I2C IRQ core1 (config/bus/GPIO/clock giữ nguyên),
Task boot chờ kết quả trước khi sensor timer tồn tại. Host RED missing module →
GREEN core1 allocation/error propagation; chưa lấy đó làm hardware PASS.

Candidate IRQ core1 + network core0 ELF
`47024CA94FEF5457168B735E662F3C9852C23ACB4B836238AFD4AA249D917649`
build/flash PASS nhưng **irq_core1/** FAIL: 208,66 s, hai cycle đầu phục hồi sạch,
cycle3 có 2 outlier (gap 3.394–17.416 us), rồi Cache error/MMU entry fault và
reboot. Raw SHA-256
`55df169b52e1d9233f2ce0e401a2f8dbe33879f5183a6e9e2d129e5ddb1fda1a`.
ELF/bin/sdkconfig tương ứng lưu `candidate_irq_core1/`; backtrace giải mã bằng
đúng ELF: esp_vfs_select → esp_tls TCP connect → esp_transport_connect →
esp_mqtt_task trên core0; core1 đang idle. Đây là vị trí xảy ra lỗi, chưa chứng
minh VFS/TCP hay I2C là nguyên nhân gốc. Không kết luận helper đã sửa xong lỗi.

Lượt tiếp theo thử riêng `esp_wifi_set_ps(WIFI_PS_NONE)` trước radio start để
đo ảnh hưởng modem-sleep lên latency/reconnect. Có tăng điện năng radio, chỉ là
profile demo cần đo, chưa hứa phù hợp pin. Host RED yêu cầu cấu hình PS trước
start, GREEN 32/32, coverage98,70% kể cả failure của API mới. Không thay watchdog,
sensor period/threshold, SDK, GPIO/UART hoặc contract. Chưa PASS phần cứng.

Candidate không modem-sleep build/flash exit0, app1.052.816 byte/31% partition
free. Docker Engine ban đầu không chạy; đã mở lại Docker Desktop và start đúng
container demo, IP LAN192.168.0.3 không đổi. `no_modem_sleep/` vì vậy thực sự boot
với broker offline >60 s rồi nhận SUBACK, không dùng mock. Interim sau cycle5
(369,73 s): tất cả recovery thành công, missed/outlier/sensor error=0. Một STOP
thật sau Wi-Fi recovery trả EXECUTED/STOPPED và duplicate trả processedAt cũ,
không gọi actuator lại; burst32 invalid frame được gửi để đo bounded RX.
CSV extractor PASS4.000 rows/CRC32 `079119B5`. Các suite host liên quan đã chạy
lại PASS; actual-password scan82 file source/docs/tools/tests và tracked diff
không có match, private header/broker secrets vẫn ignored. Hash sensor/GNSS/
LTE/actuator/command/clock sources giữ nguyên so với đầu Phase6. Campaign còn
đang chạy; các con số interim không phải nghiệm thu cuối.

### Chốt Phase 8.2.6

Profile cuối giữ TCP/IP và SDK MQTT core0, Sensor Task/esp_timer task và I2C IRQ
core1 (timer ISR vẫn core0, không đổi);
đặt Wi-Fi `WIFI_PS_NONE` trước start. Nguồn sensor/GNSS/LTE/actuator/command/
clock giữ nguyên hash so với đầu Phase6; app_main/CMake chỉ thêm boot bus helper.
Không sửa SDK, tăng/tắt watchdog, thay ngưỡng/counters sensor hoặc GPIO/UART.
Modem awake là profile demo tăng điện năng, chưa đo battery budget. Bản trước
fault vẫn được giữ; chưa chứng minh nguyên nhân gốc watchdog/cache fault.

| Kiểm tra cuối | Bằng chứng / kết quả thực tế |
| --- | --- |
| Build/flash | ESP-IDF5.5.5 exit0/COM5 hash verified, không compiler warning/error mới; app1.052.816 bytes, partition còn483.184 bytes/31%; `build.log`, `flash.log` |
| Image cuối | ELF `1840D338D7E9CE71521986A6AB15A5552CFAAE18600A3A722F9F664AE82A7A51`; BIN `CA47D2D43CD4EBF629A920030F522145BC9ED75C0DD6634E907EC2A68BFA7AD8`; bản lưu `candidate_no_modem_sleep/` |
| Final profile runtime | `no_modem_sleep/`: **1.000,19 s**,199 sensor windows, seq/ok99.603/99.603, 0 missed/outlier/IMU/BMP error/diag drop, gaps9.923–10.085 us; reset_count1 là reset chủ động lúc bắt đầu, không fatal/reset bất thường |
| Wi-Fi recovery | **8 SDK disconnect thực tế**, 9 GOT_IP, MQTT trở lại mỗi lượt; recovery khoảng6–10,2 s gồm SDK MQTT retry5 s; `wifi_cycles_summary.json`, raw/actions |
| Lỗi điều phối test | Lịch cycle8 trùng control motor của người vận hành nên không có SDK drop ở thời điểm đó; giữ nguyên FAIL timeout ở `wifi_cycles_first7.json`/log. Đã chạy lại riêng một cycle thành công cùng capture, không reset. Tổng8 là7+1 được raw/actions xác nhận; không biến timeout thành firmware PASS |
| MQTT/broker | 10 SUBACK gồm Wi-Fi recovery và broker recovery; boot broker unavailable >60 s; cuối run stop/start broker thêm khoảng94 s; không tạo event tự động/reconnect |
| STOP/dedup | Một STOP thật cho event05b75d85-8de8-4f1a-b3e2-adc6c18b9810, command b2323118-4673-4275-9ecd-5ecc3b5e00d7 trả EXECUTED/STOPPED. Duplicate trước/sau broker restart giữ processedAt, tổng actuator executions vẫn1 |
| Failsafe | Arm682.551ms→off712.621ms (**30,070 s**) khi broker offline, off_result0/event retained/không ACK command mới. Sau broker recovery lệnh mới trả REJECTED/NOT_BUZZING; `after_timeout_final.json` |
| Publish/queues | Hai offline API rejections thật; burst32 invalid frames, RX drop28, queues drain0/4 và không actuator/event thêm; SDK-full/fault cases host verified riêng |
| Resources bản cuối | 100 heap samples; free_internal tail190.311, minimum lifetime140.984, largest110.592 bytes; task tail16; free worker stack telemetry3.400/MQTT2.952 bytes. Min5 sample steady đầu190.303→cuối190.311 (+8 bytes), chưa thấy leak theo workload/thời lượng đã đo |
| Events/CSV | 2 TEST_ALERT/isTest=true, 2 UUID đúng 2 yêu cầu local, không unrequested UUID; final CSV4.000 rows/CRC32 `079119B5`, `no_modem_sleep/final_csv/` |
| Motor/button/manual | Bản cuối motor requestedON601.441→OFF601.941ms. Xác nhận rung/còi/button vật lý dùng `campaign/manual_evidence.json` từ baseline ELF4fa252585, source actuator/button behavior được bảo toàn. Không gán button presses của run cũ cho final profile (run cuối button_presses0) |
| GNSS/LTE | GNSS live NMEA/parser và selftest chạy, vẫn no-fix; LTE UART disabled/no AT/OFFLINE_UNVERIFIED |
| Host | Wi-Fi32/32/98,70%; MQTT22/22/99,59%; telemetry18/18/91,26%; command99,25%; clock, checked buzzer, sensor bus helper PASS; host không thay hardware evidence |
| Tổng hợp | `final_verification.log`, `campaign/verification.json`: **27/27 checks PASS**, raw SHA của cả hai capture được xác minh sau khi đóng recorder; `final_evidence_manifest.json` phân biệt hai image/run |
| Preservation/security | 82 source/docs/tools/tests files + tracked diff không chứa actual passwords; local credentials và private broker secrets ignored; `secrets_review.json`, `preservation_latest.json`; diff --check PASS (Git chỉ nhắc LF→CRLF của .gitignore có sẵn) |
| Cleanup | Recorder exit0, COM5 đóng; Docker process list chỉ còn Mosquitto server, broker online/bind192.168.0.3:1883; không commit/push/merge |

Final raw SHA-256:
`33a3d6c280740aefd7ea296c735a15b9eca1e2a900f9a120f1f85ca445cdd731`.
Baseline raw SHA-256:
`410eef330035ad3e79b0da0ffefc860b958934382002a5ed56b88867227f9bba`.
Đây là **hai capture/image riêng**, không phải35 phút liên tục trên cùng binary.
Files Phase6 và lệnh đo lại trong [reliability report](PHASE8_2_6_RELIABILITY_REGRESSION.md).

Chưa xác minh: tắt/bật AP AP_DEMO thật trong lượt này (user chưa thao tác được),
RF yếu/roaming, soak24 giờ, battery/power profile, production TLS/security,
Backend/App thật, GNSS outdoor fix và LTE data/MQTT. Station disconnect trên
board là hardware test thật nhưng không thay cho bài AP mất nguồn ≥60 s.
Không khẳng định modem-sleep là nguyên nhân gốc của reset cũ; kết quả PASS chỉ
áp dụng profile cuối và workload đã ghi. Khi thay SDK/power/core configuration
cần chạy lại network/sensor regression.

**Phase 8.2.6: PASS cho demo đã đo.** Phase tiếp theo được yêu cầu là
**8.2.7 — End-to-End Integration** (`làm phase 7`); cần Backend/App/Member3 thực
tế và đồng bộ command/ACK profile demo. Chưa triển khai Phase7, không tự chuyển
phase hoặc commit/push/merge.

## 28. Phase 8.2.7 — E2E preparation / BLOCKED — 2026-10-31

Lệnh người dùng: `làm phase 7`. Đã load master/progress/contracts/source liên
quan, kiểm tra Git main/HEADdae70f6 và bảo toàn dirty tree. Phase1–6 đã có bằng
chứng prerequisite, giữ nguyên image demo Phase6. Người dùng xác nhận:
**"Chưa có Backend/App — chuẩn bị bộ test và tài liệu cho Member3"**.

Đã kiểm tra cấu trúc source trong firmware và metadata C:\Workspace: không có
Backend/Web/Android Fall Detection. Docker có Mosquitto demo và ứng dụng đấu giá
OnlineBidFlowSystem; không nhầm auction_backend/cổng8080 hoặc MySQL của dự án
đó với Spring Boot/PostgreSQL Fall Detection. Không đọc/sửa Backend khác, không
tự tạo Backend/API/mock thay thế. Chưa có revision/source/URL để test App thật.

| Điểm kiểm thử | Kết quả / evidence dưới `build/phase8_2_7/` |
| --- | --- |
| Broker endpoint | Host TCP192.168.0.3:1883 reachable, Docker bind đúng IP riêng; auth required, per-device ACL, Mosquitto2.1.2; `environment_audit.json` |
| Auth/ACL thực | Anonymous CONNACK135; device publish command và backend publish status bị Denied PUBLISH/PUBACK135. CLI exit0 ở hai publish probe không đủ verdict, giữ `acl_probes_cli_inconclusive.json`; kết quả dựa broker log/clientID ở `acl_probes.json`, `acl_broker_evidence.log` |
| Recorder | Shared Phase6 recorder thêm opt-in --observe-command, native subscriber chỉ read status/event/command; broker log xác nhận3 subscriptions; không phát MQTT command/STOP hoặc giả App/Backend |
| Status thật | `device_broker/` capture COM5 reset có kiểm soát, boot ELF1840d338d, GOT_IP/CONNACK/SUBACK, status REAL live/lteReadyfalse; không dùng retained cũ làm fresh evidence |
| Test event thật | Một plain TEST_ALERT local, isTesttrue/modelVersionfirmware-test-v1/confidencenull/locationUNAVAILABLE; eventId `b7e84db8-da12-47e3-b912-00e396e99330`, occurredAt2026-10-31T12:00:25Z; không arm còi alert, call/SMS/cứu hộ |
| Sensor/CSV | 130,28s/25 windows, seq/ok12.514/12.514, missed/outlier/IMU/BMP error/diagdrop0, gaps9.948–10.051us; reset_count1 là reset lúc start, không fatal/collector error. CSV4.000 rows/CRC32 `6F3A56A0` |
| Command leg trong Phase7 | NOT_OBSERVED, không có command hợp lệ vì Backend/App chưa có; optional --require-command trả exit1 đúng. Evidence STOP/ACK Phase5/6 không thay cho App→Backend flow Phase7 |
| New checker | Host RED missing module→GREEN, thêm RED/GREEN boot ELF whitespace theo log thật; 10 tests PASS, trace104/107 executable lines (97,20%); `host_results.json`, `host_tests.log`. Fake fixtures không phải hardware/E2E |
| Broker-leg verdict | `device_broker/phase7_broker_leg.json`: device_to_brokerPASS; mọi backend_receive/persistence/app/ack_ui/end_to_end vẫn NOT_VERIFIED kể cả khi broker-leg đạt |
| Backend/App/DB | NOT_TESTED, chưa có hệ thống. Member3 chưa xác minh adoption ACK/TTL profile, isTest rescue guard, subscription/schema/persistence/event dedup/App display, auth request routing hoặc ACK UI |
| Build/flash | Không cần/thực hiện vì firmware không sửa. Hash29 source/config files và contract giữ nguyên; `preservation.json`, snapshot/contract.before. Không reset/flash để sửa code, chỉ một reset lúc recorder start |
| Cleanup | Recorder exit0/COM5 đóng, Docker top chỉ còn Mosquitto server, broker vẫn online; không đụng application khác/không commit/push/merge |
| Security/diff | Scan86 source/docs/tools/tests files + tracked diff không có actual password match; local header/private broker secrets vẫn ignored. Python syntax/JSON template/diff --check PASS; nhắc LF→CRLF của .gitignore có sẵn, không phải compiler lỗi |

Raw SHA-256:
`f2a45dc587449654acea5e191e9fff842af379c45629f3daa812210e3042d385`.
Mẫu index đã điền **chỉ chặng thực sự đo** ở `build/phase8_2_7/e2e_evidence.json`;
các stage Backend/App NOT_TESTED, reviewer/revision còn null. JSON tự điền
không là chứng nhận E2E. Broker probes dùng payload{} vô hại và bị ACL chặn;
không phát FALL_CONFIRMED hoặc valid STOP bằng native client thay Member3.

Files tạo/sửa Phase7:

- `tools/phase6_capture.py`: flag observe-command mặc địnhfalse, giữ hành vi cũ.
- `tools/phase7_check_capture.py`: mới, offline checks/same-ID command ACK,
  không đưa ra E2E PASS hoặc tự gọi API/network.
- `tests/test_phase7_capture.py`: mới, rejection/correlation/CLI guards.
- `docs/PHASE8_2_7_END_TO_END_INTEGRATION.md`: mới, môi trường/broker, command/
  ACK pitfalls, checklist từng chặng và lệnh PowerShell cho Member3.
- `docs/PHASE8_2_7_E2E_EVIDENCE_TEMPLATE.json`: mới, template trống để copy từng
  run vào ignored build, không chứa secrets/kết quả giả.
- `docs/APP_WEB_HANDOFF.md`: thêm pointer tới real-device/profile demo, phân
  biệt phần mock Phase8.1 cũ.
- `docs/PHASE8_2_PROGRESS.md`: mục28/trạng thái/dependency.

**Phase 8.2.7: BLOCKED cho nghiệm thu E2E** do thiếu Backend/App theo xác nhận
người dùng; phần chuẩn bị/test độc lập khả thi hoàn tất. Để tiếp tục Phase7,
cần Member3 cung cấp Backend/App thật, source/revision hoặc URL demo, endpoint/
auth local và evidence isTest guard + adoption ACK profile. Sau đó chạy luồng
hai chiều theo [test plan](PHASE8_2_7_END_TO_END_INTEGRATION.md), không dùng mock
hoặc direct MQTT probe làm App/Backend proof. Phase8.2.8 chưa triển khai; chỉ
thực hiện khi có lệnh riêng và phải giữ rõ tình trạng E2E chưa PASS nếu còn thiếu.

## 29. Chuẩn bị commit trước khi nhận nhánh AI — 2026-11-01

Theo yêu cầu người dùng, đã phân loại working tree để giữ source/tài liệu cần
commit và tách local artifacts. Đây là công việc chuẩn bị Git riêng, không tự
triển khai Phase8.2.8, tích hợp AI hoặc đổi trạng thái nghiệm thu các phase.
Nhánh vẫn `main`, HEADdae70f6; chưa stage/commit/pull/switch/push/merge.

- Giữ toàn bộ source/config/module mới, CMake/sdkconfig, host tests/runners,
  tools, tài liệu diagnostic/phase/contract và AGENTS. Các fake SDK headers là
  dependency của test, không phải rác. Các sample đã tracked trong docs giữ nguyên.
- `.gitignore` thêm raw captures, root Serial logs/verified CSV TXT và
  local_artifacts. Private network header/build/machine settings vẫn ignored.
- Giữ2 CSV/metadata trong captures tại chỗ, đúng hash cũ; đây là recording thật
  unknown ground truth, không xóa hoặc đổi thành dữ liệu ngã có nhãn.
- Chuyển7 root Serial logs + sensor_csv_verified_4000.txt + sdkconfig.old vào
  ignored `local_artifacts/pre_ai_merge_20261101/` (serial_logs/config_backup).
  Tổng9 file/3.199.610 bytes, SHA-256 trước/sau khớp. Tài liệu audit lịch sử vẫn
  giữ tên/vị trí log ở thời điểm test; tìm bản gốc qua moved_evidence_manifest.
- Sao lưu100 file source/docs/config/captures vào working_tree dưới cùng
  archive, có manifest SHA-256. Không có .git/build/private network header trong
  backup này. Build vẫn giữ nguyên vì chứa evidence/ELF/broker secrets đang dùng.
- Ẩn tên SSID thật thành nhãn AP_DEMO trong4 tài liệu (5 chỗ); bản tài liệu gốc
  còn trong archive. Không đổi numeric outcome, checksum, UUID hoặc trạng thái.
- Hash41 file firmware/config/Bosch/captures không thay đổi, không sửa/xóa source
  hoặc dữ liệu. Chỉ điều chỉnh ignore/docs và vị trí local evidence trong lượt này.
- 9 suites host chạy lại PASS: Wi-Fi32/98,70%, MQTT22/99,59%, telemetry18/91,26%,
  command99,25%, clock, checked buzzer, sensor bus, Phase7 checker10 tests và LTE
  parser. Python/JSON syntax và git diff --check PASS; không build/flash lại.
- Final inventory78 file changed/untracked cần commit; không có local password
  hoặc actual SSID value trong candidate files. Các đường private/artifact được
  kiểm tra ignore; `build/commit_preparation/final_review.json`, candidate list
  và test logs giữ local. Không tự stage để người dùng review kết quả cụ thể.

[COMMIT_PREPARATION.md](COMMIT_PREPARATION.md) ghi phân loại, archive, commit
message và lệnh người dùng có thể chạy sau review. Đề xuất một commit baseline
nhất quán trên nhánh giữ mốc firmware trước khi xem/merge nhánh AI; không reset/
clean để ép sạch working tree. Khi tích hợp AI, cần đọc source nhánh đó và xử lý
dependency/conflict/timing thực tế, không giả định model đã sẵn sàng.
