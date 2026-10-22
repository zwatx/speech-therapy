"""Warm identity, real branch gradients, update equivalence and fit-only moments."""
import copy
import unittest
import torch
from multiphone_models import MeanPoolPhoneRatingHead
from multiphone_sequence_head import SequenceEvidenceHead, fitting_moments


class SequenceHeadTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        torch.manual_seed(7)
        self.base = MeanPoolPhoneRatingHead(feature_dim=1037).eval()
        self.features = torch.randn(67, 1, 1037)
        self.sequence = torch.randn(67, 1, 4)
        self.extended = torch.cat((self.features, self.sequence), -1)
        self.ids = (torch.arange(67) % 23)[:, None]
        self.mask = torch.ones(67, 1, dtype=torch.bool)

    def make_head(self, enabled=True):
        model = SequenceEvidenceHead(enabled=enabled).eval()
        model.load_warm(self.base.state_dict())
        return model

    def test_zero_branch_matches_original_logits_and_attention_exactly(self):
        for size in (1, 3, 64, 67):
            args = (self.mask[:size], self.ids[:size], self.mask[:size])
            expected = self.base(self.features[:size], *args, return_attention=True)
            for enabled in (True, False):
                actual = self.make_head(enabled)(self.extended[:size], *args, return_attention=True)
                for a, b in zip(actual, expected):
                    self.assertTrue(torch.equal(a, b))

    def test_gradient_updates_branch_and_sequence_affects_prediction(self):
        model = self.make_head()
        optimizer = torch.optim.AdamW(model.parameters(), lr=3e-5, weight_decay=.01)
        args = (self.mask, self.ids, self.mask)
        logits = model(self.extended, *args)
        loss = -logits.log_softmax(-1)[..., 0].mean()
        loss.backward()
        self.assertGreater(float(model.sequence_projection.weight.grad.norm()), 0)
        self.assertGreater(float(model.acoustic_projection[0].weight.grad.norm()), 0)
        optimizer.step()
        changed = self.extended.clone(); changed[..., -4:] += 3
        self.assertFalse(torch.equal(model(changed, *args), model(self.extended, *args)))
        clone = self.make_head(); clone.load_state_dict(model.state_dict())
        self.assertTrue(torch.equal(model(self.extended, *args), clone(self.extended, *args)))

    def test_disabled_branch_has_exact_original_update_and_optimizer_state(self):
        model = self.make_head(False)
        optimizers = [torch.optim.AdamW(n.parameters(), lr=3e-5, weight_decay=.01)
                      for n in (self.base, model)]
        labels = torch.rand(67, 1, 3); labels /= labels.sum(-1, keepdim=True)
        for start in (0, 64):
            sl = slice(start, start+64)
            for net, values, opt in zip((self.base, model), (self.features, self.extended), optimizers):
                opt.zero_grad(set_to_none=True)
                z = net(values[sl], self.mask[sl], self.ids[sl], self.mask[sl])
                loss = -(labels[sl]*z.log_softmax(-1)).sum(-1).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5., error_if_nonfinite=True)
                opt.step()
        for key, value in self.base.state_dict().items():
            self.assertTrue(torch.equal(value, model.state_dict()[key]), key)
        a, b = [o.state_dict()['state'] for o in optimizers]
        self.assertEqual(a.keys(), b.keys())
        for k in a:
            for field in a[k]: self.assertTrue(torch.equal(a[k][field], b[k][field]))
        self.assertIsNone(model.sequence_projection.weight.grad)

    def test_moments_only_use_explicit_fit_rows_and_population_std(self):
        values = torch.tensor([[0., 2., 4., 1.], [2., 4., 8., 1.], [100., 200., 300., 400.]])
        mean, std = fitting_moments(values, [0, 1])
        self.assertTrue(torch.equal(mean, torch.tensor([1., 3., 6., 1.])))
        self.assertTrue(torch.equal(std, torch.tensor([1., 1., 2., 1e-6])))
        values[2] *= -100
        repeated = fitting_moments(values, [0, 1])
        self.assertTrue(all(torch.equal(a, b) for a, b in zip((mean, std), repeated)))
        for indices in ([], [0, 0], [-1], [3], [True]):
            with self.assertRaises(ValueError): fitting_moments(values, indices)
        with self.assertRaises(ValueError): fitting_moments(values.double(), [0])

    def test_bad_state_shape_and_nonfinite_values_fail(self):
        model = self.make_head()
        bad = copy.deepcopy(self.base.state_dict()); bad.pop('phone_embedding.weight')
        with self.assertRaises(ValueError): model.load_warm(bad)
        args = (self.mask, self.ids, self.mask)
        for features in (self.features, self.extended.repeat(1, 2, 1)):
            with self.assertRaises(ValueError): model(features, *args)
        for column in (0, -1):
            features = self.extended.clone(); features[0, 0, column] = torch.nan
            with self.assertRaises(ValueError): model(features, *args)


if __name__ == '__main__': unittest.main()
