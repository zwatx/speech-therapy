import copy
import unittest
import numpy as np

from middle_layer_replication import evaluation as e


class EvaluationTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(raterCounts=[5, 0, 0] if i % 2 == 0 else [0, 0, 5],
                     targetPhone=phone, speakerId=f'child{age}', clipId=str(i), age=age, legacyRowIndex=i)
                for i, (age, phone) in enumerate((a, p) for a in range(6, 13) for p in e.TARGETS[:23])]
        n = len(rows)
        uniform = np.log(np.full((n, 3), 1/3))
        better = np.log(np.array([[.8, .1, .1] if i % 2 == 0 else [.1, .1, .8] for i in range(n)]))
        result = e.evaluate_seed(rows, list(range(n)), [i % 5 for i in range(n)],
                                 dict(middle=better, final=uniform, scalar=uniform))
        return {str(seed): copy.deepcopy(result) for seed in e.SEEDS}

    def test_all_seeds_and_ages_pass(self):
        result = e.summarize(self.fixture())
        self.assertTrue(result['replicationPass'])
        self.assertEqual(result['ageGuard']['agesWorseAtEverySeed'], [])
        self.assertEqual(len(result['groups']['phone']), 23)

    def test_any_age_regression_at_all_three_fails(self):
        seeds = self.fixture()
        for count, seed in enumerate(e.SEEDS, 1):
            seeds[str(seed)]['groups']['age']['9']['deltas']['primary']['nll'] = .001
            result = e.summarize(seeds)
            self.assertEqual(result['groups']['age']['9']['seedsWithWorseNll'], count)
            self.assertEqual(result['replicationPass'], count < 3)
        self.assertEqual(result['ageGuard']['agesWorseAtEverySeed'], ['9'])

    def test_failed_seed_cannot_be_rescued_by_mean(self):
        seeds = self.fixture()
        seeds['29']['seedPass'] = False
        result = e.summarize(seeds)
        self.assertLess(result['changes']['primary']['nll']['mean'], 0)
        self.assertFalse(result['replicationPass'])

    def test_missing_seed_or_support_rejected(self):
        seeds = self.fixture()
        with self.assertRaises(ValueError): e.summarize({k: v for k, v in seeds.items() if k != '43'})
        seeds['43']['groups']['age']['8']['metrics']['middleMixture']['positions'] += 1
        with self.assertRaises(ValueError): e.summarize(seeds)
        with self.assertRaises(ValueError): e.evaluate([], [], {}, {})

    def test_frozen_discovery_numbers_exact(self):
        result = e.discovery_check()
        self.assertTrue(result['exact'])
        self.assertEqual(result['viewsCompared'], 88)


if __name__ == '__main__': unittest.main()
