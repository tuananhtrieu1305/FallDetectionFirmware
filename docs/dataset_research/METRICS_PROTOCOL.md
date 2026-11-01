# Hợp đồng đánh giá model phát hiện ngã — v1.1

Chốt ngày 2026-11-01. Áp dụng cho các thí nghiệm tiếp theo trên UNIVRFall binary v1. Đã triển khai evaluator dùng chung, kiểm tra bằng dữ liệu tổng hợp và chạy baseline/OnField; chưa train CNN. Báo cáo tại [reports/metrics_v1_1](../../reports/metrics_v1_1/README.md). Kết quả baseline cũ giữ nguyên protocol v1, không tự đổi tên thành kết quả v1.1.

## 1. Quyết định chính

**Tối đa hóa Event Recall trên development, với False Alarms per Hour (FA/h) ≤ 1.** Báo cáo đồng thời độ trễ, độ bất định, mức khác nhau giữa người và chi phí chạy trên thiết bị.

- Đây là điểm vận hành nghiên cứu, giữ khả năng đối chiếu baseline. Không phải ngưỡng chấp nhận sản phẩm hoặc chuẩn y tế.
- Không chọn model theo accuracy, window F1 hoặc ROC-AUC đơn lẻ.
- Input cố định 100 mẫu × 6 kênh; stride 50; thời gian laboratory quy đổi theo 100 Hz **danh nghĩa**. Đổi window, stride, nhãn hoặc cơ chế cảnh báo phải ghi phiên bản thí nghiệm.
- Điểm đầu ra `score_fall` không được mặc nhiên xem là xác suất đã hiệu chuẩn.

## 2. Từ window đến cảnh báo

Với window k, chỉ dùng dữ liệu đến frame cuối `e[k]`. Quyết định `positive[k] = score[k] >= threshold`. Không dùng dữ liệu tương lai hoặc nhãn thật để tạo cảnh báo.

Một cảnh báo bắt đầu khi quyết định chuyển 0 → 1. Window đầu của một segment nếu dương cũng tạo cảnh báo. Chuỗi dương liên tiếp chỉ tạo một cảnh báo; một window âm cho phép cảnh báo mới ở lần dương tiếp theo. V1.1 không thêm smoothing, bỏ phiếu hoặc cooldown. Nếu thử các cơ chế đó sau này phải chọn trên development và chạy lại baseline với cùng quy tắc.

Timestamp cảnh báo offline là frame cuối window tạo cảnh báo, không phải frame đầu/giữa. Trên thiết bị, timestamp cảnh báo là lúc kết quả thực sự sẵn sàng sau xử lý.

Reset buffer và trạng thái ở đầu trial/segment mất dữ liệu; không reset theo onset hoặc impact. Không nối trial, không nội suy qua gap. Phải phát hiện và báo lỗi nếu thiếu score của một window đủ điều kiện, không được âm thầm bỏ window/đổi mẫu số.

## 3. Metric chính: Event Recall

Mỗi sự kiện có onset `O` và impact `I`. Khoảng ghép cảnh báo đúng là **[O, I + 100]**, inclusive, theo frame nguồn. Mỗi sự kiện hiện nằm trong một trial riêng.

- `TP_event`: số sự kiện có ít nhất một **cảnh báo bắt đầu** trong khoảng ghép.
- `FN_event`: tổng sự kiện hợp lệ của tập đánh giá trừ `TP_event`.
- `Event Recall = TP_event / (TP_event + FN_event)`.
- `Miss Rate = FN_event / (TP_event + FN_event) = 1 - Recall`.
- Ghép cảnh báo hợp lệ đầu tiên; mỗi sự kiện chỉ được tính một TP. Các cảnh báo hợp lệ sau đó là cảnh báo lặp.
- Cảnh báo bắt đầu trước O không được tính là phát hiện, dù trạng thái dương kéo dài qua impact. Cảnh báo chỉ xuất hiện sau I+100 vẫn là bỏ sót theo deadline này.
- Mẫu số lấy từ manifest sự kiện, **không lấy từ các recording có prediction**. Sự kiện không sinh đủ window vẫn nằm trong mẫu số và ghi rõ nguyên nhân bỏ sót. Lỗi pipeline thiếu prediction phải làm lần chạy không hợp lệ.

Báo cáo micro recall (tổng TP / tổng sự kiện) làm metric chính, macro recall (trung bình recall từng người có sự kiện) làm metric phụ bắt buộc. Bảng theo người và loại ngã ghi cả TP, FN và tổng số sự kiện. Trường hợp không có sự kiện ghi N/A, không ghi 0% hay 100%.

