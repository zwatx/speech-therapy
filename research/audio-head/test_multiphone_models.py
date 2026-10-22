import unittest

import torch

from multiphone_models import AttentionPhoneRatingHead, MeanPoolPhoneRatingHead


class PhoneRatingHeadTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(17)
        self.features = torch.randn(2, 5, 8)
        self.frames = torch.tensor([[True, True, True, False, False], [True] * 5])
        self.phones = torch.tensor([[1, 3, -1], [2, 4, 5]])
        self.targets = torch.tensor([[True, True, False], [True] * 3])

    def heads(self):
        return [kind(feature_dim=8, num_phones=6, hidden_dim=7, dropout=0.1)
                for kind in (MeanPoolPhoneRatingHead, AttentionPhoneRatingHead)]

    def test_shapes_valid_simplexes_and_zero_padding(self):
        for model in self.heads():
            with self.subTest(model=type(model).__name__):
                logits, weights = model(self.features, self.frames, self.phones,
                                        self.targets, return_attention=True)
                self.assertEqual(tuple(logits.shape), (2, 3, 3))
                self.assertEqual(tuple(weights.shape), (2, 3, 5))
                torch.testing.assert_close(weights.sum(-1), self.targets.float())
                self.assertEqual(weights[0, :, 3:].count_nonzero(), 0)
                self.assertEqual(weights[~self.targets].count_nonzero(), 0)
                self.assertEqual(logits[~self.targets].count_nonzero(), 0)
                probabilities = logits[self.targets].softmax(-1)
                torch.testing.assert_close(probabilities.sum(-1), torch.ones(5))
                self.assertTrue((probabilities > 0).all())

    def test_padded_batch_matches_each_unpadded_clip(self):
        for model in self.heads():
            model.eval()
            with self.subTest(model=type(model).__name__):
                batched, weights = model(self.features, self.frames, self.phones,
                                         self.targets, return_attention=True)
                for row in range(2):
                    frame_count = int(self.frames[row].sum())
                    target_count = int(self.targets[row].sum())
                    single, single_weights = model(
                        self.features[row:row+1, :frame_count],
                        torch.ones(1, frame_count, dtype=torch.bool),
                        self.phones[row:row+1, :target_count],
                        torch.ones(1, target_count, dtype=torch.bool), return_attention=True)
                    torch.testing.assert_close(single[0], batched[row, :target_count])
                    torch.testing.assert_close(single_weights[0], weights[row, :target_count, :frame_count])

    def test_padding_values_and_extra_padding_do_not_change_predictions(self):
        modified = self.features.clone()
        modified[~self.frames] = torch.nan
        modified = torch.cat((modified, torch.full((2, 4, 8), torch.inf)), dim=1)
        frames = torch.cat((self.frames, torch.zeros(2, 4, dtype=torch.bool)), dim=1)
        phones = torch.cat((self.phones, torch.full((2, 2), 999)), dim=1)
        targets = torch.cat((self.targets, torch.zeros(2, 2, dtype=torch.bool)), dim=1)
        for model in self.heads():
            model.eval()
            with self.subTest(model=type(model).__name__):
                expected = model(self.features, self.frames, self.phones, self.targets)
                actual = model(modified, frames, phones, targets)
                torch.testing.assert_close(actual[:, :3], expected)
                self.assertEqual(actual[:, 3:].count_nonzero(), 0)

    def test_target_order_and_batch_order_only_reorder_predictions(self):
        order = torch.tensor([2, 0, 1])
        for model in self.heads():
            model.eval()
            with self.subTest(model=type(model).__name__):
                expected = model(self.features, self.frames, self.phones, self.targets)
                target_reordered = model(self.features, self.frames, self.phones[:, order], self.targets[:, order])
                torch.testing.assert_close(target_reordered, expected[:, order])
                batch_reordered = model(self.features.flip(0), self.frames.flip(0),
                                        self.phones.flip(0), self.targets.flip(0))
                torch.testing.assert_close(batch_reordered, expected.flip(0))

    def test_backward_reaches_acoustics_and_queries_but_not_padding(self):
        for model in self.heads():
            model.eval()
            features = self.features.clone().requires_grad_()
            with self.subTest(model=type(model).__name__):
                logits = model(features, self.frames, self.phones, self.targets)
                logits[self.targets].square().sum().backward()
                self.assertTrue(torch.isfinite(features.grad).all())
                self.assertGreater(float(features.grad[self.frames].abs().sum()), 0)
                self.assertEqual(features.grad[~self.frames].count_nonzero(), 0)
                for name, parameter in model.named_parameters():
                    self.assertIsNotNone(parameter.grad, name)
                    self.assertTrue(torch.isfinite(parameter.grad).all(), name)
                    self.assertGreater(float(parameter.grad.abs().sum()), 0, name)
                self.assertEqual(model.phone_embedding.weight.grad[0].count_nonzero(), 0)

    def test_masked_target_outputs_do_not_contribute_gradients(self):
        for model in self.heads():
            model.eval()
            features = self.features.clone().requires_grad_()
            logits = model(features, self.frames, self.phones, self.targets)
            logits[~self.targets].sum().backward()
            self.assertEqual(features.grad.count_nonzero(), 0)
            self.assertTrue(all(parameter.grad is None or parameter.grad.count_nonzero() == 0
                                for parameter in model.parameters()))

    def test_attention_queries_can_select_different_frames(self):
        model = AttentionPhoneRatingHead(feature_dim=2, num_phones=2, hidden_dim=2, dropout=0)
        with torch.no_grad():
            model.key_projection.weight.copy_(torch.eye(2))
            model.phone_embedding.weight.copy_(torch.eye(2) * 4)
        _, weights = model(torch.eye(2).unsqueeze(0), torch.ones(1, 2, dtype=torch.bool),
                           torch.tensor([[0, 1]]), torch.ones(1, 2, dtype=torch.bool),
                           return_attention=True)
        self.assertGreater(float(weights[0, 0, 0].detach()), 0.9)
        self.assertGreater(float(weights[0, 1, 1].detach()), 0.9)

    def test_mean_pool_weights_are_uniform_on_valid_frames(self):
        model = MeanPoolPhoneRatingHead(feature_dim=8, num_phones=6, hidden_dim=7)
        _, weights = model(self.features, self.frames, self.phones, self.targets, return_attention=True)
        torch.testing.assert_close(weights[0, 0], torch.tensor([1/3, 1/3, 1/3, 0, 0]))
        torch.testing.assert_close(weights[1, 2], torch.full((5,), 0.2))

    def test_duplicate_or_out_of_range_active_targets_are_rejected(self):
        for model in self.heads():
            for bad in (torch.tensor([[1, 1, -1], [2, 4, 5]]),
                        torch.tensor([[1, 6, -1], [2, 4, 5]]),
                        torch.tensor([[1, -1, -1], [2, 4, 5]])):
                with self.assertRaisesRegex(ValueError, "unique|outside"):
                    model(self.features, self.frames, bad, self.targets)

    def test_empty_rows_nonfinite_valid_features_and_wrong_shapes_are_rejected(self):
        for model in self.heads():
            empty_frames = self.frames.clone(); empty_frames[0] = False
            empty_targets = self.targets.clone(); empty_targets[0] = False
            bad_features = self.features.clone(); bad_features[0, 0, 0] = torch.nan
            cases = (
                (self.features, empty_frames, self.phones, self.targets),
                (self.features, self.frames, self.phones, empty_targets),
                (bad_features, self.frames, self.phones, self.targets),
                (self.features[:, :, :7], self.frames, self.phones, self.targets),
                (self.features, self.frames.float(), self.phones, self.targets),
                (self.features, self.frames, self.phones.float(), self.targets),
                (self.features, self.frames, self.phones, self.targets[:, :2]),
                (self.features[:0], self.frames[:0], self.phones[:0], self.targets[:0]),
            )
            for inputs in cases:
                with self.assertRaises(ValueError):
                    model(*inputs)

    def test_default_head_accepts_encoder_width_and_variable_target_count(self):
        for kind in (MeanPoolPhoneRatingHead, AttentionPhoneRatingHead):
            model = kind().eval()
            for target_count in (1, 24):
                logits = model(torch.randn(1, 3, 768), torch.ones(1, 3, dtype=torch.bool),
                               torch.arange(target_count).unsqueeze(0),
                               torch.ones(1, target_count, dtype=torch.bool))
                self.assertEqual(tuple(logits.shape), (1, target_count, 3))

    def test_invalid_architecture_configuration_is_rejected(self):
        for kind in (MeanPoolPhoneRatingHead, AttentionPhoneRatingHead):
            for settings in ({"feature_dim": 0}, {"num_phones": -1}, {"hidden_dim": 1.5},
                             {"dropout": -0.1}, {"dropout": 1.0}, {"dropout": float("nan")}):
                with self.assertRaises(ValueError):
                    kind(**settings)


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main()
