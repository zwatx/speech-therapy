"""Numerical and leakage tests with synthetic labels only; no corpus inference."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import torch

from multiphone_controls import (
    HERE, canonical_sha, checked_checkpoint, choose_trial, fit_control,
    fit_count_control, fit_feature_design, group_key, predict_control,
    predict_count_control, run_evaluate, run_inner, run_refit, score_predictions,
    transform_features, validate_study,
)
from multiphone_data import build_splits


def example(phone="B", age="child", word="BALL", counts=(0, 0, 5), clip=0):
    return {"targetPhone": phone, "ageBand": age, "targetWord": word,
            "raterCounts": list(counts), "trainingEligible": True,
            "clipIndex": clip, "clipId": f"clip-{clip}", "age": 8 if age == "child" else 20}


def synthetic_study():
    clips, rows = [], []
    for index in range(10):
        age = 8 if index % 2 else 20
        clip = {"id": f"clip-{index}", "speakerId": f"speaker-{index}",
                "audioSha256": f"wave-{index}", "text": f"prompt-{index}",
                "age": age, "ageBand": "child" if age == 8 else "adult",
                "durationSeconds": 1 + index / 10, "rms": .02 + index / 100}
        clips.append(clip)
        for phone_id, phone in enumerate(("B", "P")):
            row = example(phone, clip["ageBand"], f"WORD-{index}",
                          (index % 3, 0, 5 - index % 3), index)
            row.update({"id": f"{clip['id']}:{phone}", "speakerId": clip["speakerId"],
                        "targetId": phone_id})
            rows.append(row)
    cohort = {"authorPartition": "train", "clips": clips, "rows": rows,
              "eligibleTargetIds": [0, 1], "targetPhones": ["B", "P"],
              "recipe": {"experiment": "synthetic-test", "splitSeed": 20260926,
                         "outerFolds": 5, "innerValidationSpeakerFraction": .2}}
    return cohort, build_splits(cohort)


class MultiphoneControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_prior_is_target_specific_and_smoothed(self):
        rows = [example("B", counts=(5, 0, 0)), example("P", counts=(0, 0, 5))]
        state = fit_count_control(rows, "prior")
        probabilities = predict_count_control(state, rows)
        np.testing.assert_allclose(probabilities, [[6/8, 1/8, 1/8], [1/8, 1/8, 6/8]])
        with self.assertRaisesRegex(ValueError, "no fit-side support"):
            predict_count_control(state, [example("ZH")])

    def test_backoff_uses_only_known_phone_age_and_word_groups(self):
        rows = [example(), example(age="adult", word="BACK", counts=(5, 0, 0)),
                example("P", counts=(0, 5, 0))]
        state = fit_count_control(rows, "word-age-backoff", 5)
        phone = np.asarray([6, 1, 6]) / 13
        child = (np.asarray([0, 0, 5]) + 5 * phone) / 10
        ball = (np.asarray([0, 0, 5]) + 5 * child) / 10
        held = [example(), example(word="UNSEEN"), example(age="unseen", word="UNSEEN")]
        np.testing.assert_allclose(predict_count_control(state, held), [ball, child, phone])
        self.assertNotIn(group_key("B", "child", "UNSEEN"), state["wordAgeCounts"])

    def test_unseen_word_does_not_expand_feature_vocabulary(self):
        fit_rows = [example(clip=0), example(word="BACK", clip=1)]
        design = fit_feature_design(fit_rows)
        frozen = deepcopy(design)
        held = [example(age="adult", word="UNSEEN", clip=2)]
        clips = [{"id": f"clip-{i}", "durationSeconds": i + 1, "rms": .1} for i in range(3)]
        features = transform_features(design, held, clips)
        self.assertEqual(design, frozen)
        self.assertFalse(any("UNSEEN" in name or "adult" in name for name in design["categoricalColumns"]))
        self.assertEqual(features[:, :len(design["categoricalColumns"])].sum(), 1)
        np.testing.assert_allclose(features[0, -2:], [np.log(3), np.log(.1)])
        clips[2]["durationSeconds"] = 0
        with self.assertRaisesRegex(ValueError, "Capture features"):
            transform_features(design, held, clips)

    def test_linear_scaling_is_fitted_before_validation_features(self):
        rows = [example(word="A", counts=(4, 0, 1), clip=0),
                example(word="B", counts=(0, 1, 4), clip=1)]
        clips = [{"id": f"clip-{i}", "durationSeconds": d, "rms": rms}
                 for i, (d, rms) in enumerate(((1, .1), (2, .2), (10000, .8)))]
        state, diagnostics = fit_control(rows, clips, "linear-word-age-capture", .01, 40)
        features = transform_features(state["design"], rows, clips)
        np.testing.assert_allclose(state["head"]["featureMean"], features.mean(0))
        frozen = canonical_sha(state)
        predicted = predict_control(state, [example(word="UNSEEN", clip=2)], clips)
        self.assertEqual(canonical_sha(state), frozen)
        np.testing.assert_allclose(predicted.sum(1), [1])
        self.assertTrue(np.isfinite(predicted).all())
        self.assertTrue(np.isfinite(diagnostics["finalObjective"]))

    def test_invalid_counts_and_unsupported_targets_fail(self):
        for count in ((-1, 1, 5), (0, 0, 4), (.5, .5, 4), (0, float("nan"), 5)):
            with self.assertRaisesRegex(ValueError, "five integral"):
                fit_count_control([example(counts=count)], "prior")
        row = example()
        row["trainingEligible"] = False
        with self.assertRaisesRegex(ValueError, "masked out"):
            fit_feature_design([row])

    def test_partition_binding_and_speaker_waveform_boundaries(self):
        cohort, splits = synthetic_study()
        validate_study(cohort, splits)
        changed = deepcopy(cohort)
        changed["rows"][0]["targetWord"] = "changed"
        with self.assertRaisesRegex(ValueError, "exact cohort"):
            validate_study(changed, splits)
        for field in ("speakerId", "audioSha256"):
            changed = deepcopy(cohort)
            fit = changed["rows"][splits["folds"][0]["outerFitRows"][0]]["clipIndex"]
            held = changed["rows"][splits["folds"][0]["outerHoldoutRows"][0]]["clipIndex"]
            changed["clips"][held][field] = changed["clips"][fit][field]
            if field == "speakerId":
                for row in changed["rows"]:
                    if row["clipIndex"] == held:
                        row["speakerId"] = changed["clips"][fit][field]
            rebound = deepcopy(splits)
            rebound["cohortCanonicalSha256"] = canonical_sha(changed)
            with self.assertRaisesRegex(ValueError, "crosses split boundary"):
                validate_study(changed, rebound)
        broken = deepcopy(splits)
        broken["folds"][0]["innerFitRows"].append(broken["folds"][0]["innerValidationRows"][0])
        with self.assertRaisesRegex(ValueError, "Row crosses"):
            validate_study(cohort, broken)

    def test_selection_uses_macro_phone_loss_and_proper_per_rater_brier(self):
        rows = [example(counts=(1, 1, 3)), example("P", counts=(0, 0, 5))]
        probabilities = np.asarray([[.2, .2, .6], [0, 0, 1]])
        metrics = score_predictions(probabilities, rows)
        self.assertAlmostEqual(metrics["perRaterBrier"], (1 - (.04 + .04 + .36)) / 2)
        trials = [{"setting": 1, "metrics": {"macroTargetLogLoss": .6, "perRaterLogLoss": .1}},
                  {"setting": 5, "metrics": {"macroTargetLogLoss": .5, "perRaterLogLoss": .3}}]
        self.assertEqual(choose_trial(trials)["setting"], 5)
        trials[0]["metrics"]["macroTargetLogLoss"] = .5
        self.assertEqual(choose_trial(trials)["setting"], 5)

    def test_inner_is_unchanged_by_outer_labels_and_phases_persist_frozen_states(self):
        cohort, splits = synthetic_study()
        with tempfile.TemporaryDirectory(dir=HERE / "outputs", prefix="test-controls-") as temporary:
            root = Path(temporary)
            cohort_path, split_path = root / "cohort.json", root / "splits.json"
            cohort_path.write_text(json.dumps(cohort))
            split_path.write_text(json.dumps(splits))
            args = SimpleNamespace(cohort=cohort_path, splits=split_path, fold=0, threads=1,
                                   max_iterations=10, families=["prior", "word-age-backoff"],
                                   output=root / "inner", input=None)
            original = run_inner(args)
            changed = deepcopy(cohort)
            for index in splits["folds"][0]["outerHoldoutRows"]:
                changed["rows"][index]["raterCounts"] = [5, 0, 0]
            rebound = deepcopy(splits)
            rebound["cohortCanonicalSha256"] = canonical_sha(changed)
            cohort_path.write_text(json.dumps(changed))
            split_path.write_text(json.dumps(rebound))
            args.output = root / "inner-changed-outer"
            rerun = run_inner(args)
            self.assertEqual(original["selected"], rerun["selected"])
            for family in original["trials"]:
                for a, b in zip(original["trials"][family], rerun["trials"][family], strict=True):
                    self.assertEqual(a["metrics"], b["metrics"])
                    self.assertEqual(a["stateSha256"], b["stateSha256"])
            # Restore original binding before refit; selection cannot silently migrate.
            args.input, args.output = root / "inner", root / "refit"
            with self.assertRaisesRegex(ValueError, "another cohort"):
                run_refit(args)
            cohort_path.write_text(json.dumps(cohort))
            split_path.write_text(json.dumps(splits))
            frozen = run_refit(args)
            self.assertFalse(frozen["outerOutcomesUsed"])
            self.assertTrue(all("metrics" not in entry for entry in frozen["states"].values()))
            args.input, args.output = root / "refit", root / "evaluated"
            report = run_evaluate(args)
            self.assertEqual(report["evaluationPartition"], "outerHoldoutRows")
            self.assertEqual(set(report["results"]), {"prior", "word-age-backoff"})
            checkpoint = frozen["states"]["prior"]
            (args.input / checkpoint["statePath"]).write_text("{}")
            with self.assertRaisesRegex(ValueError, "digest differs"):
                checked_checkpoint(args.input, checkpoint["statePath"], checkpoint["stateSha256"])


if __name__ == "__main__":
    unittest.main()
