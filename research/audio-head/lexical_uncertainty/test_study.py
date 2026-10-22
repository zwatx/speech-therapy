"""Tests for declaration guards and additive diagnostic denominators."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from lexical_uncertainty import study as s

class StudyTests(unittest.TestCase):
    def test_interval_retains_undefined_and_linear_quantiles(self):
        value=s.interval([None,-2.,0.,2.,None],1.)
        self.assertEqual(value['validReplicates'],3);self.assertEqual(value['undefinedReplicates'],2)
        np.testing.assert_allclose(value['interval95'],[-1.9,1.9])
        self.assertEqual(value['fractionAboveZero'],1/3)
        self.assertEqual(s.interval([None],None)['interval95'],[None,None])
        with self.assertRaises(ValueError):s.interval([float('nan')],0.)

    def test_contributions_share_fold_denominator_and_loo_removes_whole_child(self):
        rows=[dict(speakerId=str(i//2),targetPhone='B' if i%2==0 else 'D',raterCounts=[1,1,3]) for i in range(12)]
        folds=np.array([0,0,1,1,2,2,3,3,4,4,4,4]);groups=np.arange(12)%5
        delta=np.zeros((12,3));delta[8:]=[[1,0,0],[2,0,0],[-1,0,0],[0,0,0]]
        value=s.contributions(rows,folds,groups,delta)
        self.assertEqual(value['speakerFolds']['4']['NLLDelta'],.5)
        self.assertEqual(value['fold4']['children']['4']['additiveNLLContribution'],.75)
        self.assertEqual(value['fold4']['children']['5']['additiveNLLContribution'],-.25)
        self.assertEqual(value['leaveOneChildOut']['fold4']['4']['NLLDelta'],-.5)
        self.assertEqual(value['leaveOneChildOut']['fold4']['4']['removedPositions'],2)
        self.assertEqual(value['fold4']['wordGroups']['2']['positions'],0)
        self.assertIsNone(value['fold4']['wordGroups']['2']['NLLDelta'])
        self.assertEqual(value['fold4']['ratingClasses']['0']['additiveNLLContribution'],.5)

    def test_declaration_performs_no_actual_calculation(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            output=Path(tmp)/'fresh'
            with patch.object(s,'inputs',return_value={}),patch.object(s,'calculate',side_effect=AssertionError('no actual')):
                self.assertTrue(Path(s.declare(output)['path']).exists())
                with self.assertRaisesRegex(ValueError,'Fresh'):s.declare(output)

    def test_bad_declaration_blocks_calculation(self):
        with patch.object(s,'load_plan',side_effect=ValueError('bad')),patch.object(s,'calculate') as c:
            with self.assertRaises(ValueError):s.run(Path('x'),'sha')
            c.assert_not_called()

    def test_changed_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x';path.write_text('a');pin=s.binding(path)
            path.write_text('b')
            with self.assertRaisesRegex(ValueError,'Changed input'):s.binding(path,pin['sha256'])

if __name__=='__main__':unittest.main()
