# Phân tích baseline và bước cần làm tiếp theo

**Ưu tiên tiếp theo: nhận bộ test phần cứng nhỏ có ghi nhãn, kiểm tra đơn vị/clock/hướng gắn rồi chạy baseline đã khóa.** Giữ LR C=0,1 +40 đặc trưng và ngưỡng hiện tại cho lần thử đầu. Chưa có dữ liệu đủ nhãn để xác nhận model hoạt động trên prototype; chưa có căn cứ bắt buộc chuyển sang CNN.

## 1. Kết quả đủ tốt ở đâu, chưa chứng minh được gì?

| Metric | Development OOF, 23 người | Test cố định, 6 người |
|---|---:|---:|
| Event recall | 98.46% | 100.00% |
| Macro event recall | 98.36% | 100.00% |
| Recall trước/đến impact+0,5s | 94.74% | 96.58% |
| Window precision | 99.89% | 100.00% |
| Window recall | 95.29% | 98.28% |
| Window F1 | 97.53% | 99.13% |
| Window AP | 99.94% | 99.98% |
| Phát hiện / tổng ngã | 449/456 | 117/117 |
| Cảnh báo nhầm / giờ ADL theo dõi | 1/1.5187 | 0/0.3905 |
| FA/h | 0.658 | 0.000 |
| Trễ median / P95, giây danh nghĩa | 0.240/0.486 | 0.240/0.470 |

Metric window chỉ dùng nhãn0/1; window IGNORE vẫn được suy luận để đếm cảnh báo liên tục. Precision window cao không có nghĩa cùng tỷ lệ cảnh báo đúng ở đời thực; prevalence ngã và số giờ bình thường khác nhau. Không ghép window precision với event recall để tính F1.

Recall bootstrap theo người95% development: [0.9634695831492119, 0.9978586723768736]; FA/h: [0.0, 2.086541562666118]. Cận trên Poisson một phía95%: development 3.124/h, test 7.672/h. 0FA trong khoảng23,4 phút test chưa chứng minh rate≤1/h. Bootstrap test suy biến khi không có lỗi không chứng minh độ chắc chắn tuyệt đối.

Chỉ có khoảng1,52 giờ ADL development nên bước nhảy một cảnh báo đã là0,658/h. Các điểm tại0,1/0,25/0,5/h có thể cùng cho0FA quan sát; không phải đã chứng minh đạt các mức đó. Các window chồng lấn không độc lập. Thời gian laboratory là clock100Hz danh nghĩa, chưa phải độ trễ thực trên thiết bị. Test đã từng được xem: đây là benchmark cố định, không phải xác nhận mới hoàn toàn.

## 2. Rà toàn bộ 7 lần bỏ sót và 1 báo nhầm

| Trial | Người / hoạt động | Chẩn đoán từ score OOF | Max score trong khoảng phát hiện | Chênh score−ngưỡng | Trial đúng đối chiếu |
|---|---|---|---:|---:|---|
| [S12T22R01](figures/S12T22R01.png) | SA12 / F01 | no_crossing_in_detection_interval | 0.966360 | -0.018413 | S10T22R01 |
| [S22T15R01](figures/S22T15R01.png) | SA22 / ADL15 | adl_false_alarm | N/A | N/A | S14T15R01 |
| [S31T33R01](figures/S31T33R01.png) | SA31 / F14 | no_crossing_in_detection_interval | 0.983978 | -0.000795 | S14T33R01 |
| [S36T21R01](figures/S36T21R01.png) | SA36 / F02 | no_crossing_in_detection_interval | 0.249136 | -0.735636 | S10T23R01 |
| [S36T32R01](figures/S36T32R01.png) | SA36 / F13 | no_crossing_in_detection_interval | 0.982091 | -0.002682 | S10T34R01 |
| [S36T34R01](figures/S36T34R01.png) | SA36 / F15 | no_crossing_in_detection_interval | 0.948508 | -0.036265 | S14T34R01 |
| [S36T37R01](figures/S36T37R01.png) | SA36 / F16 | no_crossing_in_detection_interval | 0.945355 | -0.039418 | S14T37R01 |
| [S37T21R01](figures/S37T21R01.png) | SA37 / F02 | no_crossing_in_detection_interval | 0.892389 | -0.092384 | S10T23R01 |

