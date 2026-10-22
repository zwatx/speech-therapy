import unittest
import numpy as np
from .core import fit, log_scaled, loss_derivatives, normalized, scaled


class TemperatureTests(unittest.TestCase):
    def test_known_binary_equivalent_optimum(self):
        # Equal alternatives form group two; q0=.6 requires 2**beta=3.
        p = [[.5, .25, .25]]
        r = fit(p, [[3, 1, 1]])
        self.assertAlmostEqual(r['beta'], np.log(3)/np.log(2), places=13)
        self.assertAlmostEqual(r['temperature'], 1/r['beta'])
        self.assertEqual(r['iterations'], 80)
        self.assertEqual(r['status'], 'interior')
        self.assertIsNone(r['boundary'])
        np.testing.assert_allclose(scaled(p, r['beta']), [[.6, .2, .2]])
        self.assertAlmostEqual(r['objective_optimum'], -(.6*np.log(.6)+.4*np.log(.2)))

    def test_exact_identity(self):
        p = np.array([[.6, .3, .10000001], [.2, .3, .5]])
        n = normalized(p)
        np.testing.assert_array_equal(scaled(p, 1), n)
        np.testing.assert_allclose(n.sum(axis=1), 1, rtol=0, atol=2e-16)
        self.assertEqual(n.dtype, np.float64)
        np.testing.assert_array_equal(p, [[.6, .3, .10000001], [.2, .3, .5]])

    def test_log_scaling_identity_and_extreme(self):
        p = np.array([[.6, .3, .10000001]])
        np.testing.assert_array_equal(log_scaled(p, 1), np.log(normalized(p)))
        extreme = [[1., 1e-300, np.nextafter(0., 1.)]]
        logs = log_scaled(extreme, 20)
        self.assertTrue(np.all(np.isfinite(logs)))
        self.assertLess(logs[0, 2], -14000)
        self.assertEqual(scaled(extreme, 20)[0, 2], 0)
        self.assertAlmostEqual(-logs[0, 2], loss_derivatives(extreme, [[0, 0, 5]], 20)[0])
        for beta in [.05, 1, 20]:
            np.testing.assert_allclose(np.exp(log_scaled(p, beta)), scaled(p, beta), rtol=1e-14)

    def test_mixed_votes(self):
        p, c = [[.6,.3,.1],[.1,.2,.7]], [[2,2,1],[0,3,2]]
        expected = -(2*np.log(.6)+2*np.log(.3)+np.log(.1)+3*np.log(.2)+2*np.log(.7))/10
        self.assertAlmostEqual(loss_derivatives(p,c,1)[0], expected)
        self.assertLessEqual(fit(p,c)['objective_optimum'], expected+1e-12)

    def test_extreme_probabilities(self):
        p, c = [[1.,1e-300,np.nextafter(0.,1.)]], [[0,2,3]]
        for beta in [.05,1,20]:
            self.assertTrue(np.all(np.isfinite(loss_derivatives(p,c,beta))))
            q = scaled(p,beta)
            self.assertTrue(np.all(np.isfinite(q)))
            np.testing.assert_allclose(q.sum(axis=1),1)
        self.assertEqual(fit(p,c)['boundary'],'lower')

    def test_boundaries_flat(self):
        p = [[.6,.3,.1]]
        self.assertEqual(fit(p,[[0,0,5]])['beta'],.05)
        r = fit(p,[[5,0,0]])
        self.assertEqual(r['beta'],20)
        self.assertEqual(r['boundary'],'upper')
        r = fit([[1/3]*3]*2,[[5,0,0],[0,2,3]])
        self.assertEqual(r['beta'],1)
        self.assertEqual(r['status'],'flat')
        self.assertEqual(r['iterations'],0)
        self.assertAlmostEqual(r['curvature'],0)

    def test_finite_differences(self):
        p,c = [[.8,.15,.05],[.11,.38,.51]], [[2,1,2],[1,3,1]]
        beta,h = 1.3,1e-4
        loss,g,v = loss_derivatives(p,c,beta)
        left,right = loss_derivatives(p,c,beta-h),loss_derivatives(p,c,beta+h)
        self.assertAlmostEqual(g,(right[0]-left[0])/(2*h),places=8)
        self.assertAlmostEqual(v,(right[1]-left[1])/(2*h),places=8)
        self.assertAlmostEqual(v,(right[0]-2*loss+left[0])/h**2,places=6)

    def test_argmax_and_normalization(self):
        p = np.random.default_rng(932).dirichlet([.5,2,1],size=200)
        p = np.vstack([p,[.4,.4,.2],[1/3]*3])
        for beta in [.05,.3,1,2,20]:
            q = scaled(p,beta)
            np.testing.assert_array_equal(q.argmax(axis=1),p.argmax(axis=1))
            np.testing.assert_allclose(q.sum(axis=1),1,atol=5e-16,rtol=0)
            np.testing.assert_array_equal(q,scaled(p,beta))

    def test_invalid_distributions(self):
        invalid = [[],[[.5,.5]],[.2,.3,.5],[[0,.5,.5]],[[-.1,.5,.6]],
                   [[1.1,.1,.1]],[[.1,.1,.1]],[[np.nan,.5,.5]],
                   [[np.inf,.5,.5]],[[True]*3],[['.2','.3','.5']],[[.2+.1j,.3,.5]]]
        for p in invalid:
            with self.subTest(p=p), self.assertRaises(ValueError):
                normalized(p)

    def test_invalid_counts_beta(self):
        p = [[.6,.3,.1]]
        invalid = [[[1,1,1]],[[-1,1,5]],[[1.5,1.5,2]],[[np.nan,2,3]],
                   [[np.inf,2,3]],[[True]*3],[['2','2','1']],[[2,3]],[2,2,1]]
        for c in invalid:
            with self.subTest(c=c),self.assertRaises(ValueError):
                fit(p,c)
        for beta in [True,np.bool_(False),0,.049,20.1,np.nan,np.inf,'1',1j]:
            with self.subTest(beta=beta):
                with self.assertRaises(ValueError):
                    scaled(p,beta)
                with self.assertRaises(ValueError):
                    log_scaled(p,beta)
                with self.assertRaises(ValueError):
                    loss_derivatives(p,[[2,2,1]],beta)
        self.assertTrue(np.isfinite(loss_derivatives(p,[[2.,2.,1.]],1)[0]))


if __name__ == '__main__':
    unittest.main()
