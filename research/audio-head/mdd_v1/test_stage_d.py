"""Synthetic checks of full CTC features, label isolation, metrics and bootstrap."""
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch
from scipy.special import expit

from .gop import labels
from .inventory import PHONE_TO_ID
from .runtime import collapse
from .stage_d_features import extract, forced_spans, gop_vector, FEATURE_NAMES, word_positions
from .stage_d_metrics import ranking, ece, speaker_bootstrap
from .stage_d_models import fit_platt, platt_logits


class FeatureTests(unittest.TestCase):
    def test_full_vector_matches_enumerated_ctc_mass(self):
        rng = np.random.default_rng(2)
        p = rng.uniform(.01,1.,(2,40))
        p /= p.sum(1,keepdims=True)
        matrix, clipped = gop_vector(torch.tensor(p).float().log(),[1])
        masses = {}
        for path in itertools.product(range(40),repeat=2):
            decoded = tuple(collapse(path,{i:i for i in range(1,40)}))
            masses[decoded] = masses.get(decoded,0.) + math.prod(p[t,label] for t,label in enumerate(path))
        self.assertEqual(matrix.shape,(1,40))
        self.assertEqual(matrix[0,0],0.)
        self.assertEqual(clipped,0)
        expected = [0.] + [math.log(masses[(i,)])-math.log(masses[(1,)]) for i in range(2,40)]
        expected += [math.log(masses[()])-math.log(masses[(1,)])]
        np.testing.assert_allclose(matrix[0],expected,atol=2e-6)

    def test_repeated_ctc_states_separate_and_impossible_fails(self):
        values = np.array([[.01,.98,.01],[.98,.01,.01],[.01,.98,.01]])
        self.assertEqual(forced_spans(np.log(values),[1,1]),[(0,1),(2,3)])
        with self.assertRaises(ValueError):
            forced_spans(np.log(values[:2]),[1,1])
        with self.assertRaises(ValueError):
            gop_vector(torch.full((1,40),1/40).log(),[1,1])

    def test_features_ignore_labels_and_manual_times(self):
        p = torch.full((7,40),.001)
        p[:,0] = .5
        p[1:3,PHONE_TO_ID['R']] = .95
        p[4:6,PHONE_TO_ID['L']] = .95
        p /= p.sum(1,keepdim=True)
        row = dict(id='so:demo',source='speechocean762',speaker='1',canonical=['R','L'],scores=[1,2])
        x, records, _ = extract(row,p.log(),[['R','L']])
        changed = dict(row,scores=[.8,0],events=[{'start':99,'end':100}],age=90,speaker='else')
        xx, changed_records, _ = extract(changed,p.log(),[['R','L']])
        np.testing.assert_array_equal(x,xx)
        self.assertEqual([r['error'] for r in records],[1,0])
        self.assertEqual([r['error'] for r in changed_records],[None,1])
        self.assertEqual(x.shape,(2,len(FEATURE_NAMES)))
        self.assertEqual(x[0,FEATURE_NAMES.index('previous_<boundary>')],1.)
        self.assertEqual(x[1,FEATURE_NAMES.index('next_<boundary>')],1.)
        self.assertEqual(x[0,FEATURE_NAMES.index('next_L')],1.)
        self.assertEqual(x[1,FEATURE_NAMES.index('word_phone_position')],1.)
        np.testing.assert_allclose(x[:,FEATURE_NAMES.index('span_seconds')],[.04,.04])

    def test_word_mismatch_is_not_silently_repaired(self):
        self.assertEqual(word_positions(['R','L'],None),[(-1.,-1.,0.)]*2)
        with self.assertRaises(ValueError):
            word_positions(['R','L'],[['R']])
        self.assertEqual(labels(dict(source='speechocean762',scores=[0,.2,.8,1,1.2,2])),{0:1,3:1,5:0})


