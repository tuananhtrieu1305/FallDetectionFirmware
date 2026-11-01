# Chuẩn bị commit firmware trước khi tích hợp nhánh AI

Ngày: 2026-11-01, Asia/Bangkok. Nhánh hiện tại `main`, HEAD trước commit
`dae70f6067b88da27b20575975c911d56f8a10d2`. Theo yêu cầu người dùng, chỉ rà soát/
dọn local artifacts và chuẩn bị nội dung commit; chưa commit, stage, pull,
switch branch, push hoặc merge. Không triển khai Phase8.2.8 hay tích hợp AI mới.

## Giữ để commit

- `.gitignore`, `AGENTS.md`: loại file local/credentials/artifacts và giữ chỉ dẫn
  đọc master/progress/contract cho các phiên làm việc sau.
- Toàn bộ thay đổi `main/` và `sdkconfig`: hardware diagnostics đã phát triển,
  Sensor Task/IRQ/core affinity, Wi-Fi/MQTT, telemetry, clock, checked buzzer,
  command/ACK/dedup/TTL, CMake và config tương ứng. `sdkconfig` đang tracked và
  chứa cấu hình board/partition/core quan trọng, không loại như file rác.
- `main/network_config.h` và `main/network_config.example.h`: template/default
  sạch; header `.local.h` có credentials chỉ ở máy phát triển.
- `tests/`, các test runners và tools trong `tools/`: gồm fake SDK của host tests,
  recorder, broker setup và checker. Đây là regression tooling, không phải file
  giả lập thừa hoặc kết quả thiết bị thật. Các test C/headers cần giữ cùng runners.
- Tài liệu diagnostic, master/progress, các phase audit/test, MQTT/ACK contract,
  test plan/evidence template Member3 và cập nhật APP_WEB_HANDOFF.
- Các file đã tracked không đổi, gồm Bosch drivers, README, sample CSV/metadata
  chuẩn trong `docs/`, AI_DATA_HANDOFF.docx: giữ nguyên. Không xóa dữ liệu mẫu có
  chủ đích trong docs khi bỏ local recordings. Sample synthetic trigger vẫn có
  ground_truth unknown, không phải bộ ngã thật đã gán nhãn.

Không chia source thành các commit phase giả dựa trên trạng thái hiện tại:
app_main/CMake/modules/header/config phụ thuộc nhau. Một commit baseline nhất
quán là phương án đơn giản để giữ mốc firmware trước khi tích hợp nhánh AI.

## Chỉ giữ local, không đưa vào commit

| Nhóm | Xử lý |
| --- | --- |
| `captures/` | Giữ hai CSV/metadata nguyên checksum ở vị trí cũ; thêm ignore. Đây là recording thật, không xóa như rác |
| 7 file `log.fall_detection_firmware.*.txt` ở root | Chuyển nguyên byte vào archive `serial_logs/`, xác minh SHA-256 trước/sau |
| `sensor_csv_verified_4000.txt` | Chuyển vào `serial_logs/`; giữ sample CSV/metadata đã tracked trong docs |
| `sdkconfig.old` | Chuyển vào archive `config_backup/`; giữ sdkconfig hiện tại để commit |
| `build/` | Giữ local/ignored: có ELF/binary đã kiểm chứng, log evidence và broker config/credentials đang dùng. Không xóa toàn bộ build để dọn Git |
| `main/network_config.local.h`, `.vscode/settings.json` | Giữ tại máy/ignored, không di chuyển hoặc commit credentials/config theo máy |
| Python cache và artifact phát sinh mới | Đã có ignore; tại thời điểm kiểm tra không thấy cache trong tools/tests cần xóa |

Archive local (ignored):

`local_artifacts/pre_ai_merge_20261101/`

- `working_tree/`: bản sao100 file trước khi dọn, gồm source/docs/config và hai
  capture; không chứa `.git`, build hoặc private network header.
- `working_tree_manifest.json`: SHA-256 của từng bản sao.
- `serial_logs/`, `config_backup/`, `moved_evidence_manifest.json`:9 file,
  3.199.610 bytes đã chuyển, checksum khớp. Không ghi đè archive đã có.

Các lệnh/path log ở tài liệu audit lịch sử ghi vị trí tại thời điểm test. Sau
lần dọn này, tìm basename tương ứng trong `serial_logs/` theo manifest; không
chỉnh metadata lịch sử để giả như log gốc chưa từng ở root. Archive và build
không đi theo clone Git; cần giữ riêng nếu muốn tra lại evidence đầy đủ.

Tên SSID thật trong4 tài liệu được thay bằng nhãn `AP_DEMO` trước commit.
Đây là nhãn đã ẩn danh, không phải tên mạng để nhập vào firmware. Tài liệu gốc
vẫn có trong archive; local header và broker credentials không thay đổi. Không
thay UUID/checksum/outcome hoặc nâng trạng thái test.

## Kiểm tra đã chạy

- 9 suites host PASS: Wi-Fi32 scenarios/98,70%, MQTT22/99,59%, telemetry18/91,26%,
  command processor99,25%, clock, checked buzzer, sensor bus helper, Phase7
  checker10 tests và LTE AT response parser. Host không thay hardware evidence.
- Không sửa C/header/CMake/sdkconfig của firmware trong lần dọn. Build/flash
  không chạy lại; evidence build/hardware các phase trước vẫn ghi riêng.
- Kiểm tra secrets theo actual local passwords/SSID, Python/JSON syntax,
  raw capture preservation, archive hashes và `git diff --check`.
- Các kết quả chi tiết/candidate inventory dưới ignored `build/commit_preparation/`.
- Phase8.2.7 vẫn BLOCKED vì chưa có Backend/App; chưa có model AI hoàn chỉnh,
  GNSS outdoor fix/LTE data chưa được nghiệm thu. Commit không phải PASS toàn bộ.

## Commit đề xuất và trước khi nhận nhánh AI

Title:

`feat(firmware): integrate Wi-Fi MQTT demo and hardware diagnostics`

Body đề xuất:

```text
Add Wi-Fi/MQTT managers, real demo STOP_BUZZER ACK/TTL/dedup and telemetry.
Preserve sensor timing and retain diagnostic/host regression tooling.
Document verified firmware phases and prepare Member3 E2E tests.
Keep Phase 8.2.7 blocked pending Backend/App; exclude local credentials/logs.
```

Lệnh để người dùng chạy khi đã review, không phải lệnh đã được agent thực hiện:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
# Tạo nhánh giữ mốc firmware hiện tại nếu chưa có tên này:
git switch -c firmware/wifi-mqtt-baseline
git add -- .gitignore AGENTS.md main sdkconfig docs tests tools
git diff --cached --stat
git diff --cached --check
git diff --cached
# Sau khi xác nhận staged diff chỉ gồm các file mong muốn:
git commit -m "feat(firmware): integrate Wi-Fi MQTT demo and hardware diagnostics"
git status --short
```

Không dùng `git add -f` với private header/captures/build/archive. `git status`
sạch sau commit là mốc an toàn để tiếp tục xem nhánh AI. Khi có tên nhánh AI,
fetch/review diff và chọn merge/cherry-pick trên nhánh tích hợp riêng theo nhu
cầu; không `pull` chồng lên dirty main, không reset/clean để ép sạch workspace.
Branch AI có thể conflict ở app_main/CMake/sdkconfig/contract: giữ các ràng buộc
sampling/network/ACK đã kiểm thử rồi build/regression lại sau tích hợp.
