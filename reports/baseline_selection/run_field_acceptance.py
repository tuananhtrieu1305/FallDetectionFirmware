import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'tools/datasets')
from select_baseline import portable_predict
from onfield_metrics_v11 import evaluate_file
from run_metrics_v11 import dump,sha
out=Path('reports/baseline_selection');source=Path(json.loads(Path('data/processed/univrfall_v1/manifest.json').read_text())['source']);raw=source.parent/'raw/univrfall'
model=json.loads((out/'selected_model.json').read_text());manifest=json.loads((raw/'full_download_manifest.json').read_text());folder=out/'onfield';folder.mkdir(exist_ok=True);results=[]
for name,e in sorted(manifest.items()):
    if '/OnField/' not in name or not name.endswith('.csv'):continue
    assert sha(e['file'])==e['sha256']
    m=evaluate_file(e['file'],model,predictor=lambda f:portable_predict(model,f))
    check=evaluate_file(e['file'],model,chunksize=37123,predictor=lambda f:portable_predict(model,f))
    assert m==check,name
    m.update(source_member=name,raw_sha256=e['sha256'],model_sha256=sha(out/'selected_model.json'),chunk_invariance='PASS')
    dump(folder/(Path(name).stem+'.json'),m);results.append(m)
    print(Path(name).name,m['false_alarms'],flush=True)
assert len(results)==18
hours=sum(m['adl_monitored_nominal_hours'] for m in results);alarms=sum(m['false_alarms'] for m in results)
dump(folder/'summary.json',dict(files=18,alarms=alarms,hours=hours,alarms_per_source_negative_hour=alarms/hours,threshold=model['threshold'],threshold_retuned=False,
    active_fraction=sum(m['alarm_active_fraction']*m['adl_monitored_nominal_hours'] for m in results)/hours,
    chunk_invariance_all_18='PASS',label_status='Source-negative, unverified labels and participant identity; nominal time',
    per_file=[dict(source_member=m['source_member'],alarms=m['false_alarms'],hours=m['adl_monitored_nominal_hours']) for m in results]))