Ngưỡng giữ nguyên: 0.98477275965882582. Đếm chẩn đoán: {'no_crossing_in_detection_interval': 7, 'adl_false_alarm': 1}. Max score tính trên tất cả window kết thúc trong [onset, impact+100], bao gồm IGNORE; không chỉ các window FALL dùng cho loss.
Cả7 lần bỏ sót đều không có score vượt threshold trong khoảng hợp lệ, không phải lỗi cảnh báo trễ. S31T33R01 chỉ cách ngưỡng khoảng0,000795, S36T32R01 khoảng0,002682; S36T21R01 thấp hơn nhiều (max score≈0,249). Việc một số ca gần ngưỡng không đủ lý do hạ ngưỡng theo từng ca; phải xét đánh đổi báo nhầm trên toàn development. Score chưa phải xác suất đã hiệu chuẩn.
SA36: bỏ sót 4/21 lần ngã, recall 80.95%; chiếm4/7 lỗi toàn bộ. Đây là tập trung lỗi theo người, chưa chứng minh do hướng gắn, nhãn hoặc gyro. Cần phân biệt tỷ lệ lỗi của người đó với số lỗi tuyệt đối. Xem [bảng theo người](by_subject.csv).
Cảnh báo nhầm duy nhất: S22T15R01, ADL15 (collapse into chair), cạnh cảnh báo tại frame949, max score0,987973 so với threshold0,984773. Các lỗi và trial đúng được vẽ đủ sáu kênh, norm và score theo frame; trial đối chiếu là cùng hoạt động, người khác, kết quả đúng, chọn trial ID nhỏ nhất để tránh cherry-pick. Một trial đúng chỉ là minh họa, không đại diện mọi người.
Đồ thị giải thích trực tiếp vị trí score dưới/vượt ngưỡng và thời điểm cảnh báo. Hai trial có thể thuộc hai fold với model train khác nhau; đối chiếu là mô tả, không phải kiểm chứng cô lập tác động của người. Khác biệt tín hiệu giữa hai người chỉ tạo giả thuyết. Không tự sửa annotation hoặc suy ra tư thế/chấn động cụ thể từ IMU; chưa có video để xác minh nguyên nhân. Không có trọng số model từng fold được lưu nên không thể phân rã đóng góp feature OOF; model fit23 người không được dùng thay model OOF để giải thích lỗi.

## 3. Model phức tạp hơn và acc-only có giúp không?

| Model, tại threshold đã khóa của nó | Event recall | Window P/R/F1 | Cứu / mất so với LR C0,1 |
|---|---:|---|---:|
| lr_C0.1 | 98.46% | 99.89% / 95.29% / 97.53% | 0 / 0 |
| lr_C1.0 | 97.37% | 99.88% / 94.52% / 97.13% | 0 / 5 |
| lr_C10.0 | 98.25% | 99.88% / 94.63% / 97.18% | 3 / 4 |
| dt_d3_l10 | 3.07% | 94.44% / 1.86% / 3.66% | 0 / 435 |
| dt_d3_l30 | 17.32% | 98.63% / 15.79% / 27.22% | 2 / 372 |
| dt_d5_l10 | Không có điểm phát hiện ngã đạt ngân sách1FA/h | N/A tại điểm hợp lệ | N/A |
| dt_d5_l30 | 53.95% | 99.78% / 48.79% / 65.54% | 4 / 207 |
| dt_d8_l10 | Không có điểm phát hiện ngã đạt ngân sách1FA/h | N/A tại điểm hợp lệ | N/A |
| dt_d8_l30 | 93.86% | 99.87% / 86.62% / 92.78% | 4 / 25 |
| rf_d5_l10 | 93.20% | 99.87% / 85.96% / 92.40% | 3 / 27 |
| rf_d5_l30 | 94.96% | 99.88% / 88.93% / 94.08% | 4 / 20 |
| rf_d10_l10 | 96.27% | 99.88% / 90.79% / 95.12% | 4 / 14 |
| rf_d10_l30 | 92.76% | 99.87% / 86.07% / 92.46% | 4 / 30 |
| acc_threshold | 33.11% | 99.33% / 32.35% / 48.80% | 1 / 299 |

