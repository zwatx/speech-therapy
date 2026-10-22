import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from lexical_support import core,study as s

class SupportTests(unittest.TestCase):
    def test_analytic_scalar_and_residual(self):
        v=core.scores([[2.,3.],[1.,-3.]],[[1.,2.,3.],[0.,4.,0.]],[1.,0.],[.5,3.],[0.,0.,0.],[[1.],[0.],[0.]])
        np.testing.assert_allclose(v['scalarZ'],[[2,1],[0,-1]])
        np.testing.assert_array_equal(v['dominantScalar'],[0,1])
        np.testing.assert_allclose(v['pcaResidualMSE'],[13/3,16/3])

    def test_residual_basis_rotation_and_translation_invariant(self):
        rng=np.random.default_rng(3);x=rng.normal(size=(12,4));sc=rng.normal(size=(12,2));basis=np.eye(4)[:,:2]
        def calc(x,c,b):return core.scores(sc,x,[0,0],[1,1],c,b)['pcaResidualMSE']
        a=calc(x,np.zeros(4),basis);b=calc(x+100,np.full(4,100),basis@np.array([[0,-1],[1,0]]))
        np.testing.assert_allclose(a,b,atol=1e-13,rtol=0)
        np.testing.assert_allclose(a,(x[:,2]**2+x[:,3]**2)/4,atol=1e-15)

    def test_empirical_ties_extremes_and_phone_reference(self):
        np.testing.assert_array_equal(core.midrank([2,1,2,4],[-1,1,2,3,4,5]),[0,.125,.5,.75,.875,1])
        self.assertEqual(core.midrank([3,3,3],[3])[0],.5)
        v=core.compare([1,2,2,4],[2,3],['A','B','A','B'],['A','B'])
        np.testing.assert_array_equal(v['samePhonePercentile'],[.75,.5]);np.testing.assert_array_equal(v['samePhoneFitPositions'],[2,2])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):core.midrank([], [1])
        with self.assertRaises(ValueError):core.midrank([1],[float('nan')])
        with self.assertRaises(ValueError):core.compare([1],[1],['A'],['B'])
        with self.assertRaises(ValueError):core.scores([[1]],[[2]],[0],[0],[0],[[1]])
        with self.assertRaises(ValueError):core.scores([[1]],[[2]],[0],[1],[0],[[2]])

    def row(self,i):
        axes={axis:dict(value=i+1.,globalPercentile=.99 if i==0 else 1.,samePhonePercentile=.2) for axis in s.RECIPE['axes']}
        return dict(speakerId=str(i//2),targetPhone='B' if i%2 else 'D',speakerFold=i%5,wordGroup=i%5,
                    raterCounts=[1,1,3],NLLDelta=float(i-2),dominantScalar=s.SCALAR_NAMES[0],**axes)

    def test_summary_denominator_tail_strictness_and_empty_cells(self):
        rows=[self.row(i) for i in range(4)];v=s.summaries(rows)
        self.assertEqual(v['pooled']['meanNLLDelta'],-.5)
        self.assertEqual(v['children']['0']['additiveNLLContribution'],-.75)
        self.assertEqual(v['tailPartitions']['scalarMaxAbsZ/globalPercentile']['true']['positions'],3)
        self.assertEqual(v['speakerFolds']['4']['positions'],0);self.assertIsNone(v['speakerFolds']['4']['meanNLLDelta'])
        self.assertEqual(sum(x['positions'] for x in v['jointTailPatterns']['cells'].values()),4)
        self.assertEqual(sum(x['additiveNLLContribution'] for x in v['jointTailPatterns']['cells'].values()),-.5)

    def test_declaration_no_score_calls_and_fresh_destination(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            output=Path(tmp)/'new'
            with patch.object(s,'inputs',return_value=({},[])),patch.object(core,'scores',side_effect=AssertionError('no score')):
                self.assertTrue(Path(s.declare(output)['path']).exists())
                with self.assertRaisesRegex(ValueError,'Fresh'):s.declare(output)

    def test_bad_declaration_stops_calculation(self):
        with patch.object(s,'load_plan',side_effect=ValueError('bad')),patch.object(s,'calculate') as c:
            with self.assertRaises(ValueError):s.run(Path('x'),'sha')
            c.assert_not_called()

if __name__=='__main__':unittest.main()