## 4. Metric ràng buộc: False Alarms per Hour

`FA/h = tổng cảnh báo bắt đầu trên ADL đã xác minh / tổng giờ ADL được theo dõi`.

Đếm trên toàn bộ chuỗi ADL, không chỉ một tập window âm đã cân bằng. Không nhân số window với độ dài window vì các window chồng lấn.

Giữ quy ước exposure của baseline: segment liên tục có N mẫu, window L=100, fs=100 thì `T_segment = max(0, N-L+1) / fs / 3600` giờ danh nghĩa. Bỏ L−1 mẫu warm-up ở mỗi segment; thời gian sau quyết định cuối đến hết segment vẫn được tính khi trạng thái được giữ. Không tính thời gian mất dữ liệu. Ghi cả thời lượng nguồn, thời lượng warm-up/gap bị loại và thời lượng theo dõi. Trên phần cứng dùng thời gian monotonic đã xác minh thay cho clock danh nghĩa.

- Báo cáo tổng số cảnh báo và tổng số giờ bên cạnh tỷ lệ. Không lấy trung bình không trọng số FA/h giữa các file làm kết quả tổng.
- Cảnh báo sớm, muộn và lặp trong trial ngã báo cáo riêng; không trộn vào FA/h trên ADL, vì đoạn sau ngã chưa có nhãn âm đáng tin.
- Với OnField, tên metric phải là **alarms/source-negative hour**: nguồn mô tả là không ngã, chưa được xác minh nhãn độc lập. Báo cáo đủ 18 file; không loại filename ID 999/1000 theo suy đoán. Không gộp OnField và laboratory thành một FA/h duy nhất.
- Báo cáo thêm **alarm-active fraction** trên ADL: thời lượng giữ quyết định dương / tổng thời lượng theo dõi. Giữ mỗi quyết định từ thời điểm phát ra đến quyết định kế tiếp hoặc hết segment theo cùng quy ước exposure. Kèm thời lượng chuỗi dương dài nhất. Một model luôn báo dương có thể có ít cạnh cảnh báo nhưng vẫn bị lộ bởi hai thống kê này; không tuyên bố model đó tốt chỉ nhờ FA/h thấp.

## 5. Độ trễ và phát hiện đúng hạn

Với cảnh báo đúng đầu tiên A: `delay_frames = A - I`, `delay_nominal_s = (A-I)/100`.

- Báo cáo median và P95 (percentile nội suy tuyến tính), số sự kiện đóng góp và tỷ lệ cảnh báo trước impact. Giữ giá trị âm, không cắt về 0. Đây không phải chứng minh khả năng dự đoán ngã trước va chạm.
- Độ trễ chỉ tính cho sự kiện phát hiện được; sự kiện bỏ sót không được gán delay=0.
- Bắt buộc kèm **Recall@0.5s** và **Recall@1s**: tỷ lệ trên **tất cả sự kiện** có cảnh báo bắt đầu trong [O, I+50] và [O, I+100]. Recall@1s chính là Event Recall. Nhờ vậy model chỉ bắt được vài lần dễ không được đánh giá tốt chỉ vì delay thấp.
- Delay offline chưa gồm thời gian tính model, truyền tin hoặc gửi thông báo. Trên phần cứng đo riêng sensor→quyết định và quyết định→thông báo; không gọi delay offline là độ trễ end-to-end.

## 6. Metric hỗ trợ theo window

Chỉ tính trên nhãn 0/1, FALL là lớp dương. IGNORE không tham gia loss hoặc metric window, nhưng **vẫn phải suy luận** để đánh giá cảnh báo liên tục.

- Confusion matrix: hàng là nhãn thật, cột là dự đoán, thứ tự [NON_FALL, FALL].
- Precision = TP/(TP+FP); Recall = TP/(TP+FN); F1 = 2TP/(2TP+FP+FN).
- **Average Precision (AP)** làm bản tóm tắt precision–recall không phụ thuộc ngưỡng: `AP = sum((R_n-R_(n-1))*P_n)`, theo các mức score giảm dần. Dùng AP, không gọi lẫn với diện tích PR tính bằng hình thang.
- Ghi tỷ lệ FALL trong tập vì precision/AP phụ thuộc phân bố nhãn. Mẫu số bằng 0 ghi N/A và kèm counts. Không bootstrap các window chồng lấn như quan sát độc lập.
- Accuracy/ROC-AUC có thể ghi phụ lục; không dùng để xếp hạng model. Event precision không dùng làm metric chính trên các trial laboratory dàn dựng vì tỷ lệ ngã/giờ không phản ánh đời sống.

