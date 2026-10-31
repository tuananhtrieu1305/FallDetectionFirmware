import json
import tempfile
import unittest
from pathlib import Path
import pandas as pd

class ReportContract(unittest.TestCase):
    def test_report_artifacts_and_test_isolation(self):
        from run_metrics_v11 import run
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root=Path(tmp); source=root/'source';source.mkdir()
            records=[];rows=[]
            for j,(partition,event) in enumerate([('fold0',None),('fold1',dict(onset=199,impact=249)),('test',None),('test',dict(onset=199,impact=249))]):
                records.append(dict(trial_id=str(j),subject_id=str(j),activity_key='F01' if event else 'ADL',partition=partition,rows=400,frame_first=0,event=event))
                for k,end in enumerate(range(99,400,50)):
                    rows.append(dict(recording_id=j,end_frame=end,y=1 if event else 0,score=.9 if event and k>=3 else .1))
            (source/'recording_manifest.json').write_text(json.dumps(records))
            (source/'selection_lock.json').write_text(json.dumps(dict(threshold=.5,length=100,stride=50)))
            (source/'baseline_model.json').write_text('{}')
            pd.DataFrame(rows).to_csv(source/'selected_window_predictions.csv',index=False)
            a=run(source,root/'a',bootstrap=30)
            frame=pd.DataFrame(rows);frame.loc[frame.recording_id>=2,'score']=.999
            frame.to_csv(source/'selected_window_predictions.csv',index=False)
            b=run(source,root/'b',bootstrap=30)
            self.assertEqual(a['selection']['threshold'],b['selection']['threshold'])
            self.assertTrue(a['legacy_parity']['pass'])
            for name in ['README.md','metrics.json','report.md','events.csv','alarms.csv','by_subject.csv','by_activity.csv','threshold_curve.csv','selection_lock.json']:
                self.assertTrue((root/'a'/name).is_file(),name)

if __name__=='__main__':unittest.main()
