import unittest

import numpy as np

import multiphone_selection_audit as audit


def row(speaker, word='BALL', phone='B', counts=None, age=8):
    return dict(speakerId=speaker, clipId=speaker+'-clip', targetWord=word,
                targetPhone=phone, raterCounts=counts or [0, 0, 5], age=age, trainingEligible=True)


class AuditTests(unittest.TestCase):
    def test_same_speaker_different_rows_is_leakage(self):
        rows = [row('a'), row('b'), row('a')]
        with self.assertRaisesRegex(ValueError, 'speakers overlap'):
            audit.check_partitions(rows, [0], [1], [2])

    def test_vocabulary_uses_fit_only_and_uppercase_exact_words(self):
        mask = audit.lexical_mask([row('a', 'ball'), row('b', 'BALLS'), row('c', 'BE')], [row('fit', 'BALL')])
        np.testing.assert_array_equal(mask, [True, False, False])

    def test_sparse_and_absent_phones_are_explicit(self):
        rows = [row('a', counts=[1, 0, 4]), row('a', counts=[1, 0, 4]), row('b', phone='P')]
        result = audit.summarize([[.2, .1, .7], [.3, .1, .6], [.1, .1, .8]], rows, [True]*3)
        s = result['allWords']['support']['ages6to12']['perPhone']
        self.assertEqual(s['B']['events']['rating0']['positiveSpeakers'], 1)
        self.assertEqual(s['B']['events']['rating0']['positiveVotes'], 2)
        self.assertEqual(s['CH']['positions'], 0)
        m = result['allWords']['metrics']['ages6to12']
        self.assertIsNone(m['perTarget']['CH'])
        self.assertIsNone(m['targetDiscrimination']['perPhone']['P']['rating0']['averagePrecision'])
        self.assertIsNone(result['unseenWords']['metrics']['ages6to12'])
        self.assertEqual(len(s), 23)

    def test_invalid_probabilities_fail(self):
        for p in ([[float('nan'), .1, .9]], [[-.1, .1, 1]], [[.1, .1, .7]]):
            with self.assertRaises(ValueError): audit.summarize(p, [row('a')], [True])

    def test_duplicate_or_missing_outer_rows_fail(self):
        fold = dict(rowIndices=[0], probabilities=[[.1, .1, .8]], seenInFitVocabulary=[True])
        with self.assertRaisesRegex(ValueError, 'more than once'): audit.pool_predictions([fold, fold], [0])
        with self.assertRaisesRegex(ValueError, 'cover'): audit.pool_predictions([fold], [0, 1])
        self.assertEqual(audit.pool_predictions([fold], [0]), fold)

    def test_pooled_gain_cannot_hide_a_fold_loss(self):
        contrasts = {key: {'pooled': {'below2AP': .02}, 'folds': [{'below2AP': .01} for _ in range(5)]}
                     for key in ('0', '0.1')}
        self.assertTrue(audit.decision(contrasts)['consistentDevelopmentRankingGain'])
        self.assertFalse(audit.decision(contrasts)['promotionEligible'])
        contrasts['0.1']['folds'][2]['below2AP'] = -.001
        self.assertFalse(audit.decision(contrasts)['consistentDevelopmentRankingGain'])
        contrasts['0.1']['folds'][2]['below2AP'] = None
        with self.assertRaises(ValueError): audit.decision(contrasts)


if __name__ == '__main__': unittest.main()