Chênh LR C0,1 so với C1: 1.10 điểm phần trăm. Khoảng chênh C1−C0,1 theo bootstrap người: [-0.02466367713004484, 0.0]. Khoảng còn chạm0 nên chưa khẳng định vượt trội chắc chắn. Đây là so sánh đã lựa chọn trên development, CI chỉ có điều kiện trên prediction cố định.
Ví dụ trade-off giữa model: RF depth10/leaf10 cứu4 ca baseline bỏ sót nhưng mất14 ca baseline phát hiện được, nên net−10; cây depth8/leaf30 cứu4 nhưng mất25. Chỉ nhìn các ca được cứu sẽ đánh giá sai lợi ích. Danh sách ghép cặp đầy đủ nằm trong model_pairs.json.
LR C0,1 có score OOF giống hệt ở seed42/43/44. Điều đó phù hợp độ xác định của solver/cấu hình; không chứng minh ổn định giữa người hoặc miền dữ liệu. Tree có seed không đạt điểm vận hành, forest có recall kém hơn trong grid hiện tại. Không kết luận mọi loại cây/forest hoặc model sâu đều kém.

**Ablation phải so cùng C trước:**

| Cấu hình chẩn đoán | Phát hiện /456 | Window P / R / F1 | FA / giờ ADL |
|---|---:|---|---:|
| Acc-only C1 | 451/456 | 99.89% / 96.05% / 97.93% | 1/1.5187 |
| Gyro-only C1 | 282/456 | 99.81% / 58.55% / 73.81% | 1/1.5187 |

- Acc-only C1 vs full6channel C1: cứu 7 sự kiện, mất 0 sự kiện, net 7; paired95% chênh recall [0.0021929824561403508, 0.032397408207343416].
- Acc-only C1 vs baseline C0,1: cứu 3 sự kiện, mất 1 sự kiện, net 2; đồng thời thay cả nhóm feature và C nên chưa tách được tác động.
- Gyro-only C1 recall 61.84%; kết quả hiện tại cho thấy gyro riêng yếu hơn trong bài toán/configuration này, không chứng minh gyro vô ích khi kết hợp hoặc trên phần cứng thật.
Giữ nguyên cả hai cảm biến khi thu test phần cứng. Acc-only là hướng xác nhận đáng ưu tiên sau bước thử thiết bị; chưa được train lại/chọn lại baseline trong giai đoạn phân tích này. Danh sách từng sự kiện cứu/mất nằm trong [sensor_comparison.json](sensor_comparison.json) và [sensor_event_outcomes.csv](sensor_event_outcomes.csv). Không có score window ablation đã lưu để vẽ hoặc quy đóng góp gyro từng thời điểm; ghi thiếu thay vì train lại.

**Đường đánh đổi từ score development đã lưu (không cập nhật threshold):**

| Ngân sách FA/h | Recall quan sát | FA/h quan sát | Threshold mô tả |
|---:|---:|---:|---:|
| 0.1 | 98.25% | 0.000 | 0.988174433 |
| 0.25 | 98.25% | 0.000 | 0.988174433 |
| 0.5 | 98.25% | 0.000 | 0.988174433 |
| 1.0 | 98.46% | 0.658 | 0.984772760 |
| 2.0 | 99.56% | 1.317 | 0.945355141 |

Cùng một điểm0FA cho nhiều ngân sách phản ánh thời lượng âm ngắn. Nới ngân sách lên2/h quan sát có thể bắt thêm sự kiện nhưng cũng tăng cảnh báo; đây là mô tả, không phải quyết định thay ngưỡng.

## 4. OnField và phần cứng: bằng chứng/giới hạn

OnField: 30 cảnh báo /54.88 giờ, rate=0.547/h, cận trên Poisson95%=0.741/h dưới giả định mô hình Poisson. Không có nhãn ngã để tính recall; không thể suy ra precision cảnh báo trong đời sống.
22/30 cảnh báo (73,33%) thuộc file20241106_1000.csv trên11,45235giờ, xấp xỉ1,921/h. Giữ đủ18file và ghi count/rate riêng; không loại file1000 hoặc gọi đây là một người đã xác minh. Nhãn âm/ID của nguồn chưa được đối chiếu độc lập; mọi điều tra chỉ mô tả, không tuning theo OnField rồi gọi nó là test mới.
Phần cứng hiện có: 4000 mẫu, dt=9994–10007µs, tần suất host trung bình 100.000Hz, gap seq=0, dữ liệu hữu hạn=True. Metadata ground_truth=unknown, trigger synthetic_test; không phải một lần ngã có nhãn. Vị trí abdomen_waist là metadata cố định; hướng sensor_frame_unmapped chưa có ánh xạ tin cậy sang nguồn lưng dưới.
CSV và nhịp đo có thể kiểm tra sơ bộ; chưa đủ nhãn/hướng đeo để chấm recall hoặc FA/h phần cứng. Chưa có nga_01/nga_02 hay phiên hoạt động có nhãn trong data project. Chi phí host đã đo chỉ là số trên máy tính; RAM, inference latency và truyền tin ESP32 vẫn NOT MEASURED.

