# Phase 11.11 — A7670C UART AT diagnostic

Ngày: 2026-10-30 (Asia/Bangkok). Chỉ kiểm tra UART/AT, không triển khai LTE
registration, SMS/call hoặc MQTT. Wiring theo người dùng: modem board 7 chân
V1.0 cấp riêng 5V/3A, GND chung, modem TX → GPIO18, GPIO17 → modem RX;
shop xác nhận UART board có logic 3.3V. Firmware không thao tác 3.8EN/PWRKEY,
NET/DTR hoặc thay wiring.

## Baseline và chọn mode

Hiện tại (Phase 8.2.2 PASS ngày 2026-10-30): source chọn UART=0/ADC=0 để bật
Wi-Fi và giữ LTE ở GPIO diagnostic 7.12e. Implementation UART/AT vẫn giữ nguyên.
Muốn chạy riêng Phase 11.11, chọn lại bộ switch UART=1/ADC=0/SKIP_WIFI=1 như
dưới đây và build/flash; bản cô lập Wi-Fi đó không dùng nghiệm thu Phase 2.

Khi bắt đầu lượt này, source thực tế có `LTE_TX_ADC_DIAG=0` sau retest Wi-Fi
ở progress mục 20, chọn 7.12e; khác mô tả bản ADC trong yêu cầu. Giữ nguyên
implementation ADC và GPIO cũ, thêm mode UART loại trừ nhau trong header:

```c
#define LTE_UART_AT_DIAG 1
#define LTE_TX_ADC_DIAG 0
#define LTE_UART_AT_DIAG_SKIP_WIFI 1
```

Bật ADC và UART cùng lúc gây compile error. `#if/#elif/#else` đảm bảo chỉ một
task/owner GPIO18 được biên dịch. Không có ADC/GPIO sampling 7.12e khi UART bật.
Normal console là UART0; GNSS là UART1 GPIO15/9600. UART2 chỉ do task LTE đọc
và ghi. Nếu UART2 đã có driver khác sở hữu, diagnostic báo INIT FAIL và không
xóa driver của module khác.

Wi-Fi được bỏ startup có chủ đích trong riêng mode UART với SKIP_WIFI=1.
Đặt SKIP_WIFI=0 có thể cho Wi-Fi startup trong mode UART; đặt cả UART/ADC=0
khôi phục đường Wi-Fi/7.12e cũ. Muốn chạy ADC cũ: UART=0, ADC=1; ADC vẫn yêu
cầu cô lập Wi-Fi. Mọi thay đổi switch cần build/flash lại.

## Luồng hữu hạn

1. START, cấu hình UART2 TX17/RX18, 115200/8N1, no flow control, RX ring 4096
   byte, TX ring 256 byte. RX không pull-up/pull-down. Không tự đổi baud.
2. Chờ **10 giây sau init UART** (do đó ít nhất 10 giây sau boot); liên tục đọc
   dữ liệu boot trong task LTE, log nhưng không đưa dữ liệu boot vào parser OK.
3. Drain thêm 200 ms, báo số byte buffered rồi `uart_flush_input()` đúng một lần
   trước chuỗi AT. Phần bị flush chưa log chi tiết có số lượng báo rõ; tổng log
   mỗi cửa sổ được giới hạn và có suppressed counter. `buffered` là snapshot
   ngay trước flush; byte đang truyền trong FIFO/đến sau snapshot cũng có thể
   bị flush và không được tính chính xác vào snapshot này.
4. Gửi đúng `AT\r` (hex `41 54 0D`), kiểm tra đủ 3 byte và TX completion timeout
   200 ms. Chỉ một writer, tối đa 15 byte cả phiên nên TX ring không thể đầy.
5. Đọc phản hồi tối đa khoảng 2 giây tính từ lần TX. Không OK thì log TIMEOUT
   và thử lại, tổng tối đa 5 attempts. Các cửa sổ này tạo khoảng cách TX khoảng
   2 giây, không thêm sleep 2 giây nữa. Scheduler/log có thể làm chênh thời điểm.
6. PASS chỉ khi nhận **nguyên dòng `OK`** kết thúc CR hoặc LF. Echo `AT` được
   log nhưng không phải PASS. Parser giữ state giữa chunks, từ chối `NOK`,
   `OKAY`, `ATOK`, ` OK`, `OK `, dữ liệu nhị phân hoặc dòng quá dài. `OK` chưa
   có terminator chưa được chấp nhận. Không reset RX bằng flush giữa retries.
   Một OK đến muộn vẫn là phản hồi AT của phiên; không đảm bảo gán chính xác
   nó cho attempt mới hay attempt trước.
7. Khi thành công, hết attempts hoặc lỗi, xóa driver UART2 do chính task cài,
   log COMPLETE rồi tự xóa task. Guard manager không cho start lần hai trong
   cùng boot. Cleanup failure được log riêng. Task không lặp vô hạn.

Mỗi read chờ tối đa 20 ms. Mỗi cửa sổ có deadline monotonic và giới hạn nhận
32.768 byte để abort nếu flood. Lỗi đọc, lỗi TX/init và flood không được đổi
thành PASS. Không có `ESP_ERROR_CHECK`/abort làm dừng Sensor Manager.

## Log dữ liệu và tác động

