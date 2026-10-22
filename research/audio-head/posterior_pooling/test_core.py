"""Independent tiny emission-path oracle; synthetic arrays only."""
import itertools
import json
import unittest

import numpy as np

from posterior_pooling.core import CTCPosterior, POLICY, box_weights, pool_hidden, vector_distance


def logsoftmax(logits):
    logits = np.asarray(logits, dtype=np.float64)
    shifted = logits-logits.max(axis=1, keepdims=True)
    return (shifted-np.log(np.exp(shifted).sum(axis=1, keepdims=True))).astype(np.float32)


def oracle(logp, target, blank=0):
    """Enumerate vocabulary emissions; collapse repeats then remove blanks.

    No forward/backward recurrence, skip mask, or core normalization is reused.
    Occurrence states are assigned only after an emission path collapses correctly.
    """
    valid = []
    for path in itertools.product(range(logp.shape[1]), repeat=len(logp)):
        collapsed = [token for i, token in enumerate(path) if (i == 0 or token != path[i-1]) and token != blank]
        if collapsed != list(target):
            continue
        occurrence, previous, states = -1, blank, []
        for token in path:
            if token == blank:
                states.append(2*(occurrence+1))
            else:
                if token != previous:
                    occurrence += 1
                states.append(2*occurrence+1)
            previous = token
        valid.append((float(sum(float(logp[t, token]) for t, token in enumerate(path))), states))
    if not valid:
        return None
    maximum = max(weight for weight, _ in valid)
    scaled = [np.exp(weight-maximum) for weight, _ in valid]
    total = sum(scaled)
    gamma = np.zeros((len(logp), 2*len(target)+1), dtype=np.float64)
    for probability, (_, states) in zip(scaled, valid):
        for t, state in enumerate(states):
            gamma[t, state] += probability/total
    return dict(logZ=maximum+np.log(total), gamma=gamma)


def direct_u(q):
    u = np.zeros(len(q), dtype=np.float64)
    for k, mass in enumerate(q):
        neighbors = [t for t in range(len(q)) if abs(t-k) <= 2]
        for t in neighbors:
            u[t] += mass/len(neighbors)
    return u


