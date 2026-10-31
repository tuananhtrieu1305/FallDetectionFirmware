"""Development-only EDA performed before the baseline comparison."""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from benchmark_univrfall import features
from run_metrics_v11 import dump,sha

NAMES=[f'{stat}_{channel}' for stat in ['mean','std','min','max','rms'] for channel in ['ax','ay','az','gx','gy','gz','acc_norm','gyro_norm']]

def run(source,out):
    out.mkdir(parents=True,exist_ok=True);plots=out/'plots';plots.mkdir(exist_ok=True)
    records=[dict(r,recording_id=j) for j,r in enumerate(json.loads((source/'recording_manifest.json').read_text())) if r['partition']!='test']
    ids={r['recording_id'] for r in records}
    index=pd.read_csv(source/'window_index_100.csv');mask=index.recording_id.isin(ids).to_numpy();index=index[mask].reset_index(drop=True)
    with np.load(source/'windows_100.npz') as d:x=d['X'][mask].copy()
    assert len(index)==len(x) and all(r['partition']!='test' for r in records)
    f=features(x);y=index.y.to_numpy();valid=y>=0
    table=pd.DataFrame(records).drop(columns=['event']);table['events']=[int(bool(r['event'])) for r in records]
    table['adl_hours']=[max(0,r['rows']-99)/100/3600 if not r['event'] else 0 for r in records]
    table.to_csv(out/'development_trials.csv',index=False)
    for field in ['subject_id','partition','activity_key']:
        agg=table.groupby(field).agg(trials=('trial_id','size'),events=('events','sum'),raw_rows=('rows','sum'),adl_hours=('adl_hours','sum'))
        counts=pd.crosstab(index[field],index.y).rename(columns={-1:'IGNORE',0:'NON_FALL',1:'FALL'})
        agg.join(counts).to_csv(out/f'counts_by_{field}.csv')
    raw_checks=[];temporal=[];examples={}
    fig,axes=plt.subplots(11,4,figsize=(18,31));axes=axes.ravel()
    for r in records:
        with np.load(source/r['recording']) as d:v=d['values'];frames=d['frame']
        raw_checks.append(dict(trial_id=r['trial_id'],subject_id=r['subject_id'],rows=len(v),finite=bool(np.isfinite(v).all()),
            gaps=int((np.diff(frames)!=1).sum()),max_axis_acc_g=float(np.abs(v[:,:3]).max()/9.80665),
            fraction_axes_near4g=float((np.abs(v[:,:3])>=3.99*9.80665).mean()),max_axis_gyro_dps=float(np.abs(v[:,3:]).max()*180/np.pi)))
        if r['event']:
            impact=r['event']['impact'];pre=v[(frames>=impact-100)&(frames<impact)];post=v[(frames>=impact)&(frames<=impact+100)]
            temporal.append(dict(trial_id=r['trial_id'],subject_id=r['subject_id'],activity_key=r['activity_key'],
                pre_acc_rms=float(np.sqrt((pre[:,:3]**2).sum(axis=1).mean())) if len(pre) else None,
                post_acc_rms=float(np.sqrt((post[:,:3]**2).sum(axis=1).mean())) if len(post) else None))
        if r['activity_key'] not in examples:
            ax=axes[len(examples)];examples[r['activity_key']]=r['trial_id']
            ax.plot((frames-frames[0])/100,np.linalg.norm(v[:,:3],axis=1),lw=.7,label='acc norm m/s2')
            ax.plot((frames-frames[0])/100,np.linalg.norm(v[:,3:],axis=1),lw=.7,label='gyro norm rad/s')
            if r['event']:
                ax.axvline((r['event']['onset']-frames[0])/100,c='orange');ax.axvline((r['event']['impact']-frames[0])/100,c='r')
            ax.set_title(r['activity_key']+' '+r['trial_id']);ax.set_xlabel('nominal seconds')
    for ax in axes[len(examples):]:ax.set_visible(False)
    fig.tight_layout();fig.savefig(plots/'activity_traces.png',dpi=120);plt.close(fig)
    pd.DataFrame(raw_checks).to_csv(out/'quality_by_trial.csv',index=False)
    pd.DataFrame(temporal).to_csv(out/'pre_post_impact.csv',index=False)
    # One observation per trial for descriptive feature plots, not overlapping windows.
    ff=pd.DataFrame(f,columns=NAMES);ff['recording_id']=index.recording_id;ff['y']=y
    trial=ff[valid].groupby(['recording_id','y'])[NAMES].median().reset_index()
    trial.to_csv(out/'feature_medians_by_trial.csv',index=False)
    corr=trial[NAMES].corr(method='spearman');corr.to_csv(out/'feature_spearman.csv')
    fig,ax=plt.subplots(figsize=(12,10));im=ax.imshow(corr,vmin=-1,vmax=1,cmap='coolwarm');ax.set_xticks(range(40),NAMES,rotation=90,fontsize=6);ax.set_yticks(range(40),NAMES,fontsize=6);fig.colorbar(im);fig.tight_layout();fig.savefig(plots/'feature_correlation.png',dpi=130);plt.close(fig)
    fig,axs=plt.subplots(2,4,figsize=(14,7))
    for ax,name in zip(axs.ravel(),['max_acc_norm','std_acc_norm','rms_gyro_norm','max_gyro_norm','std_ax','std_ay','std_az','mean_acc_norm']):
        values=[trial.loc[trial.y==label,name] for label in [0,1]];ax.boxplot(values,tick_labels=['NON_FALL','FALL'],showfliers=False);ax.set_title(name)
    fig.tight_layout();fig.savefig(plots/'feature_distributions.png',dpi=130);plt.close(fig)
    # Existing errors are OOF development only; do not inspect fixed test errors.
    old=pd.read_csv('reports/metrics_v1_1/events.csv');old=old[old.split=='development']
    errors=old[(old.events.eq(1)&old.detected.eq(0)) | old.false_alarms.gt(0) | old.early.gt(0) | old.late.gt(0)]
    errors.to_csv(out/'existing_oof_error_trials.csv',index=False)
    for group,columns in [('accelerometer',NAMES[:3]),('gyroscope',NAMES[3:6])]:pass
    summary=dict(subjects=len({r['subject_id'] for r in records}),trials=len(records),events=sum(bool(r['event']) for r in records),
        windows=len(index),window_labels={str(k):int(v) for k,v in index.y.value_counts().items()},
        adl_hours=float(table.adl_hours.sum()),raw_rows=int(table.rows.sum()),all_finite=all(r['finite'] for r in raw_checks),
        gaps=sum(r['gaps'] for r in raw_checks),max_axis_acc_g=max(r['max_axis_acc_g'] for r in raw_checks),
        max_axis_gyro_dps=max(r['max_axis_gyro_dps'] for r in raw_checks),example_trials=examples,
        fall_only_subjects=sorted(set(table.subject_id)-set(table.loc[table.events.eq(0),'subject_id'])),
        source_manifest_sha256=sha(source/'recording_manifest.json'),split_sha256=sha(source/'splits.json'),
        development_index_sha256=__import__('hashlib').sha256(index.to_csv(index=False).encode()).hexdigest(),
        features='Fixed historical 40 features; no feature selection fitted on full development',
        test_used=False,onfield_used=False)
    dump(out/'eda_summary.json',summary)
    text=f'''# Phân tích development trước chọn baseline

Có {summary['subjects']} người, {summary['trials']} trial, {summary['events']} sự kiện ngã, {summary['windows']} window và {summary['adl_hours']:.4f} giờ ADL danh nghĩa. Window chồng lấn không phải quan sát độc lập. Người chỉ có trial ngã sau quarantine: {summary['fall_only_subjects']}; cần theo dõi confounding giữa người và nhãn.

IMU hữu hạn: {summary['all_finite']}; gap frame: {summary['gaps']}. Accel tối đa theo trục {summary['max_axis_acc_g']:.3f}g, gyro {summary['max_axis_gyro_dps']:.2f} dps. Không cắt/xóa tín hiệu cực trị; timestamp 100Hz chỉ danh nghĩa. Chất lượng nhãn/đơn vị/split đã audit ở dataset v1; chưa xác minh frame hướng đeo prototype.

Biểu đồ phân bố đặc trưng dùng median từng trial/lớp để giảm chi phối từ window chồng lấn; không dùng p-value với giả định window độc lập. Cùng trial có thể có cả pre-fall âm và impact dương; bảng không coi chúng độc lập. Biểu đồ trace chọn trial đầu tiên theo thứ tự manifest cho mỗi hoạt động, không chọn theo điểm dự đoán; chỉ là minh họa, không đại diện toàn bộ người.

## Quan sát → giả thuyết → ứng viên

- Các trace có đoạn va chạm/biến thiên biên độ: kiểm tra ngưỡng max độ lớn gia tốc làm mốc vật lý đơn giản. Hoạt động thường cũng có xung lớn nên không mặc định biên độ đủ phân biệt.
- Có 40 thống kê biên độ/biến thiên và tương quan giữa chúng: Logistic Regression có regularization kiểm tra tổ hợp tuyến tính, ít tham số, giữ đối chiếu baseline hiện có.
- Phân bố FALL/NON_FALL vẫn có thể chồng lấn và phụ thuộc trục/hoạt động: cây nhỏ kiểm tra luật phi tuyến/tương tác; Random Forest giới hạn độ sâu kiểm tra lợi ích kết hợp cây so với cây đơn. Không suy ra phi tuyến tốt hơn chỉ từ hình ảnh.
- Mẫu gồm 23 người, thời lượng âm hạn chế, nhiều window phụ thuộc: giới hạn độ sâu/min leaf, không chuyển sang mạng sâu trước khi có bằng chứng từ so sánh.

Khóa nhóm ứng viên: ngưỡng gia tốc + 13 cấu hình (3 LR, 6 cây, 4 forest), cùng 40 feature và cùng 5 fold. Mean/std và trọng số chỉ fit trên train của fold. Không chọn đặc trưng từ toàn bộ development rồi gọi OOF là ước lượng độc lập; vòng này giữ feature cố định. So sánh ablation acc-only/gyro-only mang tính chẩn đoán, không mở rộng tìm kiếm theo test.

## Cần đọc cùng

- [Thống kê theo người](counts_by_subject_id.csv), [theo fold](counts_by_partition.csv), [theo hoạt động](counts_by_activity_key.csv).
- [Chất lượng từng trial](quality_by_trial.csv), [trước/sau impact](pre_post_impact.csv).
- [Phân bố đặc trưng](plots/feature_distributions.png), [tương quan](plots/feature_correlation.png), [trace hoạt động](plots/activity_traces.png).
- [Lỗi OOF baseline hiện tại](existing_oof_error_trials.csv); không dùng lỗi test/OnField để thiết kế model.

Báo cáo này và checksum được tạo trước vòng so sánh mới. EDA không xác định được model tốt nhất; thí nghiệm development kiểm chứng các giả thuyết trên. Không có kết luận dự đoán ngã trước impact.
'''
    (out/'EDA.md').write_text(text,encoding='utf-8');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('reports/baseline_selection'));a=p.parse_args();print(json.dumps(run(a.source,a.out),indent=2))
