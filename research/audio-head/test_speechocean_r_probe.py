import tempfile
import tarfile
import unittest
import wave
import hashlib
from pathlib import Path
from unittest.mock import patch
import io

import numpy as np
import torch

from speechocean_r_probe import (AUTHORITY, extract_features, fit_ridge, load_wavlm_recipe,
                                 metrics, predict_ridge,
                                 rating_baseline, read_rating_pcm, selected_r,
                                 transcript_word_baseline, validation_partition,
                                 verify_selected_archive_audio, wav_map)


class SelectionTests(unittest.TestCase):
    def test_exactly_one_canonical_r_uses_continuous_rating(self):
        one = {"words": [{"text": "RED", "phones": ["R", "EH0", "D"],
                          "phones-accuracy": [1.4, 2, 2]}]}
        self.assertEqual(selected_r(one), ("RED", 1.4))
        self.assertIsNone(selected_r({"words": [{"text": "BED", "phones": ["B", "EH0", "D"],
                                                      "phones-accuracy": [2, 2, 2]}]}))
        self.assertIsNone(selected_r({"words": [one["words"][0], one["words"][0]]}))

    def test_speaker_group_validation_keeps_test_untouched(self):
        rows = [{"split": "train", "speaker": f"SPEAKER{i:04d}"} for i in range(124) for _ in range(2)]
        rows += [{"split": "test", "speaker": f"SPEAKER{i:04d}"} for i in range(124, 129)]
        fit, val, test = validation_partition(rows)
        self.assertEqual((len(fit), len(val), len(test)), (198, 50, 5))
        self.assertFalse({rows[i]["speaker"] for i in fit} & {rows[i]["speaker"] for i in val})
        self.assertTrue(all(rows[i]["split"] == "test" for i in test))


class AudioTests(unittest.TestCase):
    def test_full_clip_longer_than_ctc_limit_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long.wav"
            samples = np.zeros(16000 * 6, dtype="<i2")
            samples[-1] = 1234
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(samples.tobytes())
            loaded = read_rating_pcm(path)
            self.assertEqual(len(loaded), 16000 * 6)
            self.assertAlmostEqual(float(loaded[-1]), 1234 / 32768)
            with self.assertRaisesRegex(ValueError, "changed after archive verification"):
                read_rating_pcm(path, hashlib.sha256(b"different audio").hexdigest())

    def test_wav_map_rejects_speaker_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "wav.scp").write_text("000000001 WAVE/SPEAKER0002/000000001.WAV\n")
            with self.assertRaisesRegex(ValueError, "speaker map"):
                wav_map(root / "wav.scp", {"000000001": "0001"}, root)

    def test_extracted_wav_must_equal_archive_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "corpus"
            wav = audio / "WAVE/SPEAKER0001/000000001.WAV"
            wav.parent.mkdir(parents=True)
            wav.write_bytes(b"original bytes")
            archive = root / "audio.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                payload = b"original bytes"
                info = tarfile.TarInfo("speechocean762/WAVE/SPEAKER0001/000000001.WAV")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            row = {"audioPath": str(wav)}
            self.assertEqual(len(verify_selected_archive_audio(archive, audio, [row])), 1)
            wav.write_bytes(b"altered bytes")
            with self.assertRaisesRegex(ValueError, "differs from pinned archive"):
                verify_selected_archive_audio(archive, audio, [row])

    def test_completed_feature_cache_rejects_changed_bytes_or_recipe(self):
        class FixtureEncoder:
            identity = {"kind": "fixture", "width": 768}

            def __init__(self, *_args, **_kwargs):
                pass

            def __call__(self, _samples):
                return torch.ones((3, 768), dtype=torch.float32)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav = root / "one.wav"
            with wave.open(str(wav), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(np.zeros(16000, dtype="<i2").tobytes())
            rows = [{"id": "000000001", "split": "train", "speaker": "0001",
                     "audioPath": str(wav), "audioSha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                     "rating": 1.0}]
            with patch("speechocean_r_probe.Wav2VecEncoder", FixtureEncoder):
                extract_features(rows, root, root)
                extract_features(rows, root, root)
                with (root / "features.npy").open("r+b") as output:
                    output.seek(-1, 2)
                    output.write(b"X")
                with self.assertRaisesRegex(ValueError, "Feature cache bytes differ"):
                    extract_features(rows, root, root)
            rows[0]["audioSha256"] = "changed-source-hash"
            with self.assertRaisesRegex(ValueError, "Feature cache index changed"):
                extract_features(rows, root, root)


class FittingTests(unittest.TestCase):
    def test_predeclared_wavlm_recipe_matches_pinned_reference(self):
        recipe = load_wavlm_recipe()
        self.assertEqual(recipe["encoderKind"], "wavlm-base-plus")
        self.assertTrue(recipe["knownHoldout"])
        self.assertFalse(recipe["confirmatory"])

    def test_wavlm_features_use_distinct_encoder_and_cache_identity(self):
        class FixtureWavLM:
            identity = {"kind": "wavlm-base-plus", "width": 768,
                        "preprocessing": "fixture"}

            def __init__(self, *_args, **_kwargs):
                pass

            def __call__(self, _samples):
                return torch.full((3, 768), 2.0)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav = root / "one.wav"
            with wave.open(str(wav), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(np.zeros(16000, dtype="<i2").tobytes())
            rows = [{"id": "000000001", "split": "train", "speaker": "0001",
                     "audioPath": str(wav), "audioSha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                     "rating": 1.0}]
            with patch("speechocean_r_probe.WavLMEncoder", FixtureWavLM):
                features, _ = extract_features(rows, root, root, "wavlm-base-plus")
                self.assertAlmostEqual(float(features[0, 0]), 2.0)
                with self.assertRaisesRegex(ValueError, "Feature cache index changed"):
                    extract_features(rows, root, root, "wav2vec2-base")

    def test_ridge_learns_audio_signal_and_unseen_word_falls_back(self):
        x = np.arange(12, dtype=float).reshape(6, 2)
        y = np.asarray([0, 0.4, 0.8, 1.2, 1.6, 2])
        head = fit_ridge(x, y, 1.0)
        self.assertLess(metrics(predict_ridge(head, x), y)["mae"],
                        metrics(np.full(len(y), y.mean()), y)["mae"])
        rows = [{"text": "SAY RED", "targetWord": "RED"},
                {"text": "SAY RED", "targetWord": "RED"}]
        unseen = [{"text": "SAY BLUE", "targetWord": "BLUE"}]
        self.assertAlmostEqual(rating_baseline(rows, y[:2], unseen, 1, "targetWord")[0], 0.2)
        self.assertAlmostEqual(transcript_word_baseline(rows, y[:2], unseen, 1)[0], 0.2)

    def test_authority_is_research_only(self):
        self.assertTrue(AUTHORITY)
        self.assertTrue(all(value is False for value in AUTHORITY.values()))


if __name__ == "__main__":
    unittest.main()
