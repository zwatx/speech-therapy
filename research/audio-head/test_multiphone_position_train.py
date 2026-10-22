"""Synthetic tests for matched membership, normalization and research decisions."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

import multiphone_position_train as m


class PositionTrainingTests(unittest.TestCase):
    def cohort(self):
        return {'rows': [dict(legacyRowIndex=old, speakerId=speaker, age=age, targetPhone='B', raterCounts=[0, 0, 5])
            for old, speaker, age in [(5, 'a', 8), (2, 'a', 8), (None, 'a', 8), (8, 'b', 18), (9, 'c', 10), (None, 'c', 10)]]}

    def test_original_order_and_expanded_membership(self):
        cohort = self.cohort(); splits = {'folds': [dict(outerFitRows=[0, 1, 2, 3], outerHoldoutRows=[4, 5])]}
        config = dict(fold=0, regime='all-age', fitRows=[2, 5, 8])
        self.assertEqual(m.partitions(cohort, splits, config, 'original'), ([1, 0, 3], [4, 5], [1, 0, 3]))
        self.assertEqual(m.partitions(cohort, splits, config, 'expanded')[0], [0, 1, 2, 3])
        config.update(regime='child-only', fitRows=[2, 5])
        self.assertEqual(m.partitions(cohort, splits, config, 'expanded')[0], [0, 1, 2])

    def test_speaker_overlap_and_missing_legacy_rejected(self):
        c = self.cohort(); splits = {'folds': [dict(outerFitRows=[0, 1, 2, 3], outerHoldoutRows=[4, 5])]}
        config = dict(fold=0, regime='all-age', fitRows=[2, 5])
        with self.assertRaises(ValueError): m.partitions(c, splits, config, 'original')
        config['fitRows'] = [2, 5, 8]; c['rows'][4]['speakerId'] = 'a'
        with self.assertRaises(ValueError): m.partitions(c, splits, config, 'expanded')

    def test_normalization_uses_only_fit_rows(self):
        c = self.cohort(); values = np.array([[1, 2], [3, 2], [9, 3], [11, 5], [900, 2], [800, 5]], np.float32)
        d = m.prepare(c, values, [0, 1])
        self.assertTrue(torch.equal(d['mean'], torch.tensor([2., 2.])))
        self.assertTrue(torch.equal(d['std'], torch.tensor([1., 1.])))
        self.assertEqual(d['priors']['B']['observedRows'], 2)

    def test_populations_are_exhaustive_and_disjoint(self):
        p = m.populations(self.cohort()['rows'])
        np.testing.assert_array_equal(p['original'] | p['added'], p['all'])
        self.assertFalse((p['original'] & p['added']).any())

    def contrasts(self):
        return {pop: dict(pooled=dict(below2AP=.01, rating0AP=0., macroNLL=-.01, Brier=-.001),
                              folds=[dict(below2AP=0.) for _ in range(5)]) for pop in ('original', 'all')}

    def test_decision_requires_both_populations_every_fold_and_proper_scores(self):
        self.assertTrue(m.decision(self.contrasts())['consistentDevelopmentGain'])
        for field, value in [('below2AP', 0.), ('rating0AP', -.01), ('macroNLL', .01), ('Brier', .01), ('below2AP', None)]:
            c = self.contrasts(); c['original']['pooled'][field] = value
            self.assertFalse(m.decision(c)['consistentDevelopmentGain'])
        c = self.contrasts(); c['all']['folds'][4]['below2AP'] = -.0001
        self.assertFalse(m.decision(c)['consistentDevelopmentGain'])
        c = self.contrasts(); c['all']['folds'].pop()
        self.assertFalse(m.decision(c)['consistentDevelopmentGain'])
        self.assertFalse(m.decision(self.contrasts())['promotionEligible'])

    def test_historical_parity_rejects_tensor_or_loss_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = torch.nn.Linear(2, 3); data = dict(mean=torch.zeros(2), std=torch.ones(2))
            checkpoint = root/'checkpoint.pt'; torch.save(dict(model=model.state_dict(), **data), checkpoint)
            history = [dict(epoch=1, trainPerRaterLogLoss=.4)]
            history_pin = m.write_new(root/'history.json', history)
            job = dict(historical={'checkpoint.pt': m.binding(checkpoint), 'history.json': history_pin})
            m.historical_parity(job, data, model, history)
            with self.assertRaises(ValueError): m.historical_parity(job, data, model, [dict(epoch=1, trainPerRaterLogLoss=.5)])
            with torch.no_grad(): model.bias[0] += .01
            with self.assertRaises(ValueError): m.historical_parity(job, data, model, history)


if __name__ == '__main__': unittest.main()
