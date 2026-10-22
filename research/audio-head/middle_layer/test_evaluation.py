import unittest
import numpy as np
from middle_layer import evaluation as e


class EvaluationTest(unittest.TestCase):
    def test_vote_loss_and_tied_ranking(self):
        rows = [dict(raterCounts=[2, 1, 2], targetPhone='B', speakerId='a', clipId='c')]
        p = np.array([[.2, .3, .5]])
        result = e.metrics(np.log(p), rows)
        labels = np.array([0, 0, 1, 2, 2])
        self.assertAlmostEqual(result['nll'], -np.log(p[0, labels]).mean())
        self.assertAlmostEqual(result['brier'], ((p-np.eye(3)[labels])**2).sum(1).mean())
        self.assertAlmostEqual(result['events']['rating0']['averagePrecision'], .4)
        self.assertAlmostEqual(result['events']['rating0']['auroc'], .5)
        rows[0]['raterCounts'] = [0, 0, 5]
        self.assertIsNone(e.metrics(np.log(p), rows)['events']['rating0']['averagePrecision'])
        with self.assertRaises(ValueError):
            e.metrics(np.log(p)+.01, rows)

    def test_six_part_screen_and_material_target(self):
        delta = dict(nll=-.01, macroNll=0., brier=0., rating0Ap=0., below2Ap=0.)
        folds = [dict(nll=0.) for _ in range(5)]
        self.assertTrue(e.screen(delta, folds, .2)['directionalPass'])
        self.assertFalse(e.screen(delta, folds, .2)['materialGainPass'])
        self.assertTrue(e.screen(dict(delta, nll=-.02, rating0Ap=.02), folds, .2)['materialGainPass'])
        for key, bad in [('nll', 0.), ('macroNll', 1e-6), ('brier', 1e-6),
                         ('rating0Ap', -1e-6), ('below2Ap', -1e-6)]:
            self.assertFalse(e.screen(dict(delta, **{key: bad}), folds, .2)['directionalPass'])
        self.assertFalse(e.screen(delta, [dict(nll=1e-6)]+folds[1:], .2)['directionalPass'])
        with self.assertRaises(ValueError):
            e.screen(delta, folds[:4], .2)
        with self.assertRaises(ValueError):
            e.screen(dict(delta, rating0Ap=None), folds, .2)

    def test_identity_and_child_scope_required(self):
        with self.assertRaises(ValueError):
            e.evaluate([], [], [], {})

    def test_paired_mixtures_and_complete_fold_comparison(self):
        rows = [dict(raterCounts=([5, 0, 0] if i % 2 == 0 else [0, 0, 5]),
                     targetPhone='B', speakerId=str(i//2), clipId=str(i),
                     age=6, legacyRowIndex=i) for i in range(10)]
        uniform = np.log(np.full((10, 3), 1/3))
        better = np.log(np.array([[.8, .1, .1] if i % 2 == 0 else [.1, .1, .8] for i in range(10)]))
        logs = dict(l12=better, l24=uniform, scalar=uniform, retainedCompact=uniform)
        folds = [i//2 for i in range(10)]
        result = e.evaluate(rows, list(range(10)), folds, logs)
        self.assertTrue(result['candidateForConfirmation'])
        self.assertTrue(result['compactCoCondition'])
        self.assertFalse(result['promotionEligible'])
        self.assertEqual(result['pooled']['deltas']['freshControl']['nll'], 0.)
        self.assertIsNone(result['groups']['age']['7']['metrics']['l12'])
        with self.assertRaises(ValueError): e.evaluate(rows, [0]*10, folds, logs)
        with self.assertRaises(ValueError): e.evaluate(rows, list(range(10)), [0]*10, logs)


if __name__ == '__main__':
    unittest.main()