class MetricTests(unittest.TestCase):
    def test_tied_ap_and_zero_error_phone(self):
        value = ranking([1,0,1,0],[.9,.9,.1,0])
        self.assertAlmostEqual(value['AP'],.5*.5+.5*2/3)
        self.assertEqual(value['recall_at_precision']['0.9'],0.)
        self.assertIsNone(ranking([0,0],[1,0])['AP'])
        weighted = ranking([1,0,1],[.9,.9,.1],weights=[2,0,1])
        explicit = ranking([1,1,1],[.9,.9,.1])
        self.assertEqual(weighted,explicit)

    def test_speaker_bootstrap_matches_explicit_resampling(self):
        records = [dict(speaker=s,error=y) for s,y in [('a',1),('a',0),('b',1),('c',0)]]
        scores = np.array([.8,.7,.3,.2])
        actual = speaker_bootstrap(records,scores,repeats=60,seed=6)
        rng = np.random.default_rng(6)
        expected = []
        for _ in range(60):
            sampled = rng.integers(0,3,3)
            indices = [i for j in sampled for i,r in enumerate(records) if r['speaker'] == ['a','b','c'][j]]
            metric = ranking([records[i]['error'] for i in indices],scores[indices])
            if metric['AP'] is not None:
                expected.append((metric['AP'],metric['recall_at_precision']['0.9']))
        ci = np.percentile(expected,[2.5,97.5],axis=0)
        np.testing.assert_allclose(actual['AP'],ci[:,0])
        np.testing.assert_allclose(actual['recall_at_precision_0_9'],ci[:,1])
        self.assertEqual(actual['valid'],len(expected))

    def test_equal_width_ece_endpoints_and_platt_monotonicity(self):
        self.assertEqual(ece([0,1],[0.,1.])['value'],0.)
        self.assertAlmostEqual(ece([0,1],[.25,.75])['value'],.25)
        x = np.arange(-5,6,dtype=float)
        y = (x > 0).astype(int)
        fit = fit_platt(x,y)
        z = platt_logits(x,fit)
        self.assertTrue(np.all(np.diff(z)>0))
        self.assertEqual(fit['phones'],11)
        self.assertTrue(np.isfinite(expit(z)).all())

    def test_fit_receipt_preserves_model_after_interrupted_scoring(self):
        from . import stage_d_models as models
        from .stage_d import sha
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            model_path = path/'mlp.pt'
            model_path.write_bytes(b'completed-model')
            receipt = dict(candidate='mlp',status='started')
            receipt_path = path/'fit-mlp.json'
            receipt_path.write_text(json.dumps(receipt))
            with patch.object(models,'RUN',path), patch.object(models,'train_mlp',side_effect=AssertionError):
                with self.assertRaises(RuntimeError):
                    models.fit_candidate('mlp',None,None,None,{},0.)
                self.assertEqual(model_path.read_bytes(),b'completed-model')
                receipt.update(status='complete',fit_seconds=12.5,model_sha256=sha(model_path))
                receipt_path.write_text(json.dumps(receipt))
                # No score JSON exists: a resumed scoring step must reuse this model.
                result = models.fit_candidate('mlp',None,None,None,{},0.)
                self.assertEqual(result['fit_seconds'],12.5)
                self.assertEqual(model_path.read_bytes(),b'completed-model')

    def test_completed_evaluation_guard_before_any_data_access(self):
        from . import stage_d, stage_d_models
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'evaluation-started.json').write_text('{}')
            (path/'selection.json').write_text('{}')
            with patch.object(stage_d,'RUN',path), patch.object(stage_d,'rows_by_group',side_effect=AssertionError):
                with self.assertRaises(FileExistsError):
                    stage_d.evaluate()
            with patch.object(stage_d_models,'RUN',path), patch.object(stage_d_models,'load_group',side_effect=AssertionError):
                with self.assertRaises(FileExistsError):
                    stage_d_models.fit()


if __name__ == '__main__':
    unittest.main()
