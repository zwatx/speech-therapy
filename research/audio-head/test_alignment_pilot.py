"""Focused checks for the training-only constrained CTC pilot."""
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from alignment_pilot import (EXPECTED_FLAGS, RECIPE, canonical_to_head, interval_iou,
                             r_interval, run, validate_recipe, viterbi_ctc)
from encoders import WavLMEncoder


def collapse(tokens):
    result = []
    previous = None
    for token in tokens:
        if token != 0 and token != previous:
            result.append(token)
        previous = token
    return result


class AlignmentPilotTests(unittest.TestCase):
    def test_viterbi_matches_exhaustive_ctc_path_search(self):
        raw = np.array([[1, 7, 3], [5, 2, 4], [3, 8, 2],
                        [8, 4, 5], [2, 3, 9]], dtype=float)
        log_prob = np.log(raw / raw.sum(axis=1, keepdims=True))
        for target in ([1], [1, 2], [1, 1], [1, 2, 1]):
            path, score = viterbi_ctc(log_prob, target)
            self.assertEqual(len(path), len(log_prob))
            states = [0]
            for token in target:
                states.extend((token, 0))
            self.assertEqual(collapse([states[state] for state in path]), target)
            brute = max(sum(log_prob[t, token] for t, token in enumerate(tokens))
                        for tokens in itertools.product(range(3), repeat=len(log_prob))
                        if collapse(tokens) == target)
            self.assertTrue(math.isclose(score, brute, abs_tol=1e-12), (target, score, brute))

    def test_repeated_phone_requires_intervening_blank(self):
        log_prob = np.log(np.array([[.1, .9], [.9, .1], [.1, .9]]))
        path, score = viterbi_ctc(log_prob, [1, 1])
        self.assertEqual(path, [1, 2, 3])
        self.assertEqual(r_interval(path, 1), (2, 3))
        self.assertAlmostEqual(score, 3 * math.log(.9))
        with self.assertRaisesRegex(ValueError, "requires 3 frames"):
            viterbi_ctc(log_prob[:2], [1, 1])

    def test_mapping_strips_stress_and_rejects_missing_phone(self):
        vocabulary = ["<blank>", "aa", "r", "t"]
        self.assertEqual(canonical_to_head(["R", "AA1", "T"], vocabulary), [2, 1, 3])
        with self.assertRaisesRegex(ValueError, "absent"):
            canonical_to_head(["R", "ZH"], vocabulary)
        with self.assertRaisesRegex(ValueError, "Invalid"):
            canonical_to_head(["r"], vocabulary)

    def test_disjoint_intervals_have_zero_overlap(self):
        self.assertEqual(interval_iou((2, 4), (4, 6)), 0)
        self.assertAlmostEqual(interval_iou((2, 6), (4, 8)), 1 / 3)

    def test_recipe_locks_selection_and_diagnostic_cutoffs(self):
        recipe = json.loads(RECIPE.read_text())
        validate_recipe(recipe)
        changed = {**recipe, "selectionSeed": 1}
        with self.assertRaisesRegex(ValueError, "Unexpected pilot recipe"):
            validate_recipe(changed)
        for key in EXPECTED_FLAGS:
            changed = {**recipe, "flags": {**recipe["flags"], key: -1}}
            with self.assertRaisesRegex(ValueError, "Unexpected pilot recipe"):
                validate_recipe(changed)

    def test_run_rejects_mismatched_archive_before_audio(self):
        metadata = [{"vocabulary": ["<blank>", "r"], "encoder": WavLMEncoder.identity,
                     "headInitializationSeed": seed, "steps": 800}
                    for seed in (7, 17, 29)]
        with tempfile.TemporaryDirectory() as temporary:
            with patch("alignment_pilot.load_head", side_effect=[(object(), row) for row in metadata]), \
                 patch("alignment_pilot.sha256_file", return_value="altered"), \
                 patch("alignment_pilot.select_train_rows") as select_rows:
                with self.assertRaisesRegex(ValueError, "archive SHA-256 mismatch"):
                    run(Path(temporary) / "report.json")
                select_rows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