## 5. Hướng làm tiếp theo, theo thứ tự

**Ưu tiên1 — thử nhanh baseline đã khóa với dữ liệu phần cứng có nhãn.**
- Bằng chứng: model có recall OOF cao nhưng có tập trung lỗi theo người; chưa có dữ liệu prototype đủ nhãn/vị trí đeo, nên thiếu bước xác nhận luồng đo→dự đoán.
- Đầu vào: CSV100Hz sáu kênh, ảnh/ghi chú vị trí và chiều đeo, vài phút hoạt động bình thường, 1–2 lần ngã có kiểm soát chỉ khi điều kiện an toàn phù hợp, mốc thời gian ngã đồng bộ. Theo [yêu cầu bàn giao](../../docs/YEU_CAU_BO_TEST_PHAN_CUNG.md). Giữ log gốc và không xem trigger là nhãn.
- Phép thử: xác minh units, clock/gap, hướng gắn trước; giữ window100/stride50, preprocessing/model/threshold và cảnh báo như baseline; đối chiếu score/cảnh báo với sự kiện có nhãn. Hướng trục chưa xác minh thì ghi hạn chế, không tự xoay để tối đa score.
- Quyết định: dữ liệu sai/thiếu thì xử lý khâu đo/annotation trước. Dữ liệu hợp lệ nhưng model bỏ sót/báo nhầm thì mở phân tích lệch miền và thu thêm dữ liệu độc lập, không chỉnh ngưỡng theo1–2 lần thử. Phát hiện đúng mà không có báo nhầm chỉ xác nhận test nhỏ đó, chưa chứng minh độ chính xác tổng thể.

**Sau đó2 — thí nghiệm xác nhận acc-only và bộ đặc trưng trên development.**
- Giả thuyết: bộ20feature acc có thể giảm lỗi theo người so với full40feature, không nhất thiết cần model sâu. Khóa cùng C/grid/5fold theo người và metric trước khi chạy, giữ dữ liệu ngoài development để xác nhận.
- Ủng hộ khi có lợi ích sự kiện được ghép cặp, không làm xấu FA/h/độ trễ và không chỉ do một người; CI chạm0 hoặc lợi ích không ổn định thì kết luận chưa đủ bằng chứng và giữ baseline. Đây là thí nghiệm đề xuất, chưa thực hiện.

**Sau đó3 — chỉ cân nhắc model chuỗi nếu có bằng chứng về thứ tự thời gian.**
- Cần chứng minh lỗi còn lại liên quan thông tin trình tự bị mất bởi thống kê, sau khi đã loại trừ units/axes/nhãn/miền dữ liệu. Các xung trong hình riêng lẻ chưa chứng minh điều đó.
- So sánh model chuỗi nhỏ theo cùng protocol và đo tài nguyên ESP32; nếu không cải thiện trade-off hoặc chưa đủ bằng chứng thì giữ model đơn giản. Chưa có lý do để chọn sẵn CNN.

## Tái lập và phạm vi

Chạy từ root project: `python tools/datasets/analyze_baseline_results.py`. Chỉ đọc score/model/result đã có; không gọi fit, không quét ngưỡng mới, không cập nhật selection_lock. Nguồn audit lấy từ manifest của dataset export. Đọc score CSV với float_precision=round_trip và đối chiếu NPZ để không lật quyết định ở ngưỡng trùng score.
Các file gốc và model/threshold được băm trước/sau; [verification.json](verification.json) ghi hash nguồn, đầu ra, số lỗi và đối chiếu counts. Điểm vận hành trong threshold_tradeoff.csv chỉ mô tả lại đường score đã lưu; không đổi baseline. Khoảng tin cậy recall/chênh recall ở dạng tỷ lệ0–1; nhân100 để đổi sang phần trăm/điểm phần trăm. Các khoảng tin cậy không được dùng để tuyên bố xác nhận độc lập sau tìm kiếm model.
Đầu ra: metric_summary, error_cases/case_windows/case_comparisons, by_subject/by_activity, model_comparison/model_pairs, sensor_comparison, seed_stability, OnField theo file, hardware_readiness và figures. Thiếu dữ liệu phần cứng là kết luận về mức sẵn sàng, không phải phần phân tích còn dang dở.
