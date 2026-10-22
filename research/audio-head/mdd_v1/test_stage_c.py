"""Tokenizer, interval, speaker and detection tests for Stage C."""
import itertools
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile
import torch
from .inventory import tokenize_jibo
from .jibo import split_children, read_interval


class JiboTests(unittest.TestCase):
    def test_multichar_and_diacritics(self):
        self.assertEqual(tokenize_jibo('ʧ t͡ʃ ʤ d͜ʒ ɑ͡ɪ e͡ɪ o͡ʊ ɑ͡ʊ ɔ͡ɪ ɚː ə̃ ɝ'),
                         (['CH', 'CH', 'JH', 'JH', 'AY', 'EY', 'OW', 'AW', 'OY', 'ER', 'AH', 'ER'], []))
        self.assertEqual(tokenize_jibo('biː̃ ɫɾ'), (['B', 'IY', 'L', 'T'], []))

    def test_unknown_and_dangling_marks_are_visible(self):
        self.assertEqual(tokenize_jibo('ʔxç'), ([], ['ʔ', 'x', 'ç']))
        self.assertEqual(tokenize_jibo('ː̃'), ([], ['ː̃']))
        self.assertEqual(tokenize_jibo('ɑ͡u'), ([], ['ɑ͡u']))
        self.assertEqual(tokenize_jibo('xxx')[1], ['x', 'x', 'x'])

    def test_sessions_group_and_reproducibility(self):
        rows = [dict(child_id=str(i), gender='female' if i%2 else 'male', task=t)
                for i in range(109) for t in ('blocks', 'letters_digits', 'blocks')]
        split = split_children(rows)
        self.assertEqual(split, split_children(list(reversed(rows))))
        self.assertEqual({s: list(split.values()).count(s) for s in set(split.values())},
                         {'train': 87, 'dev': 11, 'test': 11})

    def test_float_and_pcm_cropping(self):
        with tempfile.TemporaryDirectory() as d:
            for subtype in ('FLOAT', 'PCM_16'):
                path = Path(d)/f'{subtype}.wav'
                signal = np.arange(1600, dtype=np.float32)/1600
                if subtype == 'PCM_16':
                    signal = (signal*32767).astype(np.int16)
                wavfile.write(path, 16000, signal)
                row = dict(audio=str(path), start_seconds=.025, end_seconds=.1001)
                samples = read_interval(row)
                self.assertEqual(len(samples), 1200)
                self.assertAlmostEqual(float(samples[0]), .25, places=4)


class GOPTests(unittest.TestCase):
    def test_ctc_likelihood_matches_brute_force_and_deletion(self):
        from .gop import ctc_log_likelihoods,ctc_gop
        from .runtime import collapse
        p = torch.tensor([[.2,.7,.1],[.4,.2,.4],[.1,.2,.7]],dtype=torch.float32)
        sequences = [[],[1],[1,1],[1,2],[2,1]]
        expected = []
        for sequence in sequences:
            mass = 0.
            for path in itertools.product(range(3),repeat=3):
                decoded = collapse(path,{1:1,2:2})
                if decoded == sequence:
                    mass += math.prod(float(p[t,label]) for t,label in enumerate(path))
            expected.append(math.log(mass) if mass else -math.inf)
        np.testing.assert_allclose(ctc_log_likelihoods(p.log(),sequences),expected,atol=1e-6)
        values = ctc_log_likelihoods(p.log(),[[1,2],[2,2],[2],[1,1],[1]])
        np.testing.assert_allclose(ctc_gop(p.log(),[1,2]),
                                   [max(values[1:3])-values[0],max(values[3:])-values[0]],atol=1e-6)

    def test_repeated_impossible_prompt_is_explicit_failure(self):
        from .gop import ctc_gop
        with self.assertRaises(ValueError):
            ctc_gop(torch.tensor([[.2,.8]]).log(),[1,1])

    def test_score_labels_exclude_fractions_and_keep_l2_same_identity(self):
        from .gop import labels
        self.assertEqual(labels(dict(source='speechocean762',scores=[0,1,2,.4,1.8])),{0:1,1:1,2:0})
        row = dict(source='l2-arctic',events=[dict(canonical_index=0,canonical='S',event='substitution')])
        self.assertEqual(labels(row),{0:1})

    def test_pr_ties_and_abstained_errors(self):
        from .gop import pr_curve,coverage_curve,operating_counts
        curve = pr_curve([1,0,1,0],[.9,.9,.1,0])
        self.assertEqual([r['flagged'] for r in curve],[0,2,3,4])
        self.assertEqual(curve[1]['precision'],.5)
        coverage = coverage_curve([1,0,1,0],[.9,.9,.1,0],.5)
        self.assertEqual(coverage[-1]['coverage'],1)
        self.assertEqual(coverage[-1]['end_to_end_recall'],.5)
        self.assertEqual(operating_counts([1,0],[0,0])['precision'],None)

    def test_calibration_uses_supplied_records_only(self):
        from .gop import fit_calibration,summarize
        records = [dict(gop=float(i),disagreement=int(i>0),error=int(i>0),speaker='dev') for i in range(-4,5)]
        fit = fit_calibration(records)
        result = summarize(records,fit)
        self.assertEqual(fit['phones'],9)
        self.assertEqual(result['at_frozen_threshold']['F1'],1.)


class BucketTests(unittest.TestCase):
    def test_masked_bucket_preserves_logits_and_gradients(self):
        from transformers import Wav2Vec2Config,Wav2Vec2Model
        from .stage_c import BucketedUpperCTC
        from .train_ctc import UpperCTC
        config = Wav2Vec2Config(hidden_size=16,num_attention_heads=2,intermediate_size=32,
            num_hidden_layers=4,do_stable_layer_norm=True,num_conv_pos_embedding_groups=2,
            conv_dim=(8,),conv_stride=(2,),conv_kernel=(3,),hidden_dropout=0.,
            attention_dropout=0.,activation_dropout=0.)
        model = BucketedUpperCTC(Wav2Vec2Model(config)).eval()
        for length in (17,64,65):
            frames = torch.randn(length,16,requires_grad=True)
            direct = UpperCTC.forward(model,frames)
            padded = model(frames)
            self.assertEqual(tuple(padded.shape),(length,40))
            torch.testing.assert_close(direct,padded,atol=2e-5,rtol=2e-5)
            gradient_direct = torch.autograd.grad(direct.square().mean(),frames)[0]
            gradient_padded = torch.autograd.grad(padded.square().mean(),frames)[0]
            torch.testing.assert_close(gradient_direct,gradient_padded,atol=2e-6,rtol=2e-5)


if __name__ == '__main__':
    unittest.main()
