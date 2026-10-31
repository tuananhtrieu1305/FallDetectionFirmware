import unittest
import numpy as np
import pandas as pd

class MetricsContract(unittest.TestCase):
    def fixture(self, scores=None, event=None, rows=400):
        records=[dict(recording_id=0,trial_id='a',subject_id='s',activity_key='F01' if event else 'ADL',partition='fold0',rows=rows,frame_first=0,event=event)]
        ends=list(range(99,rows,50))
        index=pd.DataFrame(dict(recording_id=[0]*len(ends),end_frame=ends,y=[-1 if event else 0]*len(ends)))
        return records,index,np.array(scores if scores is not None else [0]*len(ends),float)

    def test_alarm_runs_delay_and_boundary(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture([0,0,0,1,1,0,1],dict(onset=200,impact=249))
        m=evaluate(r,i,s,.5,bootstrap=0)
        self.assertEqual(m['detected'],1)
        self.assertEqual(m['recall_at_0_5s'],1)
        self.assertEqual(m['extra_alarms_in_detection_interval'],0)
        self.assertEqual(m['late_fall_trial_alarms'],1)
        self.assertEqual(m['median_delay_nominal_s'],0)

    def test_persistent_early_alarm_not_detection(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture([1]*7,dict(onset=200,impact=249))
        m=evaluate(r,i,s,.5,bootstrap=0)
        self.assertEqual(m['recall'],0)
        self.assertIsNone(m['median_delay_nominal_s'])

    def test_short_event_stays_in_denominator_and_missing_score_rejected(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture(rows=50,event=dict(onset=10,impact=20))
        m=evaluate(r,i,s,.5,bootstrap=0)
        self.assertEqual((m['events'],m['missed']),(1,1))
        r,i,s=self.fixture()
        for ix,sc in [(i.iloc[:-1],s[:-1]),(i,s*np.nan),(pd.concat([i,i.iloc[:1]]),np.r_[s,0])]:
            with self.assertRaises(ValueError): evaluate(r,ix,sc,.5,bootstrap=0)

    def test_exposure_active_duration_and_null(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture([1,1,0],rows=201)
        m=evaluate(r,i,s,.5,bootstrap=0)
        self.assertEqual(m['false_alarms'],1)
        self.assertAlmostEqual(m['adl_monitored_nominal_hours'],1.02/3600)
        self.assertAlmostEqual(m['alarm_active_fraction'],1/1.02)
        self.assertEqual(m['longest_positive_run_nominal_s'],1)
        self.assertIsNone(m['recall'])
        self.assertEqual(m['window_metrics']['precision'],0)
        self.assertAlmostEqual(m['poisson_upper_95_per_hour'],4.743864518390577/(1.02/3600))

    def test_segments_reset_and_exclude_gap(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture([1,1,1,1],rows=400)
        r[0]['segments']=[dict(first_frame=0,rows=199),dict(first_frame=300,rows=199)]
        i=i.iloc[:4].copy();i['end_frame']=[99,149,399,449]
        m=evaluate(r,i,s,.5,bootstrap=0)
        self.assertEqual(m['false_alarms'],2)
        self.assertAlmostEqual(m['alarm_active_fraction'],1)
        self.assertAlmostEqual(m['adl_monitored_nominal_hours'],2.0/3600)

    def test_threshold_sweep_matches_bruteforce(self):
        from metrics_v11 import evaluate, select_threshold
        r,i,s=self.fixture([.1,.8,.2,.9,.6,.1,.7],dict(onset=200,impact=249))
        r2,i2,s2=self.fixture([.1,.7,.4,.9,.1,.2,.8]);r2[0].update(recording_id=1,trial_id='b',subject_id='t');i2['recording_id']=1
        r+=r2;i=pd.concat([i,i2],ignore_index=True);s=np.r_[s,s2]
        result,curve=select_threshold(r,i,s,limit=10000)
        for row in curve:
            brute=evaluate(r,i,s,row['threshold'],bootstrap=0)
            for key in ['recall','macro_recall','false_alarms','p95_delay_nominal_s','alarm_active_fraction']:
                self.assertEqual(row[key],brute[key],key)
        self.assertIsNotNone(result)

    def test_window_ap_ci_and_reproducibility(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture([.9,.8,.7,.1,.2,.3,.4]);i['y']=[1,0,1,0,-1,0,0]
        a=evaluate(r,i,s,.5,bootstrap=100)
        b=evaluate(r,i,s,.5,bootstrap=100)
        self.assertEqual(a,b)
        self.assertAlmostEqual(a['window_metrics']['average_precision'],5/6)
        self.assertIsNone(a['bootstrap_95']['recall'])

class AdditionalContracts(unittest.TestCase):
    fixture = MetricsContract.fixture
    def test_inclusive_deadline_and_after_deadline(self):
        from metrics_v11 import evaluate
        for impact, expected in [(199,1),(198,0)]:
            r,i,s=self.fixture([0,0,0,0,1,0,0],dict(onset=150,impact=impact))
            self.assertEqual(evaluate(r,i,s,.5,bootstrap=0)['detected'],expected)
        r,i,s=self.fixture([0,0,1,0,0,0,0],dict(onset=199,impact=249))
        self.assertEqual(evaluate(r,i,s,.5,bootstrap=0)['median_delay_nominal_s'],-.5)

    def test_ignore_scored_and_all_negative_null_precision(self):
        from metrics_v11 import evaluate
        r,i,s=self.fixture([0]*7,dict(onset=199,impact=249))
        m=evaluate(r,i,s,.5,bootstrap=100)
        self.assertEqual(m['window_metrics']['ignored_windows'],7)
        self.assertIsNone(m['window_metrics']['precision'])
        self.assertEqual(m['event_binomial_95'][0],0)
        self.assertIsNone(m['poisson_upper_95_per_hour'])
        r,i,s=self.fixture([1]*7)
        m=evaluate(r,i,s,.5,bootstrap=0)
        self.assertAlmostEqual(m['alarm_active_fraction'],1)

    def test_selection_rejects_test_and_no_detection(self):
        from metrics_v11 import select_threshold
        r,i,s=self.fixture()
        self.assertIsNone(select_threshold(r,i,s)[0])
        r[0]['partition']='test'
        with self.assertRaises(ValueError):select_threshold(r,i,s)

    def test_validation_metadata_labels_and_order(self):
        from metrics_v11 import evaluate
        for change in ['label','subject','order','segments','event','config','threshold']:
            r,i,s=self.fixture()
            kwargs={}
            if change=='label':i.loc[0,'y']=2
            if change=='subject':i['subject_id']='wrong'
            if change=='order':i=i.iloc[::-1]
            if change=='segments':r[0]['segments']=[dict(first_frame=0,rows=200),dict(first_frame=100,rows=200)]
            if change=='event':r[0]['event']=dict(onset=1,impact=1)
            if change=='config':kwargs['length']=0
            threshold=float('nan') if change=='threshold' else .5
            with self.assertRaises(ValueError):evaluate(r,i,s,threshold,bootstrap=0,**kwargs)

if __name__=='__main__': unittest.main()
