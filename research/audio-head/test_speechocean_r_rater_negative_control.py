import unittest
from collections import Counter

import numpy as np

from speechocean_r_rater_negative_control import (load_control_recipe,
                                                   permute_rating_blocks)


class SpeakerBlockPermutationTests(unittest.TestCase):
    def test_preserves_five_score_objects_fold_totals_and_clip_counts(self):
        rows = [
            {"id": "a-1", "speaker": "a"}, {"id": "a-2", "speaker": "a"},
            {"id": "b-1", "speaker": "b"}, {"id": "b-2", "speaker": "b"},
            {"id": "c-1", "speaker": "c"}, {"id": "d-1", "speaker": "d"},
            {"id": "e-1", "speaker": "e"}, {"id": "e-2", "speaker": "e"},
            {"id": "e-3", "speaker": "e"},
        ]
        original = np.asarray([[5, 0, 0], [0, 5, 0], [0, 0, 5], [2, 2, 1],
                               [1, 4, 0], [0, 1, 4], [4, 0, 1], [3, 1, 1], [1, 1, 3]])
        folds = {"a": 0, "b": 0, "c": 1, "d": 1, "e": 0}
        original_snapshot = original.copy()
        first, source, diagnostic = permute_rating_blocks(rows, original, folds, 20260923)
        second, source_again, second_diagnostic = permute_rating_blocks(
            rows, original, folds, 20260923)
        self.assertEqual(source, source_again)
        self.assertEqual(diagnostic, second_diagnostic)
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(original, original_snapshot)
        self.assertEqual(source[:4], [2, 3, 0, 1])
        self.assertEqual(source[6:], [6, 7, 8])
        self.assertEqual(sorted(source), list(range(len(rows))))
        self.assertEqual(diagnostic["clipSourceIdsMoved"], 6)
        self.assertEqual(diagnostic["clipSourceIdsUnchanged"], 3)
        for fold in {0, 1}:
            indices = [i for i, row in enumerate(rows) if folds[row["speaker"]] == fold]
            self.assertEqual(Counter(map(tuple, original[indices])),
                             Counter(map(tuple, first[indices])))
        for target, origin in enumerate(source):
            self.assertEqual(folds[rows[target]["speaker"]], folds[rows[origin]["speaker"]])

    def test_rejects_missing_speaker_and_malformed_rating_object(self):
        rows = [{"id": "a", "speaker": "s"}, {"id": "b", "speaker": "t"}]
        with self.assertRaisesRegex(ValueError, "Invalid speaker-block"):
            permute_rating_blocks(rows, np.asarray([[5, 0, 0], [0, 5, 0]]), {"s": 0}, 1)
        with self.assertRaisesRegex(ValueError, "Invalid speaker-block"):
            permute_rating_blocks(rows, np.asarray([[4, 0, 0], [0, 5, 0]]),
                                  {"s": 0, "t": 0}, 1)

    def test_recipe_pins_reference_train_only_result(self):
        control, cv_recipe, reference = load_control_recipe()
        self.assertEqual(control["permutationReplicates"], 1)
        self.assertEqual(cv_recipe["authorPartition"], "train")
        self.assertEqual(reference["outOfFoldClips"], 766)
        self.assertFalse(control["clinicalUseEligible"])


if __name__ == "__main__":
    unittest.main()
