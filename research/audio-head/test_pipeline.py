import copy
import json
from pathlib import Path
import tempfile
import struct
import unittest
from unittest.mock import patch
import wave

import torch
from torch import nn

from data import BLANK, digest, load_manifest, load_pcm, make_fixtures, read_json, write_json
from encoders import SpectralEncoder, Wav2VecEncoder, WavLMEncoder
from pipeline import (ctc_loss, frame_posteriors, greedy_decode, infer, load_head,
                      pack, train, validate_ctc_length)


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.path = make_fixtures(cls.root / "fixtures")
        cls.original = read_json(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.manifest = copy.deepcopy(self.original)

    def validate(self):
        path = self.path.parent / "test-manifest.json"
        write_json(path, self.manifest)
        return load_manifest(path)

    def test_valid_varied_audio_and_three_splits(self):
        _, rows = self.validate()
        self.assertEqual(len(rows), 30)
        self.assertGreater(len({len(row["samples"]) for row in rows}), 3)
        self.assertEqual({row["split"] for row in rows}, {"train", "calibration", "test"})

    def test_split_leakage_for_each_identity(self):
        for field in ("speakerHash", "householdHash"):
            with self.subTest(field=field):
                self.manifest = copy.deepcopy(self.original)
                self.manifest["items"][-1][field] = self.manifest["items"][0][field]
                with self.assertRaisesRegex(ValueError, "split overlap"):
                    self.validate()

    def test_duplicate_audio_even_across_splits(self):
        first, last = self.manifest["items"][0], self.manifest["items"][-1]
        last["audioSha256"], last["audioPath"] = first["audioSha256"], first["audioPath"]
        with self.assertRaisesRegex(ValueError, "Duplicate audio"):
            self.validate()

    def test_identical_pcm_with_different_wav_metadata_rejected(self):
        first, last = self.manifest["items"][0], self.manifest["items"][-1]
        original = (self.path.parent / first["audioPath"]).read_bytes()
        changed = bytearray(original + b"JUNK" + struct.pack("<I", 4) + b"meta")
        struct.pack_into("<I", changed, 4, len(changed) - 8)
        audio = self.path.parent / "duplicate-with-metadata.wav"
        audio.write_bytes(changed)
        last["audioPath"], last["audioSha256"] = audio.name, digest(changed)
        self.assertNotEqual(first["audioSha256"], last["audioSha256"])
        with self.assertRaisesRegex(ValueError, "Duplicate decoded PCM"):
            self.validate()

    def test_unsupported_phone_and_blank_target(self):
        for token in ("unlisted", BLANK):
            self.manifest["items"][0]["producedPhones"] = [token]
            with self.assertRaisesRegex(ValueError, "Unsupported phone"):
                self.validate()

    def test_prompt_targets_and_release_flags_rejected(self):
        self.manifest["labelSource"] = "expected-prompt"
        with self.assertRaisesRegex(ValueError, "produced phones"):
            self.validate()
        self.manifest = copy.deepcopy(self.original)
        self.manifest["productionEligible"] = True
        with self.assertRaisesRegex(ValueError, "ineligible"):
            self.validate()

    def test_wrong_hash_and_path_escape_rejected(self):
        self.manifest["items"][0]["audioSha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.validate()
        self.manifest = copy.deepcopy(self.original)
        self.manifest["items"][0]["audioPath"] = "../../outside.wav"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.validate()

    def test_required_partitions_and_duplicate_vocabulary(self):
        self.manifest["items"] = [i for i in self.manifest["items"] if i["split"] != "test"]
        with self.assertRaisesRegex(ValueError, "All three"):
            self.validate()
        self.manifest = copy.deepcopy(self.original)
        self.manifest["vocabulary"].append("tone-a")
        with self.assertRaisesRegex(ValueError, "Vocabulary"):
            self.validate()

    def test_truncated_and_wrong_rate_audio(self):
        valid = self.path.parent / self.original["items"][0]["audioPath"]
        bad = self.root / "truncated.wav"
        bad.write_bytes(valid.read_bytes()[:-4])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            load_pcm(bad)
        bad = self.root / "wrong-rate.wav"
        with wave.open(str(bad), "wb") as wav:
            wav.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\0\0" * 3000)
        with self.assertRaisesRegex(ValueError, "16 kHz"):
            load_pcm(bad)

    def test_silent_and_clipped_audio(self):
        for sample in (b"\0\0", b"\xff\x7f"):
            bad = self.root / "bad-level.wav"
            with wave.open(str(bad), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(sample * 3000)
            with self.assertRaises(ValueError):
                load_pcm(bad)

    def test_unknown_fields_rejected(self):
        self.manifest["prompt"] = "ball"
        with self.assertRaisesRegex(ValueError, "Unsupported manifest"):
            self.validate()


class CtcTests(unittest.TestCase):
    def test_repeated_phone_requires_intervening_blank(self):
        validate_ctc_length([1, 1], 3)
        with self.assertRaisesRegex(ValueError, "requires 3"):
            validate_ctc_length([1, 1], 2)
        self.assertEqual(greedy_decode([1, 1, 0, 1, 2, 2], [BLANK, "a", "b"]), ["a", "a", "b"])

    def test_loss_matches_enumerated_repeated_phone_path(self):
        # For [a,a] in exactly 3 frames, the only legal alignment is [a,blank,a].
        logits = torch.tensor([[[0.1, 0.9], [0.8, 0.2], [0.2, 0.8]]]).log()
        batch = (logits, torch.tensor([1, 1]), torch.tensor([3]), torch.tensor([2]))
        loss = ctc_loss(nn.Identity(), batch)
        expected = -torch.log(torch.tensor(0.9 * 0.8 * 0.8)) / 2
        self.assertAlmostEqual(float(loss), float(expected), places=6)

    def test_padding_has_no_loss_or_gradient_effect(self):
        torch.manual_seed(3)
        rows = [{"features": torch.randn(4, 3), "targetPhones": ["a"]},
                {"features": torch.randn(8, 3), "targetPhones": ["a", "a"]}]
        batch = pack(rows, [BLANK, "a"])
        features = batch[0].clone().requires_grad_(True)
        head = nn.Linear(3, 2)
        loss = ctc_loss(head, (features, *batch[1:]))
        loss.backward()
        self.assertTrue(torch.equal(features.grad[0, 4:], torch.zeros_like(features.grad[0, 4:])))
        altered = features.detach().clone()
        altered[0, 4:] = 900
        self.assertAlmostEqual(float(loss.detach()), float(ctc_loss(head, (altered, *batch[1:])).detach()), places=6)

    def test_posteriors_are_complete_normalized_and_reject_nan(self):
        head = nn.Linear(5, 3)
        vocabulary = [BLANK, "a", "b"]
        frames = frame_posteriors(head, torch.randn(7, 5), vocabulary)
        self.assertEqual(len(frames), 7)
        for frame in frames:
            self.assertEqual(set(frame), set(vocabulary))
            self.assertAlmostEqual(sum(frame.values()), 1, places=6)
        with self.assertRaisesRegex(ValueError, "Invalid frame"):
            frame_posteriors(head, torch.full((3, 5), float("nan")), vocabulary)

    def test_pinned_encoder_corruption_rejected_before_load(self):
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "config.json"
            corrupt.write_text("{}")
            with patch("huggingface_hub.hf_hub_download", return_value=str(corrupt)):
                with self.assertRaisesRegex(ValueError, "integrity failure"):
                    Wav2VecEncoder(Path(directory))


class WavLMTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = {
            "config.json": b'{"model_type":"wavlm"}',
            "preprocessor_config.json": json.dumps({"feature_extractor_type": "Wav2Vec2FeatureExtractor",
                "do_normalize": False, "sampling_rate": 16000, "feature_size": 1,
                "return_attention_mask": True}).encode(),
            "pytorch_model.bin": b"small test checkpoint; runtime loader is mocked",
        }
        self.identity = copy.deepcopy(WavLMEncoder.identity)
        self.identity["artifactSha256"] = {name: digest(body) for name, body in self.content.items()}
        self.identity["artifactBytes"] = {name: len(body) for name, body in self.content.items()}
        for name, body in self.content.items():
            (self.root / name).write_bytes(body)

    def download(self, model, filename, **kwargs):
        self.assertEqual(model, "microsoft/wavlm-base-plus")
        self.assertEqual(kwargs["revision"], WavLMEncoder.identity["revision"])
        self.assertTrue(kwargs["local_files_only"])
        return str(self.root / filename)

    def test_all_assets_checked_before_runtime_and_model_stays_frozen(self):
        # Only the weight runtime is mocked; parse a real local feature-extractor config.
        model = nn.Linear(1, 1)
        with patch.object(WavLMEncoder, "identity", self.identity), patch(
                "huggingface_hub.hf_hub_download", side_effect=self.download) as download, patch(
                "transformers.WavLMModel.from_pretrained", return_value=model) as loader:
            encoder = WavLMEncoder(self.root)
        self.assertEqual(download.call_count, 3)
        loader.assert_called_once_with(str(self.root), local_files_only=True, use_safetensors=False, weights_only=True)
        self.assertFalse(encoder.processor.do_normalize)
        self.assertTrue(encoder.processor.return_attention_mask)
        self.assertFalse(encoder.model.training)
        self.assertTrue(all(not parameter.requires_grad for parameter in encoder.model.parameters()))

    def test_each_asset_corruption_fails_before_runtime(self):
        for name, body in self.content.items():
            for bad in (b"x" * len(body), body[:-1]):
                with self.subTest(name=name, size=len(bad)):
                    (self.root / name).write_bytes(bad)
                    with patch.object(WavLMEncoder, "identity", self.identity), patch(
                            "huggingface_hub.hf_hub_download", side_effect=self.download), patch(
                            "transformers.WavLMModel.from_pretrained") as loader:
                        with self.assertRaisesRegex(ValueError, "integrity failure"):
                            WavLMEncoder(self.root)
                        loader.assert_not_called()
                    (self.root / name).write_bytes(body)

    def test_checkpoint_export_keeps_exact_encoder_license_and_rejects_changes(self):
        class FixtureEncoder:
            identity = WavLMEncoder.identity

            def __call__(self, samples):
                small = SpectralEncoder()(samples)
                return torch.nn.functional.pad(small, (0, 768 - small.shape[1]))

        manifest = make_fixtures(self.root / "fixtures")
        with patch("pipeline.load_encoder", return_value=FixtureEncoder()):
            report = train(manifest, self.root / "run", "wavlm-base-plus", self.root / "cache", steps=2)
            exported = infer(self.root / "run", manifest.parent / "test-00.wav", self.root / "posterior.json", self.root / "cache")
        self.assertEqual(report["encoder"], WavLMEncoder.identity)
        self.assertEqual(exported["encoder"]["licenseEvidence"], WavLMEncoder.identity["licenseEvidence"])
        for key in ("calibrated", "productionEligible", "learnerFeedbackEligible"):
            self.assertIs(exported[key], False)
        path = self.root / "run" / "checkpoint.json"
        changed = read_json(path)
        changed["encoder"]["licenseEvidence"]["basis"] = "MIT"
        write_json(path, changed)
        with self.assertRaisesRegex(ValueError, "altered encoder identity"):
            load_head(path.parent)


class TrainingTests(unittest.TestCase):
    def test_explicit_head_seed_is_independent_of_encoder_rng_and_default_is_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = make_fixtures(root / "fixtures")
            reports = []
            for index, consumed in enumerate((3, 100)):
                def encoder_factory(*args, **kwargs):
                    torch.rand(consumed)
                    return SpectralEncoder()
                with patch("pipeline.load_encoder", side_effect=encoder_factory):
                    reports.append(train(manifest, root / f"seeded-{index}", "spectral-engineering-v1",
                                         root / "cache", steps=2, head_seed=7))
            self.assertEqual(reports[0]["initialHeadSha256"], reports[1]["initialHeadSha256"])
            self.assertEqual(reports[0]["curve"], reports[1]["curve"])
            self.assertEqual(reports[0]["headInitializationSeed"], 7)
            # No optional seed: reproduce the old ordering (global seed, encoder, then linear head).
            torch.manual_seed(7)
            SpectralEncoder()
            expected = nn.Linear(65, 3)
            expected_sha = digest(b"".join(p.detach().numpy().astype("<f4").tobytes()
                                           for p in (expected.weight, expected.bias)))
            legacy = train(manifest, root / "legacy", "spectral-engineering-v1", root / "cache", steps=2)
            self.assertIsNone(legacy["headInitializationSeed"])
            self.assertEqual(legacy["initialHeadSha256"], expected_sha)
            with self.assertRaisesRegex(ValueError, "Head initialization seed"):
                train(manifest, root / "invalid", "spectral-engineering-v1", root / "cache", steps=2, head_seed=-1)

    def test_real_optimization_reproducible_export_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = make_fixtures(root / "fixtures")
            reports = [train(manifest, root / f"run{i}", "spectral-engineering-v1", root / "cache",
                             steps=40, seed=17, learning_rate=0.02) for i in range(2)]
            self.assertLess(reports[0]["splits"]["train"]["ctcLoss"], reports[0]["initialTrain"]["ctcLoss"])
            self.assertEqual(reports[0]["curve"], reports[1]["curve"])
            head, metadata = load_head(root / "run0")
            audio = root / "fixtures" / "test-00.wav"
            expected = frame_posteriors(head, SpectralEncoder()(load_pcm(audio)), metadata["vocabulary"])
            result = infer(root / "run0", audio, root / "posteriors.json", root / "cache")
            self.assertEqual(result["frames"], expected)
            self.assertIs(result["productionEligible"], False)
            self.assertIs(result["learnerFeedbackEligible"], False)
            self.assertIs(result["calibrated"], False)
            self.assertNotIn("pCorrect", result)
            with self.assertRaisesRegex(ValueError, "already exists"):
                train(manifest, root / "run0", "spectral-engineering-v1", root / "cache")
            weights = root / "run0" / "head.pt"
            weights.write_bytes(weights.read_bytes() + b"corrupt")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                load_head(root / "run0")


if __name__ == "__main__":
    unittest.main()
