"""Synthetic selection, refit/evaluation separation and leakage checks."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_local_outer as outer
import multiphone_local_train as inner
from test_multiphone_local_train import fixture, save


class LocalOuterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=inner.HERE / "outputs", prefix="test-local-outer-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.study = fixture(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            inner.run_inner(self.study)
        self.args = SimpleNamespace(cohort=self.study.cohort, splits=self.study.splits,
                                    features=self.study.features, fold=0,
                                    input=self.study.output, output=self.root / "frozen")

    def refit(self):
        return outer.run_refit(self.args)

    def evaluation_args(self):
        return SimpleNamespace(**{**vars(self.args), "input": self.args.output, "output": self.root / "evaluation"})

    def test_refit_never_scores_holdout_and_uses_exact_outer_fit_moments(self):
        with patch.object(outer, "score_predictions", side_effect=AssertionError("No held-out scoring in refit")):
            result = self.refit()
        self.assertFalse(result["holdoutPredictionsComputed"])
        self.assertFalse((self.args.output / "predictions.json").exists())
        cohort, splits, scalars, positions, _ = inner.load_inputs(self.args.cohort, self.args.splits, self.args.features)
        indices = splits["folds"][0]["outerFitRows"]
        matrix = inner.transform(inner.design_for(cohort), [cohort["rows"][i] for i in indices],
                                 np.asarray(scalars[[positions[i] for i in indices]]))
        saved = inner.read_json(self.args.output / "checkpoint.json")["state"]
        np.testing.assert_array_equal(saved["head"]["featureMean"], matrix.mean(0))
        selection = inner.read_json(self.study.output / "selection.json")["selected"]
        self.assertEqual(inner.read_json(self.args.output / "config.json")["alpha"], selection["alpha"])

    def test_evaluation_uses_only_outer_rows_and_does_not_change_predictor(self):
        self.refit()
        checkpoint = self.args.output / "checkpoint.json"
        before = inner.digest(checkpoint)
        report = outer.run_evaluate(self.evaluation_args())
        split = inner.read_json(self.args.splits)["folds"][0]
        self.assertEqual(report["evaluationRows"], split["outerHoldoutRows"])
        self.assertTrue(set(report["evaluationRows"]).isdisjoint(split["outerFitRows"]))
        self.assertEqual(before, inner.digest(checkpoint))
        predictions = inner.read_json(self.root / "evaluation/predictions.json")
        cohort, _, scalars, positions, _ = inner.load_inputs(self.args.cohort, self.args.splits, self.args.features)
        rows = [cohort["rows"][i] for i in predictions["rowIndices"]]
        replay = inner.predict_state(inner.read_json(checkpoint)["state"], rows,
                                     np.asarray(scalars[[positions[i] for i in predictions["rowIndices"]]]))
        np.testing.assert_array_equal(replay, predictions["probabilities"])
        self.assertEqual(report["evaluation"], outer.score_predictions(replay, rows))

    def test_changed_outer_labels_cannot_change_selection_or_fitted_state(self):
        self.refit()
        before = inner.read_json(self.args.output / "checkpoint.json")["state"]
        cohort = inner.read_json(self.args.cohort)
        for index in inner.read_json(self.args.splits)["folds"][0]["outerHoldoutRows"]:
            cohort["rows"][index]["raterCounts"] = [5, 0, 0]
        changed = fixture(self.root / "changed-outer-labels", cohort)
        with contextlib.redirect_stdout(io.StringIO()):
            inner.run_inner(changed)
        args = SimpleNamespace(**{**vars(changed), "input": changed.output, "output": self.root / "changed-frozen"})
        outer.run_refit(args)
        after = inner.read_json(args.output / "checkpoint.json")["state"]
        self.assertEqual(before, after)

    def test_wrong_inner_fold_selection_and_score_tampering_refused(self):
        original = inner.read_json(self.study.output / "selection.json")
        path = self.study.output / "selection.json"
        wrong = deepcopy(original)
        wrong["selected"] = next(row for row in wrong["trials"] if row != wrong["selected"])
        save(path, wrong)
        with self.assertRaisesRegex(ValueError, "Selected setting"):
            self.refit()
        wrong = deepcopy(original)
        wrong["trials"][0]["metrics"]["macroTargetLogLoss"] += .01
        save(path, wrong)
        with self.assertRaisesRegex(ValueError, "selection score"):
            self.refit()
        save(path, original)
        self.args.fold = 1
        with self.assertRaisesRegex(ValueError, "selection binding"):
            self.refit()

    def test_frozen_state_and_source_tampering_refused(self):
        self.refit()
        args = self.evaluation_args()
        checkpoint = self.args.output / "checkpoint.json"
        original = checkpoint.read_bytes()
        checkpoint.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "digest"):
            outer.run_evaluate(args)
        checkpoint.write_bytes(original)
        with patch.object(outer, "source_hashes", return_value={"changed": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "refit binding"):
                outer.run_evaluate(args)

    def test_rehashed_probabilities_cannot_select_a_different_checkpoint(self):
        selection_path = self.study.output / "selection.json"
        selection = inner.read_json(selection_path)
        trial = selection["trials"][0]
        predictions_path = self.study.output / trial["predictionsPath"]
        predictions = inner.read_json(predictions_path)
        cohort = inner.read_json(self.args.cohort)
        rows = [cohort["rows"][i] for i in predictions["rowIndices"]]
        changed = np.asarray([row["raterCounts"] for row in rows], dtype=float) / 5
        predictions["probabilities"] = changed.tolist()
        save(predictions_path, predictions)
        trial["predictionsSha256"] = inner.digest(predictions_path)
        trial["metrics"] = inner.score_predictions(changed, rows)
        selection["selected"] = inner.choose_trial(selection["trials"])
        save(selection_path, selection)
        with self.assertRaisesRegex(ValueError, "exactly replay"):
            self.refit()

    def test_existing_destination_rejected_before_holdout_prediction(self):
        self.refit()
        args = self.evaluation_args()
        args.output.mkdir()
        with patch.object(inner, "predict_state", side_effect=AssertionError("Holdout must remain unopened")):
            with self.assertRaisesRegex(ValueError, "fresh directory"):
                outer.run_evaluate(args)

    def test_input_mutation_during_refit_cannot_publish_frozen_completion(self):
        original_fit = inner.fit_state
        def changed(*args, **kwargs):
            result = original_fit(*args, **kwargs)
            path = self.study.output / "selection.json"
            path.write_text(path.read_text() + " ")
            return result
        with patch.object(inner, "fit_state", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.refit()
        self.assertFalse((self.args.output / "frozen.json").exists())


if __name__ == "__main__":
    unittest.main()
