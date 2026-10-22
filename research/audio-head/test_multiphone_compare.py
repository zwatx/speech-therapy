"""Synthetic comparison coverage, selection, age-slice, and support tests."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import torch

import multiphone_compare as compare
import multiphone_verify as verify
from multiphone_controls import run_inner as run_controls
from test_multiphone_controls import synthetic_study


def tiny_recipe():
    return {**verify.load_recipe(), "encoders": ["wav2vec2-base"], "heads": ["mean"],
            "folds": [0], "initializationSeeds": [7, 17, 29]}


def inventory(recipe):
    return [{**row, "status": "complete", "bestEpoch": 3,
             "selectionMacroTargetLogLoss": .4} for row in verify.matrix_runs(recipe)]


def rating_rows():
    return [{"id": f"row-{i}", "clipId": f"clip-{i}", "speakerId": f"speaker-{i // 2}",
             "targetPhone": phone, "raterCounts": counts, "age": age}
            for i, (phone, age, counts) in enumerate([
                ("B", 5, [1, 0, 4]), ("B", 6, [4, 0, 1]), ("B", 12, [1, 0, 4]),
                ("P", 13, [0, 2, 3]), ("P", 9, [0, 0, 5])])]


class MatrixSelectionTests(unittest.TestCase):
    def test_recipe_ties_choose_lower_lr_and_preserve_all_seeds(self):
        recipe = tiny_recipe()
        runs = inventory(recipe)
        for row in runs:
            # The higher LR reaches the same score earlier: lower LR is still first tie break.
            row["bestEpoch"] = 1 if row["lr"] == .001 else 9
        selected = compare.select_learning_rates(runs, recipe)
        self.assertEqual([row["seed"] for row in selected], recipe["initializationSeeds"])
        self.assertTrue(all(row["lr"] == .0003 and row["bestEpoch"] == 9 for row in selected))
        self.assertTrue(all(len(row["candidates"]) == 2 for row in selected))

    def test_exact_nll_rule_does_not_round_away_small_improvement(self):
        recipe = tiny_recipe()
        runs = inventory(recipe)
        for row in runs:
            row["selectionMacroTargetLogLoss"] = .4 - (1e-10 if row["lr"] == .001 else 0)
            row["childAUROC"] = 1 if row["lr"] == .0003 else 0
        self.assertTrue(all(row["lr"] == .001 for row in compare.select_learning_rates(runs, recipe)))

    def test_missing_invalid_duplicate_and_altered_trial_identity_refused(self):
        recipe = tiny_recipe()
        original = inventory(recipe)
        for status in ("incomplete", "invalid"):
            runs = deepcopy(original)
            runs[0]["status"] = status
            selected = compare.select_learning_rates(runs, recipe)
            self.assertEqual(selected[0]["status"], "unavailable")
            self.assertNotIn("name", selected[0])
            self.assertEqual(selected[1]["status"], "selected")
        for runs in (original[:-1], original + original[:1]):
            with self.assertRaisesRegex(ValueError, "exactly cover"):
                compare.select_learning_rates(runs, recipe)
        changed = deepcopy(original)
        changed[0]["lr"] = .1
        with self.assertRaisesRegex(ValueError, "identity/status"):
            compare.select_learning_rates(changed, recipe)

    def test_inventory_distinguishes_unverified_missing_and_tampered_artifacts(self):
        recipe = tiny_recipe()
        expected = list(verify.matrix_runs(recipe))
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pin = {**expected[0], "bestEpoch": 1, "selectionMacroTargetLogLoss": .4, "artifactsSha256": {}}
            directory = base / pin["name"]
            directory.mkdir()
            for filename in compare.ARTIFACT_NAMES:
                (directory / filename).write_text("synthetic")
                pin["artifactsSha256"][filename] = compare.digest(directory / filename)
            second = base / expected[1]["name"]
            second.mkdir()
            (second / "report.json").write_text("{}")
            result = compare.inventory_runs(recipe, base, {pin["name"]: pin})
            self.assertEqual(result[0]["status"], "complete")
            self.assertEqual(result[1]["status"], "incomplete")
            self.assertIn("verification", result[1]["reason"])
            self.assertIn("not published", result[2]["reason"])
            (directory / "predictions.json").write_text("changed")
            self.assertEqual(compare.inventory_runs(recipe, base, {pin["name"]: pin})[0]["status"], "invalid")
            (directory / "predictions.json").unlink()
            self.assertEqual(compare.inventory_runs(recipe, base, {pin["name"]: pin})[0]["status"], "invalid")


class SliceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.rows = rating_rows()
        self.p = np.asarray([[.1, .1, .8], [.7, .1, .2], [.1, .1, .8], [.1, .3, .6], [.01, .01, .98]])
        self.phones = ["B", "P", "ZH"]

    def test_children_use_exact_numeric_ages_six_through_twelve(self):
        np.testing.assert_array_equal(compare.slice_mask(self.rows, "ages6to12"), [False, True, True, False, True])
        result = compare.slice_diagnostics(self.p, self.rows, self.phones, "ages6to12")
        self.assertEqual(result["support"], {"positions": 3, "clips": 3, "speakers": 3,
                                           "raterWeights": [5, 0, 10], "presentPhones": ["B", "P"],
                                           "absentPhones": ["ZH"]})
        expected_loss = -(4 * np.log(.7) + np.log(.2) + np.log(.1) + 4 * np.log(.8) + 5 * np.log(.98)) / 15
        self.assertAlmostEqual(result["proper"]["perRaterLogLoss"], expected_loss)
        self.assertEqual(result["perPhone"]["B"]["support"]["positions"], 2)
        self.assertEqual(result["macroTarget"]["rating0"]["definedTargets"], 1)
        self.assertEqual(result["macroTarget"]["rating0"]["excludedPhones"], ["P"])
        self.assertIsNone(result["perPhone"]["P"]["rating0"]["auroc"])

    def test_empty_child_slice_is_explicitly_undefined(self):
        rows = deepcopy(self.rows)
        for row in rows:
            row["age"] = 20
        value = compare.slice_diagnostics(self.p, rows, self.phones, "ages6to12")
        self.assertEqual(value["support"]["positions"], 0)
        self.assertEqual(value["support"]["absentPhones"], self.phones)
        self.assertIsNone(value["proper"])
        self.assertIsNone(value["macroTarget"])
        self.assertIsNone(compare.comparison_delta(value, value)["proper"])

    def test_phone_prior_uses_identical_support_and_cannot_hide_undefined_targets(self):
        prior = np.asarray([[.3, .1, .6] if row["targetPhone"] == "B" else [.1, .1, .8] for row in self.rows])
        model = compare.slice_diagnostics(self.p, self.rows, self.phones, "ages6to12")
        baseline = compare.slice_diagnostics(prior, self.rows, self.phones, "ages6to12")
        self.assertEqual(baseline["macroTarget"]["rating0"]["auroc"], .5)
        delta = compare.comparison_delta(model, baseline)
        self.assertGreater(delta["macroTarget"]["rating0"]["auroc"], 0)
        self.assertIsNone(delta["perPhone"]["P"]["rating0"]["auroc"])
        changed = deepcopy(baseline)
        changed["support"]["speakers"] += 1
        with self.assertRaisesRegex(ValueError, "slice/support"):
            compare.comparison_delta(model, changed)
        changed = deepcopy(baseline)
        changed["perPhone"]["B"]["rating0"]["positiveRaterWeight"] += 1
        with self.assertRaisesRegex(ValueError, "event support"):
            compare.comparison_delta(model, changed)

    def test_overlapping_inner_partitions_are_counted_without_pooling_predictions(self):
        cohort = {"rows": self.rows}
        splits = {"folds": [{"fold": 0, "innerValidationRows": [0, 1, 2]},
                             {"fold": 1, "innerValidationRows": [1, 3, 4]}]}
        value = compare.partition_overlap(cohort, splits)
        self.assertEqual(value["allAges"]["distinctSpeakers"], 3)
        self.assertEqual(value["allAges"]["speakerMembershipsAcrossFolds"], 5)
        self.assertEqual(value["ages6to12"]["pairs"], [{"folds": [0, 1], "rows": 1, "clips": 1, "speakers": 1}])

    def test_seed_spread_is_same_fold_descriptive_and_keeps_missing_metrics(self):
        recipe = tiny_recipe()
        selections = compare.select_learning_rates(inventory(recipe), recipe)
        for index, row in enumerate(selections):
            p = self.p.copy()
            p[1] = [.7 - .1 * index, .1, .2 + .1 * index]
            row["slices"] = {age: compare.slice_diagnostics(p, self.rows, self.phones, age) for age in compare.SLICES}
            row["modelMinusControls"] = {"prior": {age: compare.comparison_delta(profile, profile)
                                                    for age, profile in row["slices"].items()}}
        spread = compare.seed_spread(selections, recipe)
        self.assertEqual(len(spread), 1)
        metrics = spread[0]["slices"]["ages6to12"]["metrics"]
        self.assertEqual(metrics["macroTargetLogLoss"]["definedSeeds"], 3)
        self.assertGreater(metrics["macroTargetLogLoss"]["maximum"], metrics["macroTargetLogLoss"]["minimum"])
        self.assertEqual(metrics["macroNLLModelMinusPrior"]["mean"], 0)
        self.assertIn("not independent", spread[0]["interpretation"])


class ControlReplayTests(unittest.TestCase):
    def test_selected_control_rules_replay_on_identical_age_slices_and_reject_changed_binding(self):
        torch.set_num_threads(1)
        cohort, splits = synthetic_study()
        with tempfile.TemporaryDirectory(dir=compare.HERE / "outputs", prefix="test-compare-") as temporary:
            base = Path(temporary)
            for name, value in (("cohort.json", cohort), ("splits.json", splits)):
                (base / name).write_text(json.dumps(value))
            args = SimpleNamespace(cohort=base / "cohort.json", splits=base / "splits.json", fold=0,
                                   threads=1, max_iterations=30, families=list(compare.CONTROL_FAMILIES),
                                   output=base / "controls/fold-0-inner")
            with contextlib.redirect_stdout(io.StringIO()):
                run_controls(args)
            recipe = {"cohortSha256": compare.digest(args.cohort), "splitsSha256": compare.digest(args.splits)}
            report = compare.controls_for_fold(base / "controls", 0, cohort, splits, recipe, base)
            self.assertEqual(set(report["families"]), set(compare.CONTROL_FAMILIES))
            child_support = [row["slices"]["ages6to12"]["support"] for row in report["families"].values()]
            self.assertTrue(all(value == child_support[0] for value in child_support))
            config_path = args.output / "config.json"
            config = json.loads(config_path.read_text())
            config["validationRows"] = config["fitRows"]
            config_path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "partitions/scope"):
                compare.controls_for_fold(base / "controls", 0, cohort, splits, recipe, base)


if __name__ == "__main__":
    unittest.main()
