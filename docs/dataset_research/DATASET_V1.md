# Dataset UNIVRFall binary v1 — bản laboratory

Mục tiêu: phát hiện khi/vừa ngã, ưu tiên hạn chế bỏ sót, input sáu kênh IMU từ thiết bị đeo lưng dưới. Đây là dataset nghiên cứu theo thời gian danh định; chưa xác nhận hiệu quả trên prototype hoặc người cao tuổi.

Nguồn: [UNIVRFall Zenodo v1, DOI 10.5281/zenodo.18346755](https://zenodo.org/records/18346755), tác giả Ali, Demrozi, Turetta và Pravadelli; giấy phép CC BY 4.0. Khi sử dụng/phân phối lại cần ghi nguồn, tác giả, giấy phép và các bước chuyển đổi ở đây. Raw giữ nguyên, ngoài Git. Manifest lưu SHA-256, CRC32 từng member đã lấy; chưa kiểm MD5 toàn ZIP trong giai đoạn laboratory.

## Kết quả đã xây

| Hạng mục | Số lượng |
|---|---:|
| CSV laboratory đã thu và kiểm kê | 1.234 |
| Bảng nhãn XLSX | 29 |
| Dòng CSV nguồn, không tính header | 1.228.027 |
| Trial được dùng | 1.148 |
| Dòng của trial được dùng | 1.119.744 |
| Trial được cách ly | 86 |
| Sự kiện ngã hợp lệ | 573 |
| Người development / test | 23 / 6 |

29 bảng nhãn có **574 dòng**, trong đó `SA24 / T26 / R01` ghi onset = impact = 311; dòng này không đạt hợp đồng annotation và không bị tự sửa. Có 573 annotation hợp lệ, tất cả ghép được với CSV. Một trial khác `SA12 / T28 / R01` không có annotation tương ứng, không được tự coi là NON_FALL.

76 ADL của SA10–SA13 có protocol task khác chưa xác minh ý nghĩa từng hoạt động; thêm 8 trial T20/T21 của bốn người này không có bằng chứng nhãn. Tổng 84 trial này được giữ nguyên trong raw và cách ly để chờ protocol; các trial ngã có annotation hợp lệ của họ vẫn được dùng. Không suy đoán bảng dịch task +2. V1 hy sinh độ phủ ADL ở nhóm này để giữ tính đúng đắn của nhãn; bản sửa protocol sau này phải tạo phiên bản dataset mới.

## Hợp đồng dữ liệu

- Thứ tự kênh: `ax, ay, az, gx, gy, gz`; accel m/s² có trọng lực, gyro rad/s. Chuyển từ mg bằng ×0,00980665 và mdps bằng ×π/180000.
- Bản ghi vật lý: float32 `[rows, 6]`, kèm FrameCounter int64, timestamp host gốc đổi sang giây và thời gian danh định `(frame-first_frame)/100`.
- Giữ trục nguồn. Việc ánh xạ sang hệ trục prototype cần hiệu chuẩn vị trí/hướng gắn thực tế; không có phép quay tự suy đoán trong dataset.
- Không thêm lọc, không trừ trọng lực, không nội suy qua mất frame, không augmentation trong bản chuẩn. Euler/áp suất không phải input.
- File window: `X` float32 `[N, length, 6]`, `y` int8. `0=NON_FALL`, `1=FALL`, `-1=IGNORE`. **-1 phải loại khỏi loss; không phải lớp thứ ba.** Tensor giữ cả IGNORE để đánh giá chuỗi liên tục.
- Mỗi window truy được về người, trial, frame đầu/cuối, activity gốc, split và cờ chất lượng qua CSV index.
- Mean/std được tính trên từng dòng train trước windowing, riêng cho mỗi fold; bản final dùng 23 người development. Baseline đặc trưng dùng StandardScaler riêng fit trên feature train; model neural về sau dùng normalizer sáu kênh đã xuất.

Nhãn window dùng khoảng inclusive `[s,e]`: FALL nếu window chứa impact `I` và `I ≤ e ≤ I+100`; NON_FALL nếu trial là ADL đã xác minh hoặc window kết thúc trước `onset−50`; các trường hợp còn lại IGNORE. Không nối trial, không padding. Không gán toàn bộ trial ngã là FALL hoặc tự gán phần sau ngã thành NON_FALL.

| Window, stride 50 | NON_FALL | FALL | IGNORE | Sự kiện có window dương |
|---|---:|---:|---:|---:|
| 100 mẫu | 16.668 | 1.145 | 2.873 | 573/573 |
| 200 mẫu | 14.413 | 1.155 | 2.822 | 573/573 |
| 300 mẫu | 12.421 | 1.139 | 2.534 | 572/573 |

Window 300 không tạo được mẫu dương cho `S21T27R01`; sự kiện vẫn nằm trong mẫu số đánh giá event recall. Số window không phải số quan sát độc lập.

## Chia tập và baseline

Split cố định seed 42, chọn từ 1.000 hoán vị người bằng metadata hoạt động, số ngã và thời lượng ADL; không dùng tín hiệu hoặc điểm model để chọn split. Mỗi tập có đủ 44 nhóm laboratory: 23 ADL và 21 loại ngã. Test gồm **SA09, SA13, SA16, SA17, SA19, SA24**; 23 người còn lại chia năm fold. Người và trial không đi qua ranh giới tập.

Baseline dùng 40 đặc trưng: mean/std/min/max/RMS của sáu kênh vật lý cùng độ lớn accel và gyro; StandardScaler + LogisticRegression cân bằng trọng số lớp, C=1. Ngưỡng và độ dài window chọn trên dự đoán development out-of-fold, theo recall tại ≤1 báo giả/giờ danh định, rồi độ trễ trung vị và độ dài ngắn hơn. Có báo cáo đường đánh đổi tại 0,1/0,25/0,5/1/2 báo giả/giờ. Đây là tiêu chí so sánh, không phải SLA sản phẩm.

| Window | Development phát hiện ngã | Recall | Báo giả / giờ danh định |
|---|---:|---:|---:|
| 100 | 443/456 | 97,15% | 0 |
| 200 | 440/456 | 96,49% | 0,719 |
| 300 | 436/456 | 95,61% | 0,792 |

Đã khóa **100 mẫu, stride 50**, ngưỡng **0,9973402932729418** trước khi đánh giá sáu người test. Test phát hiện **117/117 sự kiện**, không có báo giả trên **0,39047 giờ ADL được giám sát**, độ trễ trung vị **0,25 giây danh định**, p95 **0,47 giây danh định**. Không có chỉnh cấu hình sau khi xem test.

Đây là kết quả trong nguồn laboratory. Thời lượng ADL test chỉ khoảng 23,4 phút: dù không thấy báo giả, cận trên Poisson một phía 95% vẫn khoảng **7,67 báo giả/giờ danh định**. Khoảng tin cậy nhị thức 95% cho 117/117 khoảng [96,90%; 100%], nhưng giả định sự kiện độc lập không phản ánh hết tương quan trong cùng người. Kết quả này không chứng minh độ tin cậy khi đeo thực tế.

## Chất lượng và giới hạn

- Tất cả 1.148 trial được dùng có timestamp host lặp; tốc độ hiệu dụng theo host khoảng 106,19–112,56 Hz thay vì 100 Hz công bố. Clock chưa giải quyết; không gọi window 100 mẫu là đúng một giây vật lý đã xác nhận.
- 604 trial có thành phần accel gần giới hạn quan sát ±4g, khác dải ±16g trong metadata. Có 7 trial gyro vượt ±2000°/s, tối đa 2111,2°/s. Giữ nguyên và gắn cờ; chưa kết luận cơ chế clipping, scaling hay calibration nguồn. Có cả ADL và fall gần biên, cần kiểm tra chuyển miền trên phần cứng.
- Không phát hiện hai trial được dùng có tensor sáu kênh trùng hoàn toàn. Kiểm tra này không loại trừ mọi dạng trùng người/phiên hoặc tín hiệu gần giống.
- Đã sinh và xem 13 trang biểu đồ, 103 trial đại diện theo người/hoạt động và toàn bộ 7 trial gyro vượt dải. Các mốc có thể kiểm tra với chuyển động nhìn trên tín hiệu; không có video để xác nhận ngữ nghĩa từng nhãn hoặc sửa frame.
- Nguồn chưa đại diện đầy đủ người cao tuổi/người phục hồi chức năng. Các ADL tháo thiết bị, làm rơi thiết bị, đai xoay/trượt và nằm nghỉ nhiều giờ còn cần thu bằng prototype.
- OnField được tải riêng để kiểm tra báo giả với model/ngưỡng đã khóa; chưa đưa vào train hay báo cáo kết quả khi chưa kiểm tra đủ schema/clock/đơn vị. Không dùng các cột `aiOut0/aiOut1` của nguồn làm feature hoặc ground truth.

## Artifact và chạy lại

Thư mục dữ liệu trên máy hiện tại:

```text
C:/Users/Admin/.codex/visualizations/2026/10/31/01a19255-0f78-7130-b6ac-088fb917fbd1/dataset-research/
  raw/univrfall/full_download_manifest.json
  raw/univrfall/full_members/
  univrfall_binary_v1/
    config.json, audit.json, annotation_errors.json, quarantine.json
    recording_manifest.json, annotations.json, unmatched_annotations.json
    recordings/*.npz
    splits.json, normalizers.json
    windows_{100,200,300}.npz, window_index_{100,200,300}.csv
    tensor_hashes.json, reproduction.json, verification.json
    selection_lock.json, benchmark.json, baseline_model.json
    selected_window_predictions.csv, test_trial_results.csv
    review/review_index.csv, review_*.png, quality_distributions.png
```

Từ repo root, dùng môi trường Python riêng và các dependency trong `tools/datasets/requirements.txt`. Pin requests đã nâng lên 2.34.2 sau audit; môi trường khảo sát cũ ghi trong environment.json vẫn giữ nguyên làm bằng chứng lịch sử. Audit trực tiếp bảy dependency được ghim không thấy lỗ hổng đã biết; đây không phải audit toàn bộ môi trường máy.

```powershell
$datasetRoot = 'C:/Users/Admin/.codex/visualizations/2026/10/31/01a19255-0f78-7130-b6ac-088fb917fbd1/dataset-research'
python tools/datasets/acquire_univrfall.py --raw "$datasetRoot/raw/univrfall"
python tools/datasets/build_univrfall.py --raw "$datasetRoot/raw/univrfall" --out "$datasetRoot/univrfall_binary_v1"
python tools/datasets/benchmark_univrfall.py --dataset "$datasetRoot/univrfall_binary_v1"
python tools/datasets/verify_univrfall.py --raw "$datasetRoot/raw/univrfall" --dataset "$datasetRoot/univrfall_binary_v1"
python tools/datasets/review_univrfall.py --dataset "$datasetRoot/univrfall_binary_v1"
python -m unittest discover -s tools/datasets -p test_univrfall.py
```

`acquire_univrfall.py --subset all` tiếp tục tải toàn archive bằng range có cache và backoff, sau đó materialize OnField; không coi cache tải dở là dữ liệu CRC-verified. Trạng thái tải phải xem tiến trình thật và manifest hiện tại.

Kiểm thử gồm nhãn riêng từng người, nhãn thiếu/trùng/sai frame, biến thể header thời gian, đổi đơn vị, ranh giới window, split lặp lại được, normalizer chỉ dùng train, đếm báo động theo chuỗi và kiểm tra thay toàn bộ feature test không làm đổi lựa chọn cấu hình. Verifier độc lập đối chiếu tất cả raw hash, annotation hợp lệ, sáu normalizer và toàn bộ window với nguồn.
