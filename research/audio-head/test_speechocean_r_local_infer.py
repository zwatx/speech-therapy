"""Offline public-corpus replay and fail-closed inference tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from speechocean_r_local_infer import (
    AUDIO, HERE, infer, verified_head, verified_public_train_row,
)
from speechocean_r_rater_cv import predict_softmax
from speechocean_r_rater_final_fit import load_recipe


PUBLIC_TRAIN_WAV = (AUDIO / "WAVE/SPEAKER0001/000010011.WAV")


class LocalInferenceTests(unittest.TestCase):
    def test_real_public_author_train_replay_matches_saved_feature_for_both_encoders(self):
        recipe = load_recipe()
        for kind in ("wav2vec2-base", "wavlm-base-plus"):
            with self.subTest(kind=kind):
                result = infer(PUBLIC_TRAIN_WAV, kind)
                self.assertEqual(result["inputSource"], "pinned-public-author-train")
                self.assertEqual(result["runPurpose"], "artifact-replay-smoke-inference")
                self.assertNotIn("utteranceId", result)
                self.assertNotIn("audioSha256", result)
                self.assertFalse(result["calibrated"])
                self.assertFalse(result["learnerFeedbackEligible"])
                self.assertFalse(result["clinicalUseEligible"])
                directory = HERE / recipe["inputs"][kind]["directory"]
                index = json.loads((directory / "feature-index.json").read_text())
                position = next(i for i, row in enumerate(index["rows"])
                                if row["id"] == "000010011" and row["split"] == "train")
                feature = np.load(directory / "features.npy", allow_pickle=False)[position]
                expected = predict_softmax(verified_head(kind, recipe),
                                           feature.astype(np.float64)[None, :])[0]
                np.testing.assert_allclose(result["subjectiveCorpusRatingProbabilities"],
                                           expected, rtol=0, atol=1e-6)
                self.assertAlmostEqual(sum(result["subjectiveCorpusRatingProbabilities"]),
                                       1.0, places=12)

    def test_rejects_nonpublic_path_and_author_test_partition(self):
        recipe = load_recipe()
        with tempfile.TemporaryDirectory() as directory:
            unrelated = Path(directory) / "recording.wav"
            unrelated.write_bytes(PUBLIC_TRAIN_WAV.read_bytes())
            with self.assertRaisesRegex(ValueError, "Only local pinned public"):
                verified_public_train_row(unrelated, "wav2vec2-base", recipe)
        index_path = HERE / recipe["inputs"]["wav2vec2-base"]["directory"] / "feature-index.json"
        test_row = next(row for row in json.loads(index_path.read_text())["rows"]
                        if row["split"] == "test")
        with self.assertRaisesRegex(ValueError, "not one selected public author-training"):
            verified_public_train_row(Path(test_row["audioPath"]), "wav2vec2-base", recipe)

    def test_rejects_corrupt_final_artifact_and_feature_index(self):
        recipe = load_recipe()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ("report.json", "provenance.json", "heads.npz"):
                original = HERE / "outputs/speechocean-r-rater-final-fit-v1" / filename
                (root / filename).write_bytes(original.read_bytes())
            (root / "heads.npz").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "head or research provenance mismatch"):
                verified_head("wav2vec2-base", recipe, root)
            (root / "report.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "report or provenance SHA-256 mismatch"):
                verified_head("wav2vec2-base", recipe, root)
        with patch("speechocean_r_local_infer.sha256_file", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "feature index SHA-256 mismatch"):
                verified_public_train_row(PUBLIC_TRAIN_WAV, "wav2vec2-base", recipe)

    def test_rejects_unrecognized_encoder(self):
        with self.assertRaisesRegex(ValueError, "Unsupported frozen encoder"):
            verified_head("spectral-engineering-v1", load_recipe())


if __name__ == "__main__":
    unittest.main()