## 7. Chọn model và threshold

Giữ sáu người test hiện có. Bản train 18 người / validation 5 người (fold0) phục vụ chạy thử; đánh giá chọn model chính thức dùng 5-fold theo người trên 23 người development như baseline. Mỗi người chỉ được dự đoán bởi model chưa train trên người đó. Mean/std, class weights và augmentation chỉ học/áp dụng từ train của fold tương ứng.

Nếu early stopping: dùng nhóm người validation nội bộ tách từ train của outer fold, hoặc số epoch cố định từ trước; không dùng nhãn outer fold để chọn checkpoint rồi gọi dự đoán đó là holdout độc lập. Development dùng để chọn cấu hình vẫn là kết quả lựa chọn, không phải ước lượng test không thiên lệch.

Quét ngưỡng từ score OOF development. V1.1 dùng tất cả score phân biệt, cộng ngưỡng all-positive và all-negative; phải tính lại các cạnh cảnh báo tại từng ngưỡng. FA/h đếm cạnh **không nhất thiết đơn điệu theo ngưỡng**. Không dùng tìm kiếm nhị phân hoặc giả định threshold cao luôn giảm số cảnh báo.

Quy tắc chọn xác định, theo thứ tự:

1. Giữ các cấu hình/ngưỡng có FA/h ADL development ≤ 1.
2. Chọn micro Event Recall cao nhất.
3. Nếu bằng: macro Event Recall cao hơn; FA/h thấp hơn; P95 delay thấp hơn; alarm-active fraction thấp hơn; model ít tham số hơn; threshold cao hơn; cuối cùng ID cấu hình theo thứ tự từ điển. Delay thiếu coi là +∞ khi phá hòa.
4. Trường hợp chỉ có model không phát hiện được sự kiện nào đáp ứng giới hạn: báo thất bại, không gọi all-negative là model đạt.

Báo cáo thêm đường trade-off và điểm vận hành tại 0.1, 0.25, 0.5, 1, 2 FA/h theo cùng quy tắc. Đây là mức quan sát; dữ liệu ngắn có thể cho cùng một điểm ở nhiều giới hạn. Không suy ra đã chứng minh mức 0.1/h chỉ vì quan sát 0 cảnh báo.

Lưu cấu hình, seed, threshold, preprocessing, split hash, model hash, phiên bản evaluator và checkpoint trước khi đánh giá test/OnField. Khóa seed chính 42; nếu chạy thêm 43,44 để kiểm tra ổn định phải báo cả ba, không chọn seed tốt nhất theo test.

Baseline lịch sử dùng 301 quantile threshold và tie-break khác. Muốn xếp hạng CNN với Logistic Regression theo v1.1 phải tính lại lựa chọn development của **cả hai** cùng protocol. Không so CNN train 18 người với baseline train 23 người rồi kết luận do kiến trúc.

Test và OnField đã được xem ở baseline: gọi đây là bộ benchmark cố định, không gọi là dữ liệu hoàn toàn chưa từng thấy của toàn quá trình nghiên cứu. Không chỉnh model/ngưỡng theo lỗi của chúng; cần dữ liệu phần cứng mới hoặc bộ độc lập cho xác nhận cuối. Nếu dùng OnField để phát triển sau này phải đổi vai trò thành development và có bộ xác nhận mới.

## 8. Độ bất định và điều kiện báo cáo

- Báo cáo khoảng 95% cho recall và FA/h bằng bootstrap theo **người**, giữ nguyên toàn bộ trial của người được lấy mẫu: 10.000 lần, seed 42, khoảng percentile 2.5–97.5. Tính lại tỷ lệ từ tổng counts/exposure ở từng lần; không bootstrap window. Khoảng này có điều kiện trên model/prediction đã cố định, không bao gồm bất định của toàn bộ quá trình train/chọn model.
- Nêu số người; test chỉ có 6 người nên khoảng bootstrap còn hạn chế. Nếu bootstrap suy biến khi không có lỗi, không coi [100%,100%] hay [0,0] là bằng chứng chắc chắn.
- Kèm Clopper–Pearson 95% cho recall dưới giả định sự kiện độc lập; và cận trên Poisson một phía 95% cho FA/h. Các giả định này không thay thế phân tích theo người. Khi 0 cảnh báo trên T giờ, cận trên là `-ln(0.05)/T ≈ 2.996/T`.
- Ví dụ: 0 cảnh báo trong 0.39047 giờ chỉ cho cận trên xấp xỉ 7.67/h, không chứng minh rate ≤1/h. Khi có 0 cảnh báo cần ít nhất khoảng 3 giờ để cận trên Poisson ≤1/h, hoặc 30 giờ để ≤0.1/h; vẫn phải kiểm tra tính đại diện và phụ thuộc theo người.
- OnField chưa xác minh ánh xạ filename ID→người: không giả làm bootstrap theo người; báo cáo counts/exposure theo file/session và nêu giới hạn. Không suy ra recall vì không có sự kiện ngã được gán nhãn ở đây.

