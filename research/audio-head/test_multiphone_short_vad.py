import unittest
import multiphone_short_vad as short


class ShortVadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vendor, _ = short.raw.read_bound_json(short.study.ROOT/'vad-source-v1/manifest.json')
        cls.helper = short.study.load_helper(vendor['files']['utils_vad.py'])

    def test_fixed_duration_difference_preserves_true_end(self):
        # First positive at sample2560 leaves2000samples=125ms, above100 but below250.
        p = [0.0]*5 + [0.9]*4
        self.assertEqual(short.segment(self.helper, p, 4560, 250), [])
        intervals = short.segment(self.helper, p, 4560, 100)
        self.assertEqual(intervals, [{'start': 2080, 'end': 4560}])
        self.assertEqual(short.study.PARAMS['min_speech_duration_ms'], 250)

    def test_no_speech_and_invalid_probability(self):
        for duration in (100, 250):
            self.assertEqual(short.segment(self.helper, [0.0]*10, 5000, duration), [])
        with self.assertRaises(ValueError): short.segment(self.helper, [float('nan')], 512, 100)

    def test_historical_decision_tampering_rejected(self):
        record = {'clip': {'sampleCount': 4560}, 'probabilities': [0.0]*5+[0.9]*4,
                  'timestamps': [], 'vad': True}
        with self.assertRaises(ValueError): short.compare(self.helper, record)

    def test_combination_still_requires_phone_evidence(self):
        record = {'clip': {'sampleCount': 4560, 'gate': False},
                  'probabilities': [0.0]*5+[0.9]*4, 'timestamps': [], 'vad': False}
        result = short.compare(self.helper, record)
        self.assertTrue(result['vad']['short100'])
        self.assertFalse(result['combined']['short100'])

    def test_report_separates_measured_combined_from_fresh_vad_only(self):
        r = {'clip': {'id': 'c', 'corpusId': 'c', 'population': 'corpus', 'gate': True},
             'vad': {'default250': True, 'short100': True}}
        old = {'clip': {'id': 'e', 'population': 'environment', 'category': 'dog'},
               'vad': {'default250': True, 'short100': True},
               'combined': {'default250': False, 'short100': False}}
        fresh = {'clip': {'id': 'f', 'population': 'fresh', 'category': 'dog'},
                 'vad': {'default250': True, 'short100': True}}
        rows = [{'clipId': 'c', 'speakerId': 's', 'age': 8, 'targetPhone': 'B', 'raterCounts': [1, 1, 3]}]
        result = short.summarize({'c': r, 'e': old, 'f': fresh}, rows)
        self.assertEqual(result['challenges']['short100']['environment']['dog']['combinedRetained'], 0)
        self.assertEqual(result['challenges']['short100']['fresh']['dog']['retained'], 1)
        self.assertNotIn('combinedRetained', result['challenges']['short100']['fresh']['dog'])


if __name__ == '__main__': unittest.main()
