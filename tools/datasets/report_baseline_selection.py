"""Render baseline comparison from locked, verified artifacts."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from select_baseline import ranking
from run_metrics_v11 import dump


def run(out):
    rows=json.loads((out/'development_results.json').read_text());assert len(rows)==14
    winner=max([r for r in rows if r['eligible']],key=ranking)
    lock=json.loads((out/'selection_lock.json').read_text());assert winner['id']==lock['winner']['id']
    chosen=json.loads((out/'cache'/(winner['id']+'_metrics.json')).read_text());old=json.loads((out/'cache/lr_C1.0_metrics.json').read_text())
    a=pd.DataFrame(chosen['per_trial']);b=pd.DataFrame(old['per_trial'])
    merged=a[['trial_id','subject_id','events','detected']].merge(b[['trial_id','detected']],on='trial_id',suffixes=('_new','_old'))
    groups=merged.groupby('subject_id')[['events','detected_new','detected_old']].sum();rng=np.random.default_rng(42)
    sums=groups.to_numpy()[rng.integers(len(groups),size=(10000,len(groups)))].sum(axis=1)
    paired=dict(delta_event_recall=winner['recall']-old['recall'],paired_subject_bootstrap_95=np.percentile((sums[:,1]-sums[:,2])/sums[:,0],[2.5,97.5]).tolist(),limitation='Selected development comparison; conditional predictions; does not account for selection optimism')
    dump(out/'paired_comparison.json',paired)
    test=json.loads((out/'test_metrics.json').read_text());field=json.loads((out/'onfield/summary.json').read_text());ablation=json.loads((out/'sensor_ablation.json').read_text())
    eligible=sorted([r for r in rows if r['eligible']],key=ranking,reverse=True)
    fig,ax=plt.subplots(figsize=(12,6));ax.barh([r['id'] for r in eligible],[r['recall']*100 for r in eligible]);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('Development Event recall (%) at <=1 FA/nominal hour');fig.tight_layout();fig.savefig(out/'plots/model_comparison.png',dpi=130);plt.close(fig)
    errors=a[(a.events.eq(1)&a.detected.eq(0))|a.false_alarms.gt(0)];errors.to_csv(out/'selected_oof_errors.csv',index=False)
    source=Path(json.loads(Path('data/processed/univrfall_v1/manifest.json').read_text())['source'])
    records=json.loads((source/'recording_manifest.json').read_text())
    fig,axs=plt.subplots(max(1,len(errors)),1,figsize=(12,max(3,len(errors)*2.6)),squeeze=False)
    for ax,row in zip(axs.ravel(),errors.itertuples()):
        r=records[row.recording_id]
        with np.load(source/r['recording']) as data:v=data['values'];frame=data['frame']
        ax.plot(frame,np.linalg.norm(v[:,:3],axis=1),label='acc norm m/s2')
        ax.plot(frame,np.linalg.norm(v[:,3:],axis=1),label='gyro norm rad/s')
        if r['event']:
            ax.axvline(r['event']['onset'],c='orange');ax.axvline(r['event']['impact'],c='red')
        for alarm in chosen['alarms']:
            if alarm['recording_id']==row.recording_id:ax.axvline(alarm['frame'],c='purple',ls='--')
        ax.set_title(r['trial_id']+' '+r['activity_key']);ax.legend(fontsize=6)
    fig.tight_layout();fig.savefig(out/'plots/selected_oof_errors.png',dpi=120);plt.close(fig)
    text=['# Kết quả phân tích và lựa chọn baseline','',f'**Chọn {winner["id"]}: Logistic Regression C=0.1 + StandardScaler + balanced weights + 40 đặc trưng thống kê.** Ngưỡng {winner["threshold"]:.17g}, window100×6, stride50. Đây là tốt nhất trong nhóm đã khóa, chưa phải tối ưu cho mọi model hoặc phần cứng.',
    '', '## Cơ sở từ dữ liệu',
    'EDA ghi trước thí nghiệm: 23 người, 916 trial, 456 lần ngã; 16.424 window gồm 2.238 IGNORE; 1,5187 giờ ADL danh nghĩa. Đặc trưng cực trị/biến thiên của accel và gyro khác biệt mô tả giữa lớp, tạo cơ sở thử model thống kê có regularization trước model chuỗi sâu. Biểu đồ median/trial không chứng minh tách lớp hoàn toàn.',
    'Window chồng lấn không độc lập; SA10–SA12 chỉ còn trial ngã nên có nguy cơ confounding giữa người và nhãn. Tín hiệu hữu hạn, không có gap frame ở development; clock100Hz vẫn danh nghĩa, biên độ gần4g và hướng gắn prototype chưa xác minh. Xem [EDA.md](EDA.md), [trace sáu kênh ví dụ](plots/six_channels_F03.png), [phân bố theo người](features_by_subject.csv).',
    '', '## So sánh cùng điều kiện', '| Cấu hình | Phát hiện /456 | Recall | FA/h | P95 trễ danh nghĩa |','|---|---:|---:|---:|---:|']
    for r in sorted(rows,key=lambda r:r['id']):
        if r['eligible']:text.append(f'| {r["id"]} | {r["detected"]} | {r["recall"]:.2%} | {r["false_alarms_per_nominal_hour"]:.3f} | {r["p95_delay_nominal_s"]:.3f}s |')
        else:text.append(f'| {r["id"]} | — | Không có ngưỡng phát hiện ngã đạt ≤1FA/h | — | — |')
    text+=['',f'Ngưỡng max độ lớn gia tốc là mốc vật lý; LR kiểm tra tổ hợp tuyến tính, cây kiểm tra luật phi tuyến, forest kiểm tra lợi ích kết hợp cây. Tất cả dùng cùng phân chia theo người, cùng window và cơ chế cảnh báo. Cây/forest không cải thiện recall so với LR ở ngân sách1/h trong bộ đặc trưng này.',
    f'LR C=0.1 phát hiện {winner["detected"]}/456, bỏ sót {winner["missed"]}, có {winner["false_alarms"]} báo nhầm trên {winner["adl_monitored_nominal_hours"]:.4f} giờ ADL. So với C=1, chênh lệch recall {paired["delta_event_recall"]*100:.2f} điểm phần trăm, khoảng bootstrap theo người {paired["paired_subject_bootstrap_95"]}. Đây là kết quả lựa chọn development, không phải kiểm định độc lập; CI chỉ có điều kiện trên prediction cố định.',
    'Seed42/43/44: [seed_stability.csv](seed_stability.csv). LR giữ nguyên kết quả; cây có seed không có điểm vận hành khả thi. Không chọn seed theo test.',
    '', '## Ablation và lỗi còn lại',
    f'Chẩn đoán LR C=1: acc-only recall {ablation["acc_only"].get("recall"):.2%}, gyro-only {ablation["gyro_only"].get("recall"):.2%}. Acc-only cao hơn nhóm40feature cho thấy cần kiểm chứng thêm lựa chọn cảm biến/đặc trưng trước khi tăng độ phức tạp. Đây là chẩn đoán ngoài grid chính; chưa tự thay baseline được khóa. Không suy ra nên bỏ gyro trên phần cứng thật chỉ từ dataset này.',
    'Trong 7 lần ngã bỏ sót, 4 thuộc SA36; một cảnh báo nhầm là S22T15R01 (ADL15, collapse into chair). Đồ thị lỗi có xung gia tốc nhưng gyro tương đối thấp ở một số ca; đây là quan sát, chưa chứng minh nguyên nhân. Nên kiểm tra giả thuyết trọng số gyro/đặc trưng và khả năng khái quát theo người trước khi tăng độ phức tạp. ',
    'Xem [các lỗi OOF](selected_oof_errors.csv), [đồ thị lỗi](plots/selected_oof_errors.png), [tương quan](plots/feature_correlation.png), [dịch chuyển theo người](plots/subject_feature_shift.png), [trước/sau impact](pre_post_impact.csv). Không suy ra nguyên nhân tư thế từ IMU đơn thuần. Nhóm lỗi theo người/hoạt động nằm trong development_by_subject_id.csv và development_by_activity_key.csv.',
    '', '## Benchmark sau khóa lựa chọn',
    f'Test: {test["detected"]}/{test["events"]}, FA={test["false_alarms"]} trên {test["adl_monitored_nominal_hours"]:.4f} giờ ADL; median/P95 delay={test["median_delay_nominal_s"]}/{test["p95_delay_nominal_s"]}s danh nghĩa. Cận trên Poisson95% của FA/h là {test["poisson_upper_95_per_hour"]:.2f}; thời lượng âm quá ngắn để kết luận báo nhầm thực thấp.',
    f'OnField đủ18file: {field["alarms"]}/{field["hours"]:.2f} giờ, {field["alarms_per_source_negative_hour"]:.3f} cảnh báo/source-negative hour. Không retune ngưỡng; đủ18file khớp giữa chunks100000/37123. Nhãn âm/ID người chưa được xác minh độc lập.',
    'Test/OnField từng được xem trong baseline trước; đây là benchmark cố định, chưa phải dữ liệu xác nhận cuối mới. Chi phí máy tính: [host_cost.json](host_cost.json); RAM và latency ESP32 NOT MEASURED.',
    '', '## Quyết định',
    'Giữ LR C=0.1 +40feature làm baseline chính của vòng so sánh. Ưu tiên xác nhận acc-only và thu ADL có nhãn từ đúng phần cứng/vị trí đeo để kiểm tra lệch miền. Chỉ thử CNN khi lỗi còn lại tạo giả thuyết rõ về lợi ích học thứ tự thời gian; hiện chưa có lý do bắt buộc chuyển CNN.']
    (out/'REPORT.md').write_text('\n'.join(line.rstrip() for line in text)+'\n',encoding='utf-8')
    (out/'README.md').write_text('''# Phân tích dữ liệu và chọn baseline

- [Kết luận và bảng so sánh](REPORT.md), [EDA trước train](EDA.md)
- [CSV so sánh](comparison.csv), [prediction OOF](oof_predictions.csv)
- [Khóa thí nghiệm](experiment_lock.json), [khóa lựa chọn](selection_lock.json), [model JSON](selected_model.json)
- [Seed stability](seed_stability.csv), [ablation cảm biến](sensor_ablation.json), [so sánh theo người](paired_comparison.json)
- [Test](test_metrics.json), [OnField riêng](onfield/summary.json), [chi phí host](host_cost.json)
- [Nghiệm thu](completion_audit.json), [test](tests.txt), [coverage](test_coverage.json)

Chạy từ root project, lấy SOURCE từ trường source trong data/processed/univrfall_v1/manifest.json:

```powershell
python tools/datasets/analyze_baseline_data.py --source SOURCE
python tools/datasets/select_baseline.py --source SOURCE
python tools/datasets/diagnose_baseline_data.py --source SOURCE
python reports/baseline_selection/run_field_acceptance.py
python tools/datasets/report_baseline_selection.py
python tools/datasets/verify_baseline_selection.py --source SOURCE
python -m unittest discover -s tools/datasets -p 'test_*.py'
```

Khi đọc score CSV để đếm lại ở threshold trùng score, dùng `pd.read_csv(path, float_precision="round_trip")`; hoặc đọc score NPZ giữ float64 nguyên vẹn trong cache. Parser mặc định có thể làm đổi chữ số cuối và lật quyết định đúng tại ngưỡng.
Cache score/fold/threshold curve tồn tại trên đĩa, bị bỏ qua trong Git và có thể tạo lại. Model JSON xuất nội bộ đã đối chiếu prediction với sklearn. Chưa train CNN.
''',encoding='utf-8')
    return winner

if __name__=='__main__':print(run(Path('reports/baseline_selection'))['id'])