## 9. Khả năng triển khai và báo cáo bắt buộc

Trên thiết bị đích: kích thước model (bytes), peak RAM gồm buffer/tensor arena, thời gian tiền xử lý+suy luận median/P95/max, số deadline miss và mẫu mất. Với stride50 ở100Hz, chu kỳ xử lý là500ms: yêu cầu hoàn thành trong chu kỳ với dự phòng tài nguyên. Chưa chốt một giới hạn RAM tuyệt đối khi chưa đo tài nguyên firmware còn trống.

Sau quantization/chuyển runtime phải chạy lại metric chất lượng và đo phần cứng. Không mặc nhiên chuyển kết quả float32 sang model int8.

Mỗi báo cáo phải có: split/số người; TP/FN và recall micro/macro; FA và giờ ADL; FA/h; CI/cận trên; median/P95 delay; Recall@0.5s; alarm-active fraction; cảnh báo sớm/muộn/lặp; confusion matrix/precision/recall/F1/AP; bảng theo người/hoạt động; model/threshold/seed/hash; kết quả OnField riêng; tài nguyên thiết bị nếu đã đo. Thông số chưa đo ghi NOT MEASURED.

Không chốt sẵn accuracy 99% hoặc recall 100% như tiêu chuẩn đạt. Mục tiêu hiện tại là tối đa hóa recall dưới ngân sách báo nhầm, chứng minh trade-off so với baseline và nêu rõ mức độ chắc chắn; tiêu chí nghiệm thu sản phẩm cần xác nhận thực tế riêng.

## 10. Triển khai và nghiệm thu

Lệnh chạy và API cho CNN: [METRICS_USAGE.md](METRICS_USAGE.md).

- `tools/datasets/metrics_v11.py`: đầu vào manifest/prediction, alarm runs, ghép sự kiện, các metric, CI và quét threshold chính xác. API `evaluate(...)` dùng chung cho baseline/CNN; `select_threshold(...)` chỉ nhận development.
- `tools/datasets/run_metrics_v11.py`: dùng score baseline OOF/test đã lưu, xuất báo cáo và đối chiếu metric cũ ở cùng ngưỡng.
- `tools/datasets/onfield_metrics_v11.py`: adapter streaming sáu kênh IMU, tách segment theo timestamp, giữ đầy đủ 18 file nguồn.
- `tools/datasets/verify_metrics_v11.py`: kiểm tra artifact, parity laboratory, chunk invariance tất cả file OnField và đối chiếu số cảnh báo/frame/giờ với release cũ tại ngưỡng cũ.
- Các test `test_metrics_v11.py`, `test_metrics_report.py`, `test_onfield_metrics_v11.py`: tình huống tính tay, gap, biên thời hạn, N/A, schema lỗi, bootstrap, AP và test không ảnh hưởng ngưỡng.

Bản v1.1 hiện chọn threshold cho một cấu hình model cố định. Khi so nhiều kiến trúc, áp dụng tiếp tie-break số tham số và ID cấu hình như mục7. RAM/thời gian suy luận thiết bị vẫn NOT MEASURED, cần đo khi tích hợp firmware.

Đường dẫn dữ liệu audit lấy từ trường `source` trong `data/processed/univrfall_v1/manifest.json`. Không dùng bản export đã loại IGNORE để chấm cảnh báo liên tục. Các file phiên bản cũ giữ nguyên; kết quả v1.1 nằm riêng trong project.

## Cơ sở tham khảo

Nghiên cứu thực tế của [Kangas et al., Sensitivity and false alarm rate of a fall sensor in long-term fall detection in the elderly](https://pubmed.ncbi.nlm.nih.gov/25138139/) báo cáo sensitivity cùng false alarms trên giờ sử dụng qua theo dõi dài hạn. Đây là cơ sở cho việc dùng cặp metric theo sự kiện/thời gian thay vì chỉ accuracy theo window. Các lựa chọn deadline +100 frame, giới hạn1/h, stride50 và quy tắc tie-break ở trên là quyết định kỹ thuật của project, không phải tiêu chuẩn từ bài báo.
