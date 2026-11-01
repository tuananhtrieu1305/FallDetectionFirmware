"""Analysis must diagnose alarm timing, not just positive window counts."""
import unittest
import numpy as np


class ResultAnalysisContracts(unittest.TestCase):
    def test_no_crossing_and_inclusive_deadline(self):
        from analyze_baseline_results import diagnose_trial
        event = dict(onset=150, impact=200)
        a = diagnose_trial([99, 149, 199, 249, 299, 349], [.1]*6, .5, event)
        self.assertEqual(a['diagnosis'], 'no_crossing_in_detection_interval')
        self.assertAlmostEqual(a['threshold_margin'], -.4)
        b = diagnose_trial([100, 150, 200, 250, 300, 350], [0, 0, 0, 0, .5, 0], .5, event)
        self.assertEqual(b['diagnosis'], 'detected')
        self.assertEqual(b['first_matching_alarm_frame'], 300)

    def test_early_persistent_and_late(self):
        from analyze_baseline_results import diagnose_trial
        event = dict(onset=150, impact=200)
        a = diagnose_trial([99, 149, 199, 249, 299, 349], [.9]*6, .5, event)
        self.assertEqual(a['diagnosis'], 'already_positive_before_onset')
        self.assertIsNone(a['delay_nominal_s'])
        b = diagnose_trial([99, 149, 199, 249, 299, 349], [0, 0, 0, 0, 0, .9], .5, event)
        self.assertEqual(b['diagnosis'], 'late_only')

    def test_missing_opportunity_and_adl(self):
        from analyze_baseline_results import diagnose_trial
        a = diagnose_trial([], [], .5, dict(onset=10, impact=20))
        self.assertEqual(a['diagnosis'], 'no_window_in_detection_interval')
        b = diagnose_trial([99, 149, 199, 249], [.9, .9, .1, .8], .5, None)
        self.assertEqual(b['diagnosis'], 'adl_false_alarm')
        self.assertEqual(b['alarm_frames'], [99, 249])

    def test_paired_rescued_and_lost_not_just_net(self):
        from analyze_baseline_results import paired_events
        reference = [dict(trial_id=str(k), subject_id='P'+str(k//2), events=1, detected=v)
                     for k, v in enumerate([0, 1, 0, 1])]
        challenger = [dict(r, detected=v) for r, v in zip(reference, [1, 0, 1, 1])]
        a = paired_events(reference, challenger, resamples=100)
        self.assertEqual(a['rescued_trials'], ['0', '2'])
        self.assertEqual(a['lost_trials'], ['1'])
        self.assertEqual(a['delta_detected'], 1)
        self.assertAlmostEqual(a['delta_recall'], .25)
        self.assertEqual(a, paired_events(reference, challenger, resamples=100))

    def test_pairing_requires_identical_events_and_subjects(self):
        from analyze_baseline_results import paired_events
        r = [dict(trial_id='a', subject_id='P', events=1, detected=0)]
        for wrong in [[], [dict(r[0], subject_id='Q')], r+r]:
            with self.assertRaises(ValueError): paired_events(r, wrong)

    def test_success_comparator_is_other_person_and_deterministic(self):
        from analyze_baseline_results import choose_comparator
        r = dict(trial_id='bad', subject_id='P', activity_key='F01')
        candidates = [dict(trial_id=t, subject_id=p, activity_key='F01')
                      for t, p in [('b', 'Q'), ('a', 'R'), ('0', 'P')]]
        outcomes = {t: 1 for t in ['a', 'b', '0']}
        self.assertEqual(choose_comparator(r, candidates, outcomes)['trial_id'], 'a')
        self.assertEqual(choose_comparator(r, candidates[::-1], outcomes)['trial_id'], 'a')
        self.assertIsNone(choose_comparator(r, [], outcomes))


if __name__ == '__main__': unittest.main()
