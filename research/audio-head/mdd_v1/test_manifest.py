import unittest
from test_l2_arctic_annotations import grid
from .manifest import check_leakage, l2_record, speech_record
from .inventory import PHONES, map_espeak
from .evaluate import align, per_counts, mdd_counts, evaluate


class ManifestTests(unittest.TestCase):
    def test_l2_preserves_events_unknown_and_detail(self):
        raw = grid([('words', [(0, 1, 'word')]), ('phones', [
            (0, .2, 'R,AH0*,s'), (.2, .4, 'T,sil,d'), (.4, .6, 'sil,S,a'),
            (.6, .8, 'L,err,s'), (.8, 1, 'IY1')])])
        row = l2_record(raw, 'YDCK', 'a', '/a.wav')
        self.assertEqual(row['canonical'], ['R', 'T', 'L', 'IY'])
        self.assertEqual(row['perceived'], ['AH', 'S', None, 'IY'])
        self.assertEqual([e['canonical_index'] for e in row['events']], [0, 1, 2, 2, 3])
        self.assertTrue(row['events'][0]['perceived_detail']['deviation'])
        self.assertEqual(row['events'][0]['raw'], 'R,AH0*,s')
        with self.assertRaises(ValueError):
            l2_record(raw, 'EBVS', 'a', '/a.wav')

    def test_scores_do_not_impute_identity(self):
        row = speech_record({'words': [{'phones': ['R', 'AH0', 'T'], 'phones-accuracy': [2, 1.8, 0]}]},
                            '1', 'a', 'train', 7, '/a.wav')
        self.assertEqual(row['perceived'], ['R', None, None])
        self.assertFalse(row['all_correct'])
        self.assertEqual(row['population'], 'child')
        with self.assertRaises(ValueError):
            speech_record({'words': [{'phones': ['R'], 'phones-accuracy': []}]}, '1', 'a', 'train', 7, '/a')

    def test_leakage_duplicate_and_reserved_rejected(self):
        row = dict(source='speechocean762', speaker='1', split='train', id='a', audio='/a', audio_sha256='x')
        check_leakage([row])
        for other in [dict(row), dict(row, id='b', audio='/b', split='test'),
                      dict(row, id='b', audio='/b', speaker='2', split='test'),
                      dict(row, id='b', source='l2-arctic', speaker='EBVS')]:
            with self.subTest(other=other), self.assertRaises(ValueError):
                check_leakage([row, other])

    def test_inventory_unknown_not_silently_removed(self):
        self.assertEqual(len(PHONES), 39)
        self.assertEqual(map_espeak(['ɑːɹ', '??', 'ɾ']), (['AA', 'R', '<unk>', 'T'], ['??']))


class EvaluationTests(unittest.TestCase):
    def test_per_sdi_and_repeated_phones(self):
        c, _ = per_counts(['AA', 'B', 'S'], ['AA', 'D', 'S', 'T'])
        self.assertEqual(dict(c), dict(N=3, S=1, D=0, I=1))
        c, _ = per_counts(['T', 'T'], ['T'])
        self.assertEqual(c['D'], 1)
        self.assertEqual(align([], ['T']), [(None, 0)])

    def test_mdd_all_four_cases_and_diagnosis(self):
        row = dict(canonical=['AA', 'B', 'S', 'T'], events=[
            dict(canonical_index=0, perceived='AA', event='unchanged'),
            dict(canonical_index=1, perceived='B', event='unchanged'),
            dict(canonical_index=2, perceived='Z', event='substitution'),
            dict(canonical_index=3, perceived=None, event='deletion')])
        c = mdd_counts(row, ['AA', 'D', 'S'])
        self.assertEqual([c[k] for k in ['TA', 'FR', 'FA', 'TR', 'CD']], [1, 1, 1, 1, 1])

    def test_unknown_per_excluded_but_detection_scored(self):
        row = dict(id='a', source='l2-arctic', canonical=['R'], perceived=[None],
                   events=[dict(canonical_index=0, perceived=None, event='substitution')])
        result = evaluate([row], {'a': ['L']})
        self.assertIsNone(result['PER'])
        self.assertEqual(result['mdd']['TR'], 1)
        self.assertIsNone(result['diagnosis_accuracy'])

    def test_same_broad_phone_deviation_is_reference_error(self):
        row = dict(canonical=['R'], events=[dict(canonical_index=0, perceived='R', event='substitution')])
        self.assertEqual(mdd_counts(row, ['R'])['FA'], 1)
        self.assertEqual(mdd_counts(row, ['R'])['same_broad_identity_FA'], 1)
        counts = mdd_counts(row, ['L'])
        self.assertEqual(counts['same_broad_identity_TR'], 1)
        self.assertEqual(counts['diagnosis_eligible_TR'], 1)
        self.assertEqual(counts['CD'], 0)

    def test_insertions_are_separate_from_canonical_positions(self):
        row = dict(canonical=['R'], events=[dict(canonical_index=0, perceived='R', event='unchanged'),
                    dict(canonical_index=1, perceived='S', event='insertion')])
        c = mdd_counts(row, ['R', 'S'])
        self.assertEqual(c['TA'], 1)
        self.assertEqual(c['correct_insertion_phones'], 1)

class L2NormalizationTests(unittest.TestCase):
    def test_case_ax_and_raw_labels(self):
        raw = grid([('words', [(0, 1, 'word')]), ('phones', [(0, .5, 'AX0'), (.5, 1, 'w,v,S')])])
        row = l2_record(raw, 'ASI', 'a', '/a')
        self.assertEqual(row['canonical'], ['AH', 'W'])
        self.assertEqual(row['perceived'], ['AH', 'V'])
        self.assertEqual(row['raw_intervals'][0]['rawLabel'], 'AX0')


if __name__ == '__main__':
    unittest.main()
