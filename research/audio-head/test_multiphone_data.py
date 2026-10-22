"""Small synthetic metadata tests; no corpus download, audio inference, or training."""
from copy import deepcopy
import unittest

from multiphone_data import TARGETS, build_splits, derive_examples, target_summary


def annotation(phones, annotations, word="BALL"):
    decoded = []
    for text in annotations:
        tokens = [token for token in text.split() if not token.startswith("[")]
        decoded.append([0 if token.startswith("(") else 1 if token.startswith("{") else 2
                        for token in tokens])
    aggregate = {"text": word, "words": [{"text": word, "phones": phones,
                                          "phones-accuracy": [sum(row[i] for row in decoded) / 5
                                                              for i in range(len(phones))]}]}
    detailed = {"text": word, "words": [{"text": word, "ref-phones": " ".join(phones),
                                         "phones": annotations}]}
    return aggregate, detailed


def small_cohort():
    clips, rows = [], []
    for index in range(10):
        clip = {"id": f"clip-{index}", "speakerId": f"speaker-{index}",
                "audioSha256": f"hash-{index}", "text": f"prompt-{index}"}
        clips.append(clip)
        for target in (0, 1, 23):
            rows.append({"id": f"{clip['id']}:{target}", "clipId": clip["id"],
                         "clipIndex": index, "speakerId": clip["speakerId"], "targetId": target,
                         "targetWord": "SHARED", "raterCounts": [1, 1, 3],
                         "trainingEligible": target != 23})
    return {"authorPartition": "train", "clips": clips, "rows": rows,
            "eligibleTargetIds": [0, 1],
            "recipe": {"experiment": "synthetic-test", "splitSeed": 20260926, "outerFolds": 5,
                       "innerValidationSpeakerFraction": .2}}


class MultiphoneDataTests(unittest.TestCase):
    def test_recovers_five_raters_and_ignores_insertion_tokens(self):
        a, d = annotation(["B", "AO1", "L"], ["B AO1 L", "{B} AO1 L", "(B) AO1 L",
                                                "B [R] AO1 L", "B AO1 L"])
        rows = derive_examples("clip", "speaker", 7, a, d)
        b = next(row for row in rows if row["targetPhone"] == "B")
        self.assertEqual(b["raterCounts"], [1, 1, 3])
        self.assertEqual((b["wordIndex"], b["phoneIndex"]), (0, 0))
        self.assertEqual([row["targetPhone"] for row in rows], ["B", "L"])

    def test_repeated_target_is_excluded_without_discarding_other_targets(self):
        a, d = annotation(["B", "B", "L"], ["B B L"] * 5)
        rows = derive_examples("clip", "speaker", 20, a, d)
        self.assertEqual([row["targetPhone"] for row in rows], ["L"])
        self.assertEqual(rows[0]["phoneIndex"], 2)

    def test_malformed_or_mismatched_labels_fail(self):
        a, d = annotation(["B"], ["B"] * 5)
        bad = deepcopy(a)
        bad["words"][0]["phones-accuracy"] = [0]
        with self.assertRaisesRegex(ValueError, "aggregate differs"):
            derive_examples("clip", "speaker", 7, bad, d)
        bad = deepcopy(d)
        bad["words"][0]["phones"][0] = "R"
        with self.assertRaisesRegex(ValueError, "Rater sequence"):
            derive_examples("clip", "speaker", 7, a, bad)
        bad["words"][0]["phones"][0] = "B?"
        with self.assertRaisesRegex(ValueError, "Malformed"):
            derive_examples("clip", "speaker", 7, a, bad)
        with self.assertRaisesRegex(ValueError, "age bands"):
            derive_examples("clip", "speaker", 16, a, d)

    def test_support_rule_requires_both_rows_and_speakers(self):
        rows = [{"targetId": 0, "speakerId": str(i % 49), "targetWord": "BALL",
                 "raterCounts": [0, 0, 5], "age": 7} for i in range(100)]
        recipe = {"minimumTargetRows": 100, "minimumTargetSpeakers": 50}
        self.assertFalse(target_summary(rows, recipe)[0]["trainingEligible"])
        rows[-1]["speakerId"] = "new-speaker"
        self.assertTrue(target_summary(rows, recipe)[0]["trainingEligible"])
        self.assertFalse(target_summary(rows[:-1], recipe)[0]["trainingEligible"])

    def test_splits_keep_all_targets_of_a_clip_and_speaker_together(self):
        cohort = small_cohort()
        result = build_splits(cohort)
        self.assertEqual(result, build_splits(cohort))
        held = []
        for fold in result["folds"]:
            self.assertFalse(set(fold["outerFitSpeakers"]) & set(fold["outerHoldoutSpeakers"]))
            self.assertFalse(set(fold["innerFitSpeakers"]) & set(fold["innerValidationSpeakers"]))
            self.assertEqual(set(fold["innerFitClips"]) | set(fold["innerValidationClips"]),
                             set(fold["outerFitClips"]))
            for key in ("outerFit", "outerHoldout", "innerFit", "innerValidation"):
                self.assertEqual(len(fold[key + "Rows"]), 2 * len(fold[key + "Clips"]))
                self.assertTrue(all(cohort["rows"][i]["targetId"] != 23 for i in fold[key + "Rows"]))
            held += fold["outerHoldoutRows"]
            self.assertEqual(fold["lexicalOverlap"]["outer"]["targetWordTypes"], 1)
        self.assertEqual(sorted(held), [i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]])

    def test_split_rejects_wrong_speaker_duplicate_rows_and_waveform_leakage(self):
        cohort = small_cohort()
        cohort["rows"][0]["speakerId"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Row identity"):
            build_splits(cohort)
        cohort = small_cohort()
        cohort["rows"].append(cohort["rows"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate clip"):
            build_splits(cohort)
        cohort = small_cohort()
        for clip in cohort["clips"]:
            clip["audioSha256"] = "duplicate"
        with self.assertRaisesRegex(ValueError, "Duplicate WAV"):
            build_splits(cohort)


if __name__ == "__main__":
    unittest.main()
