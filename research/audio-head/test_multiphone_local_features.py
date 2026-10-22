"""Synthetic checks for estimated local features; no corpus model inference."""
import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from multiphone_local_features import (RECIPE, SCALAR_NAMES, canonical_mapping, convolution_frames,
                                       capture_digests, geometry_selection, local_features, pooled_window,
                                       require_unchanged, validate_log_prob, validate_manifest_rows)


def log_prob(labels):
    values = np.full((len(labels), 392), .2 / 391, dtype=np.float64)
    for frame, token in enumerate(labels):
        values[frame, token] = .8
    return np.log(values).astype(np.float32)


class LocalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.recipe = json.loads(RECIPE.read_text())

    def test_mapping_preserves_positions_and_marks_ambiguity(self):
        vocab = {token: index + 4 for index, token in enumerate(
            sorted(set(self.recipe["consonants"].values()) | set(self.recipe["vowels"].values()) |
                   set(self.recipe["stressOverrides"].values())))}
        tokens, ids, flags = canonical_mapping(["B", "AH0", "ER1", "AA1", "R", "T", "L"], vocab, self.recipe)
        self.assertEqual(tokens, ["b", "ə", "ɚ", "ɑː", "ɹ", "t", "l"])
        self.assertEqual(ids, [vocab[token] for token in tokens])
        self.assertIn("postvocalic-r-may-compete-with-merged-rhotic-tokens", flags)
        self.assertIn("er-stress-collapsed-to-rhotic-schwa", flags)
        with self.assertRaisesRegex(ValueError, "no declared"):
            canonical_mapping(["QQ"], vocab, self.recipe)

    def test_geometry_selection_does_not_read_ratings_or_model_support(self):
        clips = [{"id": str(i), "sampleCount": count} for i, count in enumerate([5000, 1000, 9000, 3000, 7000])]
        self.assertEqual(geometry_selection(clips, [0, 1, 2, 3, 4]), [1, 0, 2])
        self.assertEqual(convolution_frames(16000, self.recipe), 49)

    def test_target_rows_remain_included_with_short_or_low_support_intervals(self):
        values = log_prob([0, 4, 0, 5, 0])
        rows, diagnostics = local_features(values, [4, 5], [0, 1], self.recipe)
        self.assertEqual([row["intervalFrames"] for row in rows], [[1, 2], [3, 4]])
        self.assertEqual(len(rows), 2)
        self.assertTrue(diagnostics["greedyExactCanonicalSequence"])
        for row in rows:
            self.assertEqual(len(row["scalarFeatures"]), len(SCALAR_NAMES))
            self.assertTrue(np.isfinite(row["scalarFeatures"]).all())
            self.assertIn("fewer-than-two-target-state-frames", row["diagnosticFlags"])
        unrelated = log_prob([7, 7, 7, 7, 7])
        retained, _ = local_features(unrelated, [4, 5], [0, 1], self.recipe)
        self.assertEqual(len(retained), 2)
        self.assertTrue(all("target-is-not-argmax-on-most-occupied-frames" in row["diagnosticFlags"] for row in retained))

    def test_full_vocabulary_mass_and_repeated_phone_ctc_constraints(self):
        values = log_prob([4, 0, 4])
        rows, _ = local_features(values, [4, 4], [0, 1], self.recipe)
        self.assertEqual([row["intervalFrames"] for row in rows], [[0, 1], [2, 3]])
        self.assertAlmostEqual(rows[0]["scalarFeatures"][1], .8, places=6)
        with self.assertRaisesRegex(ValueError, "requires 3 frames"):
            local_features(values[:2], [4, 4], [0], self.recipe)
        invalid = values.copy(); invalid[:, 390] = 0
        with self.assertRaisesRegex(ValueError, "full-vocabulary"):
            validate_log_prob(invalid, 3)

    def test_pooling_uses_exact_shared_grid_and_clips_context_at_edges(self):
        frames = np.broadcast_to(np.arange(5, dtype=np.float32)[:, None], (5, 768)).copy()
        pooled, window = pooled_window(frames, [0, 1], 5, 2)
        self.assertEqual(window, [0, 3])
        np.testing.assert_array_equal(pooled, np.ones(768, dtype=np.float32))
        with self.assertRaisesRegex(ValueError, "frame grids differ"):
            pooled_window(frames, [0, 1], 6, 2)
        with self.assertRaisesRegex(ValueError, "pooling interval"):
            pooled_window(frames, [4, 6], 5, 2)

    def test_manifest_cannot_swap_target_rows_clips_or_canonical_positions(self):
        clips = [{"id": f"c{i}", "speakerId": f"s{i}", "audioPath": f"/audio/{i}",
                  "audioSha256": str(i), "sampleCount": 16000, "canonicalPhoneCount": 2} for i in range(2)]
        rows = [{"id": f"c{i}:B", "clipIndex": i, "clipId": f"c{i}", "targetId": 0,
                 "targetPhone": "B", "wordIndex": 0, "phoneIndex": 0, "trainingEligible": True} for i in range(2)]
        cohort = {"authorPartition": "train", "clips": clips, "rows": rows}
        manifest = {"authorPartition": "train", "clips": [{**clip, "clipIndex": i,
                    "canonicalPhones": ["B", "AA1"], "targetRows": [{"rowIndex": i, "rowId": rows[i]["id"],
                    "targetId": 0, "targetPhone": "B", "wordIndex": 0, "phoneIndex": 0, "canonicalIndex": 0}]}
                    for i, clip in enumerate(clips)]}
        validate_manifest_rows(manifest, cohort)
        changed = deepcopy(manifest)
        changed["clips"][0]["targetRows"], changed["clips"][1]["targetRows"] = (
            changed["clips"][1]["targetRows"], changed["clips"][0]["targetRows"])
        with self.assertRaisesRegex(ValueError, "target differs"):
            validate_manifest_rows(changed, cohort)
        for key, value in (("rowId", "wrong"), ("targetId", 1), ("phoneIndex", 1), ("wordIndex", 1)):
            changed = deepcopy(manifest); changed["clips"][0]["targetRows"][0][key] = value
            with self.assertRaisesRegex(ValueError, "target differs"):
                validate_manifest_rows(changed, cohort)
        changed = deepcopy(manifest); changed["clips"][0]["targetRows"][0]["canonicalIndex"] = 1
        with self.assertRaisesRegex(ValueError, "Canonical target"):
            validate_manifest_rows(changed, cohort)
        changed = deepcopy(manifest); changed["clips"][0]["audioSha256"] = "different"
        with self.assertRaisesRegex(ValueError, "clip differs"):
            validate_manifest_rows(changed, cohort)
        changed = deepcopy(manifest); changed["clips"][0]["targetRows"] = []
        with self.assertRaisesRegex(ValueError, "omits eligible"):
            validate_manifest_rows(changed, cohort)

    def test_mutated_inputs_are_rejected_before_report_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = {name: Path(temporary) / name for name in ("manifest", "recipe", "source", "index")}
            for path in paths.values():
                path.write_text("original")
            initial = capture_digests(paths)
            require_unchanged(paths, initial)
            for path in paths.values():
                path.write_text("changed")
                with self.assertRaisesRegex(ValueError, "changed during extraction"):
                    require_unchanged(paths, initial)
                path.write_text("original")


if __name__ == "__main__":
    unittest.main()
