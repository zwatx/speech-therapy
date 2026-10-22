"""Control candidate replay and immutable refit/evaluation publication checks."""
import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

import multiphone_control_outer as outer
from test_multiphone_controls import synthetic_study
from test_multiphone_local_train import save


class ControlOuterTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        temporary = tempfile.TemporaryDirectory(dir=outer.HERE / "outputs", prefix="test-control-outer-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cohort, self.splits = synthetic_study()
        save(self.root / "cohort.json", self.cohort)
        save(self.root / "splits.json", self.splits)
        self.args = SimpleNamespace(cohort=self.root / "cohort.json", splits=self.root / "splits.json",
            fold=0, input=self.root / "inner", output=self.root / "refit", threads=2)
        inner = SimpleNamespace(**{**vars(self.args), "input": None, "output": self.args.input,
                                   "families": list(outer.controls.FAMILIES), "max_iterations": 30})
        with contextlib.redirect_stdout(io.StringIO()):
            outer.controls.run_inner(inner)

    def evaluate_args(self):
        return SimpleNamespace(**{**vars(self.args), "input": self.args.output, "output": self.root / "evaluation"})

    def test_three_refits_and_separate_predictions_have_verified_provenance(self):
        result = outer.run_refit(self.args)
        self.assertTrue(result["everyInnerCandidateReplayed"])
        self.assertFalse(result["holdoutPredictionsComputed"])
        config = outer.read_json(self.args.output / "config.json")
        self.assertEqual(config["fitRows"], self.splits["folds"][0]["outerFitRows"])
        self.assertFalse(list(self.args.output.glob("*predictions.json")))
        args = self.evaluate_args()
        evaluated = outer.run_evaluate(args)
        self.assertEqual(len(evaluated["predictionArtifactsSha256"]), 3)
        for path in evaluated["predictionArtifactsSha256"]:
            self.assertEqual(outer.read_json(Path(path))["rowIndices"], self.splits["folds"][0]["outerHoldoutRows"])

    def test_nonwinning_candidate_metrics_cannot_be_rewritten(self):
        path = self.args.input / "selection.json"
        selection = outer.read_json(path)
        selection["trials"]["word-age-backoff"][0]["metrics"]["macroTargetLogLoss"] += .3
        save(path, selection)
        with self.assertRaisesRegex(ValueError, "checkpoint replay differs"):
            outer.run_refit(self.args)
        self.assertFalse(self.args.output.exists())

    def test_rehashed_count_state_must_match_actual_fit_rows(self):
        path = self.args.input / "selection.json"
        selection = outer.read_json(path)
        trial = selection["trials"]["word-age-backoff"][0]
        state_path = self.args.input / trial["statePath"]
        state = outer.read_json(state_path)
        state["phonePriors"]["B"] = [.1, .2, .7]
        save(state_path, state)
        trial["stateSha256"] = outer.controls.digest(state_path)
        save(path, selection)
        with self.assertRaisesRegex(ValueError, "actual inner-fit rows"):
            outer.run_refit(self.args)

    def test_input_mutation_during_refit_prevents_verified_publication(self):
        original = outer.controls.run_refit

        def mutate(args):
            result = original(args)
            path = args.input / "selection.json"
            path.write_text(path.read_text() + " ")
            return result

        with patch.object(outer.controls, "run_refit", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "pinned artifact changed"):
                outer.run_refit(self.args)
        self.assertFalse((self.args.output / "verified.json").exists())

    def test_rehashed_nested_linear_setting_cannot_be_relabelled(self):
        path = self.args.input / "selection.json"
        selection = outer.read_json(path)
        trial = selection["trials"]["linear-word-age-capture"][0]
        state_path = self.args.input / trial["statePath"]
        state = outer.read_json(state_path)
        state["head"]["alpha"] = .99
        save(state_path, state)
        trial["stateSha256"] = outer.controls.digest(state_path)
        save(path, selection)
        with self.assertRaisesRegex(ValueError, "moments or setting differs"):
            outer.run_refit(self.args)
        self.assertFalse(self.args.output.exists())

    def test_frozen_mutation_during_evaluation_prevents_verified_publication(self):
        outer.run_refit(self.args)
        original = outer.controls.run_evaluate

        def mutate(args):
            result = original(args)
            path = args.input / "frozen.json"
            path.write_text(path.read_text() + " ")
            return result

        args = self.evaluate_args()
        with patch.object(outer.controls, "run_evaluate", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "pinned artifact changed"):
                outer.run_evaluate(args)
        self.assertFalse((args.output / "verified.json").exists())

    def test_existing_destination_refused_before_holdout_prediction(self):
        outer.run_refit(self.args)
        args = self.evaluate_args()
        args.output.mkdir()
        with patch.object(outer.controls, "predict_control", side_effect=AssertionError("predicted")):
            with self.assertRaises(FileExistsError):
                outer.run_evaluate(args)

    def test_mutated_saved_refit_state_is_not_blessed(self):
        original = outer.controls.run_refit

        def mutate(args):
            result = original(args)
            path = args.output / "prior.json"
            state = outer.read_json(path)
            state["phonePriors"]["B"] = [.1, .2, .7]
            save(path, state)
            return result

        with patch.object(outer.controls, "run_refit", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "digest differs"):
                outer.run_refit(self.args)
        self.assertFalse((self.args.output / "verified.json").exists())

    def test_mutated_saved_predictions_are_not_blessed(self):
        outer.run_refit(self.args)
        original = outer.controls.run_evaluate

        def mutate(args):
            result = original(args)
            path = args.output / "prior-predictions.json"
            value = outer.read_json(path)
            value["probabilities"] = [[.1, .2, .7]] * len(value["rowIndices"])
            save(path, value)
            return result

        args = self.evaluate_args()
        with patch.object(outer.controls, "run_evaluate", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "frozen checkpoint replay"):
                outer.run_evaluate(args)
        self.assertFalse((args.output / "verified.json").exists())


if __name__ == "__main__":
    unittest.main()