`AT RX data=...` escape CR/LF/tab/backslash và control byte, không in control
thẳng ra terminal. Hàng có byte bất thường (ngoài printable ASCII/CR/LF/tab)
có thêm `AT RX HEX`. Mỗi cửa sổ BOOT/DRAIN/RESPONSE chỉ in tối đa 256 byte đầu
nhưng parser vẫn nhận mọi byte đọc thành công; summary ghi total/logged/suppressed.
Dữ liệu boot thực có thể trống nếu modem đã khởi động trước khi UART được init.

Task priority 3/stack 4096, buffers cố định, UART timeout giúp nhường CPU.
Sensor/GNSS/alert/Wi-Fi Manager/config/sdkconfig được bảo toàn. GPIO4 vẫn poll
20 ms và bỏ event; motor auto-test đã disabled sẵn. Trong mode UART bỏ riêng
caller auto-test buzzer ở app_main; code điều khiển/khởi tạo buzzer không đổi.
Lịch buzzer cũ trở lại khi tắt mode UART. Không gọi alert/MQTT/SMS/call từ LTE.

## Build, flash, monitor

Trong ESP-IDF v5.5.5 terminal đã kích hoạt, đóng monitor khác đang giữ COM5:

```powershell
Set-Location 'C:\Workspace\FallDetectionFirmware'
$env:ESP_ROM_ELF_DIR = 'C:\Espressif\tools\esp-rom-elfs\20241011'
$env:IDF_CCACHE_ENABLE = '0'
$env:CCACHE_DISABLE = '1'
$env:IDF_PY_BUILD_JOBS = '1'
idf.py --no-ccache build
idf.py --no-ccache -p COM5 flash monitor
```

Chỉ monitor nếu đã flash đúng binary:

```powershell
idf.py --no-ccache -p COM5 monitor
```

Thoát bằng `Ctrl+]`. Thu log tối thiểu 40 giây, giữ nguyên wiring/nguồn theo
yêu cầu. Không tự reset/PWRKEY modem hoặc thay baud để ép PASS.

Các mốc mong đợi (dữ liệu minh họa, không phải log đo thật):

```text
LTE_UART_AT_DIAG START | Phase 11.11 | at_us=...
UART2 INIT PASS | TX=GPIO17 RX=GPIO18 baud=115200 8N1 flow=NONE ...
AT RX data=... | phase=BOOT ...                  (nếu có boot data)
RX stale cleanup: ... buffered=... bytes
AT TX attempt=1 data=AT\r hex=41 54 0D at_us=...
AT RX data=\r\nAT\r\r\nOK\r\n | phase=RESPONSE ...
AT RESPONSE PASS | attempt=1 | complete OK line received
LTE_UART_AT_DIAG COMPLETE | result=PASS attempts=1 | AT-only, not LTE network readiness
```

Nếu không có nguyên dòng OK, mỗi lần có `AT RESPONSE TIMEOUT`, tối đa attempt 5,
COMPLETE result=TIMEOUT. Init lỗi có `UART2 INIT FAIL`; lỗi I/O/TX/flood có
COMPLETE IO_ERROR. Không xem kết quả thiếu OK là AT PASS hoặc modem online.

Theo dõi thêm sensor `diag_5s`, missed_ticks/jitter, GPIO4, GNSS và xác nhận
motor/buzzer không tự test. Build và host parser test không thay thế hardware
test UART/logic levels/noise. Lượt triển khai không flash hoặc mở serial;
chưa có AT RESPONSE PASS từ modem thật.

Host parser check (GCC trên máy, không chạy trong firmware):

```powershell
gcc -std=c11 -Wall -Wextra -Werror -I main tests/lte_at_response_test.c -o build/phase11_11/lte_at_response_test.exe
& .\build\phase11_11\lte_at_response_test.exe
```

## Bằng chứng triển khai

- Build ESP-IDF v5.5.5 PASS exit 0, ccache off, Ninja -j1; incremental compile
  app_main/lte_manager, link và partition check thành công. App 0x4cbe0 =
  314.336 byte, còn 70% app partition 1 MB; không đổi sdkconfig/partition.
- Không compiler warning/error/fatal/FAILED trong `build/phase11_11/build.log`;
  `build.exitcode` trong cùng thư mục bằng 0.
- Host parser test PASS; `build/phase11_11/parser_test.log`.
- `nm` kiểm tra ELF: UART read/write/flush có mặt; ADC read, GPIO test 7.12e,
  Wi-Fi start và buzzer auto-test không có mặt. Các bài cũ bị loại khi compile,
  không bị xóa source. Bản UART vẫn dùng GNSS UART1 độc lập.
- So sánh hai body ADC/7.12e với snapshot đầu lượt: không đổi. Hash source ngoài
  LTE/app và sdkconfig giữ nguyên. `build/phase11_11/verification.xml`, các file
  `*hashes*.xml` và `*.before.*` giữ bằng chứng; artifact đều ở ignored build.
- `git diff --check` PASS. Không flash/monitor, không xác nhận modem thật trả OK,
  và không có kiểm thử hardware/regression sampling mới.

Trạng thái Phase 11.11: **CODE_DONE_NEEDS_HARDWARE_TEST**. Không tự chuyển phase,
không commit/push/merge. Kết quả modem thật cần log `AT RESPONSE PASS` sau flash.
