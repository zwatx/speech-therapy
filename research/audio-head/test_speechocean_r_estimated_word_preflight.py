"""Focused geometry, split, and private-publication checks for the label-free preflight."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

import numpy as np

from speechocean_r_estimated_word_preflight import (HERE, equal_length_offword,
                                                    load_recipe, publish_private,
                                                    require_train_rows, word_state_span)


class EstimatedWordPreflightTests(unittest.TestCase):
    def test_recipe_is_locked_and_has_no_training_authority(self):
        recipe = load_recipe()
        self.assertEqual(recipe["sampleCount"], 40)
        self.assertTrue(recipe["noRatings"] and recipe["noFit"])
        self.assertFalse(recipe["trainingEligible"])

    def test_word_span_uses_distinct_ctc_states_for_repeated_phones(self):
        # Canonical phones [R, R, AA] need a blank between the repeated Rs.
        path = [0, 1, 1, 2, 3, 4, 5, 5, 6]
        self.assertEqual(word_state_span(path, [1, 2], 0), (1, 3))
        self.assertEqual(word_state_span(path, [1, 2], 1), (4, 8))
        with self.assertRaisesRegex(ValueError, "complete phone span"):
            word_state_span([0, 1, 2], [1, 1], 1)
        with self.assertRaisesRegex(ValueError, "monotone"):
            word_state_span([0, 3, 1], [1, 1], 1)

    def test_equal_length_offword_is_disjoint_or_missing(self):
        self.assertEqual(equal_length_offword(100, (60, 80), "0000000000000000"), (0, 20))
        self.assertEqual(equal_length_offword(100, (20, 40), "0000000000000000"), (80, 100))
        self.assertIsNone(equal_length_offword(100, (30, 70), "0000000000000000"))
        self.assertIsNone(equal_length_offword(20, (0, 20), "0000000000000000"))
        with self.assertRaisesRegex(ValueError, "geometry"):
            equal_length_offword(100, (40, 20), "0000000000000000")

    def test_train_membership_rejects_test_id_and_speaker_mismatch(self):
        rows = [{"sourceId": f"{number:09d}", "speakerId": "0001"} for number in range(40)]
        train = {row["sourceId"]: "0001" for row in rows}
        require_train_rows(rows, train)
        with self.assertRaisesRegex(ValueError, "non-train"):
            require_train_rows(rows[:-1] + [{"sourceId": "999999999", "speakerId": "0001"}], train)
        with self.assertRaisesRegex(ValueError, "mismatched speaker"):
            require_train_rows(rows[:-1] + [{"sourceId": rows[-1]["sourceId"], "speakerId": "0002"}], train)

    def test_private_artifact_has_no_placeholder_offword_vector(self):
        with tempfile.TemporaryDirectory(dir=HERE / "outputs") as temporary:
            output = Path(temporary) / "result"
            vectors = {"estimatedWord": np.ones((2, 768), dtype=np.float32),
                       "fullClip": np.ones((2, 768), dtype=np.float32),
                       "offWord": np.ones((1, 768), dtype=np.float32),
                       "offWordRowIndices": np.array([1], dtype=np.int32)}
            report = {"rows": [{"clipId": "0" * 16, "offWordAvailable": False},
                               {"clipId": "1" * 16, "offWordAvailable": True}]}
            publish_private(output, report, vectors)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertEqual({path.name for path in output.iterdir()}, {"vectors.npz", "report.json"})
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir()))
            with np.load(output / "vectors.npz", allow_pickle=False) as saved:
                self.assertEqual(saved["offWord"].shape, (1, 768))
                np.testing.assert_array_equal(saved["offWordRowIndices"], [1])
            self.assertNotIn("rating", json.dumps(json.loads((output / "report.json").read_text())).lower())
            with self.assertRaisesRegex(ValueError, "already exists"):
                publish_private(output, report, vectors)


if __name__ == "__main__":
    unittest.main()