class PosteriorTests(unittest.TestCase):
    def compare_oracle(self, logits, target, blank=0):
        logp = logsoftmax(logits)
        expected = oracle(logp, target, blank)
        self.assertIsNotNone(expected)
        result = CTCPosterior(logp, target, blank)
        self.assertAlmostEqual(result.log_probability, expected['logZ'], places=11)
        np.testing.assert_allclose(result.gamma, expected['gamma'], rtol=0, atol=2e-12)
        np.testing.assert_allclose(result.gamma.sum(1), 1., rtol=0, atol=2e-12)
        self.assertTrue((result.gamma[:, 1::2].sum(0) >= 1.-2e-12).all())
        hidden = np.arange(len(logp)*3, dtype=np.float32).reshape(len(logp), 3)/7
        for j in range(len(target)):
            with self.subTest(canonicalIndex=j):
                gamma = expected['gamma'][:, 2*j+1]
                q = gamma/gamma.sum()
                u = direct_u(q)
                weights = result.token_weights(j)
                np.testing.assert_allclose(weights['gamma'], gamma, rtol=0, atol=2e-12)
                np.testing.assert_allclose(weights['q'], q, rtol=0, atol=2e-12)
                np.testing.assert_allclose(weights['u'], u, rtol=0, atol=2e-12)
                expected64 = sum(q[k]*hidden[max(0,k-2):min(len(hidden),k+3)].mean(0,dtype=np.float64)
                                 for k in range(len(hidden)))
                pooled = result.pool(hidden, j)
                np.testing.assert_allclose(pooled['vector'], expected64.astype(np.float32), rtol=0, atol=1e-6)
                self.assertEqual(pooled['vector'].dtype, np.dtype('<f4'))
                self.assertEqual(weights['metadata']['state'], 2*j+1)
                self.assertEqual(weights['metadata']['tokenId'], target[j])
                self.assertFalse(weights['metadata']['targetsAccessed'])
                json.dumps(weights['metadata'], allow_nan=False)
        json.dumps(result.audit, allow_nan=False)
        return result

    def test_independent_oracle_distinct_repeat_and_empty_graphs(self):
        rng = np.random.default_rng(427)
        for frames, target in ((1, [1]), (2, [1,2]), (3, [1,1]), (4, [1,2,1]),
                               (5, [1,1]), (5, [1,2,1,2]), (4, [])):
            with self.subTest(frames=frames, target=target):
                self.compare_oracle(rng.normal(size=(frames, 3)), target)
        self.compare_oracle(rng.normal(size=(4, 3)), [0,0], blank=2)

    def test_adjacent_equals_minimum_length_and_occurrence_identity(self):
        result = self.compare_oracle([[2,0,1]]*3, [1,1])
        np.testing.assert_array_equal(result.gamma, [[0,1,0,0,0], [0,0,1,0,0], [0,0,0,1,0]])
        np.testing.assert_array_equal(result.token_weights(0)['q'], [1,0,0])
        np.testing.assert_array_equal(result.token_weights(1)['q'], [0,0,1])
        # An occurrence index is not a consonant-only ordinal: the middle token
        # represents any vowel in the complete mapping, and selects state three.
        result = self.compare_oracle([[1,2,0]]*5, [1,2,1])
        self.assertEqual(result.token_weights(1)['metadata']['tokenId'], 2)
        self.assertEqual(result.token_weights(1)['metadata']['state'], 3)

    def test_sharp_path_and_long_blank_runs(self):
        logits = np.full((7, 3), -1000.)
        logits[:, 0] = 0
        logits[3, 0], logits[3, 1] = -1000., 0.
        result = self.compare_oracle(logits, [1])
        np.testing.assert_array_equal(result.token_weights(0)['q'], [0,0,0,1,0,0,0])
        np.testing.assert_allclose(result.token_weights(0)['u'], [0,.2,.2,.2,.2,.2,0], rtol=0, atol=1e-15)
        self.assertTrue(np.isneginf(result.forward).any())
        self.assertTrue(np.isneginf(result.backward).any())

    def test_extreme_rare_canonical_path_does_not_underflow(self):
        # Absolute path probability underflows, while its conditional occupancy
        # remains exact. No exponentiation of logZ is needed by the algorithm.
        result = self.compare_oracle([[0,-1000,-1000]]*3, [1,1])
        self.assertLess(result.log_probability, -1900)
        self.assertEqual(np.exp(result.log_probability), 0.)
        np.testing.assert_array_equal(result.token_weights(0)['q'], [1,0,0])
        self.assertTrue(np.isfinite(result.gamma).all())
        result = CTCPosterior(logsoftmax([[0,-1000,-1000]]*100), [1,2])
        self.assertTrue(np.isfinite(result.token_weights(0)['q']).all())
        self.assertAlmostEqual(result.token_weights(1)['u'].sum(),1.,places=12)

    def test_long_full_vocabulary_extreme_grid_invariants(self):
        logits=np.full((1500,392),-1000.,dtype=np.float64); logits[:,0]=0.
        result=CTCPosterior(logsoftmax(logits),[1,2,1,1,3]*8)
        self.assertEqual(result.gamma.shape,(1500,81))
        self.assertLess(result.audit['frameMassMaxAbs'],result.tolerance)
        self.assertTrue(all(mass>=1.-result.tolerance for mass in result.audit['tokenOccupancies']))
        hidden=np.random.default_rng(43).normal(size=(1500,1024)).astype(np.float32)
        pooled=result.pool(hidden,19)
        self.assertEqual(pooled['vector'].shape,(1024,)); self.assertTrue(np.isfinite(pooled['vector']).all())
        self.assertAlmostEqual(pooled['q'].sum(),1.,places=12); self.assertAlmostEqual(pooled['u'].sum(),1.,places=12)
        self.assertTrue((pooled['vector']>=hidden.min(axis=0)).all())
        self.assertTrue((pooled['vector']<=hidden.max(axis=0)).all())
        json.dumps(result.audit,allow_nan=False)

    def test_impossible_guard_including_historical_negative_infinity_pitfall(self):
        from multiphone_sequence_ctc import SequenceCTC
        logp = logsoftmax([[0,0,0]])
        historical = SequenceCTC(logp, [1,1])
        self.assertEqual(historical.log_probability, -np.inf)
        self.assertTrue(np.isclose(-np.inf,-np.inf))
        with self.assertRaisesRegex(ValueError, 'Impossible'):
            CTCPosterior(logp, [1,1])
        for frames, target in ((2,[1,1]), (3,[1,1,1]), (1,[1,2])):
            with self.subTest(frames=frames, target=target),self.assertRaisesRegex(ValueError, 'Impossible'):
                CTCPosterior(logsoftmax([[0,0,0]]*frames), target)

    def test_source_normalized_edge_kernel_and_expectation(self):
        q = np.array([.75,0,0,.25,0,0,0], dtype=np.float64)
        u = box_weights(q)
        np.testing.assert_allclose(u, [.25,.3,.3,.05,.05,.05,0], rtol=0, atol=1e-15)
        self.assertAlmostEqual(u.sum(),1.,places=15)
        # The rejected global-normalization recipe has a different edge mixture.
        wrong = np.convolve(q,np.ones(5),mode='same'); wrong /= wrong.sum()
        self.assertFalse(np.allclose(u,wrong))
        hidden = np.arange(14,dtype=np.float32).reshape(7,2)
        expected = .75*hidden[:3].mean(0,dtype=np.float64)+.25*hidden[1:6].mean(0,dtype=np.float64)
        np.testing.assert_allclose(pool_hidden(hidden,u),expected.astype(np.float32),rtol=0,atol=1e-6)
        for frames in (1,2,3,4,9):
            for k in range(frames):
                delta = np.zeros(frames,dtype=np.float64); delta[k]=1.
                weights=box_weights(delta)
                direct=np.zeros(frames,dtype=np.float64); direct[max(0,k-2):min(frames,k+3)]=1./(min(frames,k+3)-max(0,k-2))
                np.testing.assert_array_equal(weights,direct)
                vectors=np.arange(frames*2,dtype=np.float32).reshape(frames,2)
                mean=vectors[max(0,k-2):min(frames,k+3)].mean(0,dtype=np.float64).astype(np.float32)
                # Numerical equality of this hand fixture does not promise bit
                # equality for arbitrary floats or replace historical pooled_vectors.
                np.testing.assert_allclose(pool_hidden(vectors,weights),mean,rtol=0,atol=1e-6)

    def test_empty_sequence_and_read_only_tables(self):
        logp=logsoftmax([[0,1,2]]*4)
        result=CTCPosterior(logp,[])
        np.testing.assert_allclose(result.gamma,np.ones((4,1)),rtol=0,atol=1e-12)
        self.assertEqual(result.audit['tokenOccupancies'],[])
        with self.assertRaisesRegex(ValueError,'canonical_index'): result.token_weights(0)
        before=result.logp.copy(); logp[:]=0
        np.testing.assert_array_equal(result.logp,before)
        for array in (result.forward,result.backward,result.gamma,result.log_gamma,result.states,result.logp):
            with self.assertRaises(ValueError): array.flat[0]=0

    def test_malformed_nonfinite_and_subset_inputs_rejected(self):
        valid=logsoftmax([[0,1,2]]*4)
        cases=[valid.astype(np.float64), valid[:0], np.zeros((2,1),np.float32), np.zeros((2,3),np.float32), valid[:,:2]]
        for value in (np.nan,np.inf,-np.inf):
            bad=valid.copy();bad[0,0]=value;cases.append(bad)
        for bad in cases:
            with self.subTest(shape=bad.shape),self.assertRaises(ValueError): CTCPosterior(bad,[1])
        for target in ([0],[True],[3],['1'],[np.int64(1)],'1',None):
            with self.subTest(target=target),self.assertRaises(ValueError): CTCPosterior(valid,target)
        for blank in (-1,3,True,np.int64(0)):
            with self.subTest(blank=blank),self.assertRaises(ValueError): CTCPosterior(valid,[1],blank)
        result=CTCPosterior(valid,[1])
        for index in (-1,1,True,np.int64(0),None):
            with self.assertRaises(ValueError): result.token_weights(index)

    def test_weights_hidden_shape_finiteness_and_distance_guards(self):
        hidden=np.ones((4,2),dtype=np.float32);u=np.ones(4,dtype=np.float64)/4
        for bad in (np.zeros(4,dtype=np.float64),np.array([np.nan]*4),-u,u.astype(np.float32),u[:3]):
            with self.assertRaises(ValueError): pool_hidden(hidden,bad)
            with self.assertRaises(ValueError): box_weights(bad)
        for bad in (hidden.astype(np.float64),hidden[:,:0],hidden[:0],np.full((4,2),np.nan,dtype=np.float32)):
            with self.assertRaises(ValueError): pool_hidden(bad,u)
        result=CTCPosterior(logsoftmax([[0,1,2]]*4),[1])
        with self.assertRaisesRegex(ValueError,'frame counts'): result.pool(hidden[:3],0)
        distances=vector_distance(np.array([1,0],np.float32),np.array([0,1],np.float32))
        self.assertAlmostEqual(distances['l2'],np.sqrt(2));self.assertEqual(distances['cosineDistance'],1.)
        self.assertIsNone(vector_distance(np.zeros(2,np.float32),np.ones(2,np.float32))['cosineDistance'])
        with self.assertRaises(ValueError): vector_distance(np.ones(2),np.ones(2))
        json.dumps(POLICY,allow_nan=False)

if __name__ == '__main__': unittest.main()
