"""Independent numerical and no-fitting/phase guards for the fixed mixture."""
import copy
from decimal import Decimal, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from lexical_mixture import study as s


def pred(p, ids=None):
    p = np.asarray(p, dtype=np.float64)
    return dict(rowIndices=list(range(len(p))) if ids is None else ids,
                probabilities=p.tolist(), logProbabilities=np.log(p).tolist())


class MixtureTests(unittest.TestCase):
    def test_arithmetic_is_probability_mean_and_symmetric(self):
        a, b = pred([[.01,.09,.9],[.2,.3,.5]]), pred([[.4,.3,.3],[.7,.2,.1]])
        rows = [dict(raterCounts=[1,0,4]), dict(raterCounts=[2,1,2])]
        value = s.mixture(a,b,rows)
        expected = (np.asarray(a['probabilities'])+np.asarray(b['probabilities']))/2
        np.testing.assert_allclose(value['probabilities'],expected,rtol=2e-15,atol=0)
        self.assertEqual(s.mixture(b,a,rows),value)
        np.testing.assert_allclose(s.mixture(a,a,rows)['probabilities'],a['probabilities'],rtol=2e-15,atol=0)
        self.assertAlmostEqual(value['NLL'],float(-(np.array([r['raterCounts'] for r in rows])*np.log(expected)).sum()/10),places=15)

    def test_extreme_stable_logs_match_decimal_without_probability_floor(self):
        a = dict(rowIndices=[0], probabilities=[[0.,0.,1.]], logProbabilities=[[-2000.,-3000.,0.]])
        b = dict(rowIndices=[0], probabilities=[[0.,0.,1.]], logProbabilities=[[-2200.,-2800.,0.]])
        result=s.mixture(a,b,[dict(raterCounts=[5,0,0])])
        with localcontext() as ctx:
            ctx.prec=80
            expected=-((Decimal(-2000).exp()+Decimal(-2200).exp())/2).ln()
        self.assertLess(abs(result['NLL']-float(expected)),1e-12)
        self.assertGreater(result['NLL'],2000)
        self.assertEqual(result['probabilities'][0][0],0.)
        self.assertTrue(np.isfinite(result['logProbabilities']).all())

    def test_invalid_identity_probability_and_counts_rejected(self):
        a=pred([[.1,.2,.7],[.2,.2,.6]]);rows=[dict(raterCounts=[1,1,3])]*2
        for kind in ('order','duplicate','normalization','logs','nan','counts'):
            b=copy.deepcopy(a);rr=copy.deepcopy(rows)
            if kind=='order':b['rowIndices'].reverse()
            elif kind=='duplicate':b['rowIndices']=[0,0]
            elif kind=='normalization':b=pred([[.2,.4,1.4],[.2,.2,.6]])
            elif kind=='logs':b['logProbabilities'][0][0]+=.1
            elif kind=='nan':b['logProbabilities'][0][0]=float('nan')
            else:rr[0]['raterCounts']=[1,1,2]
            with self.subTest(kind=kind),self.assertRaises(ValueError):s.mixture(a,b,rr)

    def test_source_partition_equality_includes_fit_selection_and_refit(self):
        a=dict(family='scalars',regime='all-age',speakerFold=0,wordGroup=0,
               fitRows=[0],selectionRows=[1],refitRows=[0,1],outerRows=[2])
        b=dict(a,family='pca16-scalars');s.check_pair(a,b)
        for key in ('fitRows','selectionRows','refitRows','outerRows','speakerFold','wordGroup','regime'):
            bad=copy.deepcopy(b);bad[key]=[99] if key.endswith('Rows') else 'wrong'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'membership'):s.check_pair(a,bad)

    def test_run_never_calculates_without_valid_declaration(self):
        with patch.object(s,'load_plan',side_effect=ValueError('bad declaration')),patch.object(s,'calculate') as calculate:
            with self.assertRaisesRegex(ValueError,'bad declaration'):s.run(Path('plan'),'sha')
            calculate.assert_not_called()

    def test_declaration_reads_metadata_without_calculating_mixture(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=s.HERE/'outputs') as tmp:
            dest=Path(tmp)/'fresh'
            with patch.object(s,'inputs',return_value=({},[])),patch.object(s,'mixture',side_effect=AssertionError('no mixture')):
                pin=s.declare(dest)
                self.assertTrue(Path(pin['path']).exists())
                with self.assertRaisesRegex(ValueError,'Fresh ignored'):s.declare(dest)


if __name__=='__main__':unittest.main()
