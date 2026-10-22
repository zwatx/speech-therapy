"""Offline checks for the pinned, frozen HuBERT engineering encoder."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import torch
from torch import nn

from data import digest, make_fixtures, read_json, write_json
from encoders import HubertEncoder, SpectralEncoder, load_encoder
from pipeline import infer, load_head, train


class FakeHubertModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(1))
        self.last_input = None

    def forward(self, input_values):
        self.last_input = input_values.detach().clone()
        return SimpleNamespace(last_hidden_state=torch.ones((1, 5, 768)) * self.weight)


class HubertEncoderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.content = {
            "config.json": b'{"model_type":"hubert","hidden_size":768}',
            "preprocessor_config.json": json.dumps({
                "feature_extractor_type": "Wav2Vec2FeatureExtractor", "do_normalize": True,
                "sampling_rate": 16000, "feature_size": 1, "return_attention_mask": False,
            }).encode(),
            "pytorch_model.bin": b"mocked runtime weights",
        }
        self.identity = copy.deepcopy(HubertEncoder.identity)
        self.identity["artifactSha256"] = {name: digest(body) for name, body in self.content.items()}
        self.identity["artifactBytes"] = {name: len(body) for name, body in self.content.items()}
        for name, body in self.content.items():
            (self.root / name).write_bytes(body)

    def download(self, model, filename, **kwargs):
        self.assertEqual(model, "facebook/hubert-base-ls960")
        self.assertEqual(kwargs["revision"], "dba3bb02fda4248b6e082697eee756de8fe8aa8a")
        self.assertTrue(kwargs["local_files_only"])
        return str(self.root / filename)

    def test_assets_verified_then_frozen_model_uses_normalized_single_clip(self):
        model = FakeHubertModel()
        with patch.object(HubertEncoder, "identity", self.identity), patch(
                "huggingface_hub.hf_hub_download", side_effect=self.download) as download, patch(
                "transformers.HubertModel.from_pretrained", return_value=model) as loader:
            encoder = load_encoder("hubert-base-ls960", self.root)
        self.assertEqual(download.call_count, 3)
        loader.assert_called_once_with(str(self.root), local_files_only=True,
                                       use_safetensors=False, weights_only=True)
        self.assertTrue(encoder.processor.do_normalize)
        self.assertFalse(encoder.processor.return_attention_mask)
        self.assertFalse(model.training)
        self.assertTrue(all(not parameter.requires_grad for parameter in model.parameters()))
        samples = torch.linspace(-0.4, 0.6, 1600)
        frames = encoder(samples)
        self.assertEqual(tuple(frames.shape), (5, 768))
        self.assertEqual(frames.device.type, "cpu")
        self.assertTrue(frames.is_contiguous())
        self.assertAlmostEqual(float(model.last_input.mean()), 0.0, places=5)
        self.assertAlmostEqual(float(model.last_input.var(unbiased=False)), 1.0, places=4)

    def test_each_corrupt_or_truncated_asset_fails_before_model_load(self):
        for name, body in self.content.items():
            for bad in (b"x" * len(body), body[:-1]):
                with self.subTest(asset=name, size=len(bad)):
                    (self.root / name).write_bytes(bad)
                    with patch.object(HubertEncoder, "identity", self.identity), patch(
                            "huggingface_hub.hf_hub_download", side_effect=self.download), patch(
                            "transformers.HubertModel.from_pretrained") as loader:
                        with self.assertRaisesRegex(ValueError, "integrity failure"):
                            HubertEncoder(self.root)
                        loader.assert_not_called()
                    (self.root / name).write_bytes(body)

    def test_verified_but_wrong_preprocessing_is_rejected_before_model_load(self):
        config = json.loads(self.content["preprocessor_config.json"])
        config["do_normalize"] = False
        body = json.dumps(config).encode()
        (self.root / "preprocessor_config.json").write_bytes(body)
        self.identity["artifactSha256"]["preprocessor_config.json"] = digest(body)
        self.identity["artifactBytes"]["preprocessor_config.json"] = len(body)
        with patch.object(HubertEncoder, "identity", self.identity), patch(
                "huggingface_hub.hf_hub_download", side_effect=self.download), patch(
                "transformers.HubertModel.from_pretrained") as loader:
            with self.assertRaisesRegex(ValueError, "preprocessing mismatch"):
                HubertEncoder(self.root)
            loader.assert_not_called()

    def test_checkpoint_preserves_identity_and_rejects_tampering(self):
        class FixtureEncoder:
            identity = HubertEncoder.identity

            def __call__(self, samples):
                small = SpectralEncoder()(samples)
                return torch.nn.functional.pad(small, (0, 768 - small.shape[1]))

        manifest = make_fixtures(self.root / "fixtures")
        with patch("pipeline.load_encoder", return_value=FixtureEncoder()):
            report = train(manifest, self.root / "run", "hubert-base-ls960", self.root / "cache", steps=2)
            exported = infer(self.root / "run", manifest.parent / "test-00.wav",
                             self.root / "posteriors.json", self.root / "cache")
        self.assertEqual(report["encoder"], HubertEncoder.identity)
        self.assertEqual(exported["encoder"], HubertEncoder.identity)
        for key in ("calibrated", "productionEligible", "learnerFeedbackEligible"):
            self.assertIs(exported[key], False)
        metadata_path = self.root / "run" / "checkpoint.json"
        changed = read_json(metadata_path)
        changed["encoder"]["revision"] = "unverified"
        write_json(metadata_path, changed)
        with self.assertRaisesRegex(ValueError, "altered encoder identity"):
            load_head(metadata_path.parent)


if __name__ == "__main__":
    unittest.main()
