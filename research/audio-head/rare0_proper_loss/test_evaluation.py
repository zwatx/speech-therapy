"""Small, outcome-free checks of added fixed decision rules."""
import math
import unittest

import numpy as np

from rare0_proper_loss import evaluation as e


class EvaluationTests(unittest.TestCase):
    def sample_seed(self):
        phones = {str(i): {'metrics': {
            'rare0Mixture': {'events': {'rating0': {'averagePrecision': .2}}},
            'finalMixture': {'events': {'rating0': {'averagePrecision': .1}}}}}
            for i in range(23)}
        return {'groups': {'phone': phones, 'age': {'6': {
            'deltas': {'primary': {'rating0Ap': .01, 'macroNll': -.01}}}}}}

    def test_extra_guard_all_23_and_age6(self):
        sample = self.sample_seed()
        result = e.extra_screen(sample)
        self.assertTrue(result['passed'])
        self.assertEqual(result['equalPhoneRating0Ap']['supportedPhones'], 23)
        sample['groups']['age']['6']['deltas']['primary']['rating0Ap'] = -.001
        self.assertFalse(e.extra_screen(sample)['checks']['age6Rating0ApNonworse'])
        sample['groups']['age']['6']['deltas']['primary']['rating0Ap'] = .01
        sample['groups']['phone']['0']['metrics']['rare0Mixture']['events']['rating0']['averagePrecision'] = None
        with self.assertRaisesRegex(ValueError, 'Undefined required'):
            e.extra_screen(sample)

    def test_class_contribution_preserves_mixed_votes(self):
        counts = [[2, 0, 3], [0, 0, 5]]
        candidate = np.log([[.3, .1, .6], [.1, .1, .8]])
        reference = np.log([[.2, .1, .7], [.05, .15, .8]])
        value = e.class_contribution(counts, candidate, reference)
        self.assertEqual(value['votes'], [2, 0, 8])
        self.assertIsNone(value['classConditionalMeanDelta'][1])
        self.assertAlmostEqual(sum(value['additiveNllDelta']), value['nllDelta'], places=12)
        self.assertAlmostEqual(value['additiveNllDelta'][0], 2*math.log(.2/.3)/10, places=12)

    def test_rejects_invalid_probability_and_vote_rows(self):
        with self.assertRaisesRegex(ValueError, 'Invalid vote'):
            e.class_contribution([[2, 0, 2]], np.log([[.2, .3, .5]]), np.log([[.2, .3, .5]]))
        with self.assertRaisesRegex(ValueError, 'Invalid vote'):
            e.class_contribution([[2, 0, 3]], np.log([[.2, .3, .4]]), np.log([[.2, .3, .5]]))


if __name__ == '__main__':
    unittest.main()
