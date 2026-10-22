"""Synthetic leakage, provenance, numerical, and replay checks; no speech inference."""
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

from multiphone_data import build_splits
from multiphone_controls import run_inner as run_controls
from multiphone_local_train import (
    HERE, SCALAR_NAMES, TRAINING_RECIPE, canonical_sha, choose_trial, design_for,
    control_comparisons, digest, fit_state, load_inputs, predict_state, replay_checkpoint, run_inner, transform,
)
from test_multiphone_controls import synthetic_study


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True))


def fixture(directory, cohort=None):
    """Create a complete small study and its independently hash-bound feature artifact."""
    directory.mkdir(exist_ok=True)
    if cohort is None:
        cohort, _ = synthetic_study()
        for row in cohort["rows"]:
            row.update(wordIndex=0, phoneIndex=row["targetId"])
    splits = build_splits(cohort)
    cohort_path, splits_path = directory / "cohort.json", directory / "splits.json"
    save(cohort_path, cohort)
    save(splits_path, splits)
    rows = cohort["rows"]
    scalars = np.arange(len(rows) * len(SCALAR_NAMES), dtype=np.float32).reshape(len(rows), -1) / 100
    # A constant column tests the zero-SD fallback without invalid feature values.
    scalars[:, 4] = 1
    np.save(directory / "scalars.npy", scalars, allow_pickle=False)
    feature_rows = [{"rowIndex": i, "rowId": row["id"], "clipId": row["clipId"],
                     "targetId": row["targetId"], "targetPhone": row["targetPhone"],
                     "wordIndex": row["wordIndex"], "phoneIndex": row["phoneIndex"],
                     "canonicalIndex": row["targetId"], "scalarFeatures": scalars[i].tolist()}
                    for i, row in enumerate(rows)]
    manifest = {"authorPartition": "train", "fullCohortCoverage": True,
                "partition": "allEligibleAuthorTrain", "cohortSha256": digest(cohort_path),
                "splitsSha256": digest(splits_path),
                "clips": [{"id": clip["id"], "targetRows": [
                    {key: value for key, value in row.items() if key not in ("clipId", "scalarFeatures")}
                    for row in feature_rows if row["clipId"] == clip["id"]]}
                    for clip in cohort["clips"]]}
    save(directory / "manifest.json", manifest)
    save(directory / "recipe.json", {"mappingVersion": "arpabet-espeak-provisional-v1"})
    (directory / "ctc").mkdir()
    save(directory / "ctc/config.json", {"manifestSha256": digest(directory / "manifest.json")})
    save(directory / "ctc/index.json", {"complete": True, "configSha256": digest(directory / "ctc/config.json")})
    metadata = {"complete": True, "fullCohortCoverage": True, "eligibleCohortRows": len(rows),
                "failedRows": [], "unmappableRows": [], "rowIndices": list(range(len(rows))),
                "cohortSha256": digest(cohort_path), "splitsSha256": digest(splits_path),
                "scalarFeatureNames": SCALAR_NAMES, "mappingVersion": "arpabet-espeak-provisional-v1",
                "sourceSha256": {name: digest(HERE / name) for name in
                                 ("multiphone_local_features.py", "alignment_pilot.py")},
                "scalarFeatures": {"path": "scalars.npy", "sha256": digest(directory / "scalars.npy"),
                                   "shape": list(scalars.shape), "dtype": "float32"},
                "rows": feature_rows, "wavlmIndexSha256": None}
    for flag in ("frameTimesValidated", "producedPhoneLabelsAvailable", "authorTestInferencePerformed",
                 "clinicalUseEligible", "learnerFeedbackEligible"):
        metadata[flag] = False
    for name, filename in (("manifest", "manifest.json"), ("ctcIndex", "ctc/index.json"), ("recipe", "recipe.json")):
        metadata[name + "Path"] = str(directory / filename)
        metadata[name + "Sha256"] = digest(directory / filename)
    save(directory / "features.json", metadata)
    return SimpleNamespace(cohort=cohort_path, splits=splits_path, features=directory / "features.json",
                           output=directory / "run", controls=None, fold=0)


class LocalTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=HERE / "outputs", prefix="test-local-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.args = fixture(self.root)

    def load(self):
        return load_inputs(self.args.cohort, self.args.splits, self.args.features)

    def metadata(self):
        return json.loads(self.args.features.read_text())

    def test_complete_row_identity_and_values_are_bound(self):
        cohort, _, values, positions, evidence = self.load()
        self.assertEqual(list(positions), list(range(len(cohort["rows"]))))
        self.assertEqual(values.dtype, np.float32)
        self.assertEqual(evidence["featuresSha256"], digest(self.args.features))
        metadata = self.metadata()
        # Keep coverage intact while assigning another target's scalar row.
        metadata["rows"][0], metadata["rows"][1] = metadata["rows"][1], metadata["rows"][0]
        save(self.args.features, metadata)
        with self.assertRaisesRegex(ValueError, "different target"):
            self.load()

    def test_partial_missing_duplicate_and_unreviewed_scope_refused(self):
        original = self.metadata()
        changes = (("fullCohortCoverage", False), ("failedRows", [1]),
                   ("rowIndices", original["rowIndices"][:-1]),
                   ("rowIndices", [0] + original["rowIndices"][:-1]),
                   ("authorTestInferencePerformed", True))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                metadata = deepcopy(original)
                metadata[key] = value
                save(self.args.features, metadata)
                with self.assertRaises(ValueError):
                    self.load()

    def test_scalar_column_name_and_named_row_values_checked(self):
        original = self.metadata()
        metadata = deepcopy(original)
        metadata["scalarFeatureNames"][9] = "estimatedDurationSeconds"
        save(self.args.features, metadata)
        with self.assertRaisesRegex(ValueError, "schema"):
            self.load()
        metadata = deepcopy(original)
        metadata["rows"][0]["scalarFeatures"][0] += 1
        save(self.args.features, metadata)
        with self.assertRaisesRegex(ValueError, "values differ"):
            self.load()

    def test_changed_scalar_file_source_and_upstream_hash_refused(self):
        original = self.metadata()
        metadata = deepcopy(original)
        metadata["sourceSha256"]["alignment_pilot.py"] = "0" * 64
        save(self.args.features, metadata)
        with self.assertRaisesRegex(ValueError, "Extraction source"):
            self.load()
        metadata = deepcopy(original)
        metadata["manifestSha256"] = "0" * 64
        save(self.args.features, metadata)
        with self.assertRaisesRegex(ValueError, "manifest input digest"):
            self.load()
        save(self.args.features, original)
        with (self.root / "scalars.npy").open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "path/digest"):
            self.load()

    def test_self_consistently_rehashed_nonfinite_matrix_refused(self):
        matrix = np.load(self.root / "scalars.npy")
        matrix[0, 0] = np.nan
        np.save(self.root / "scalars.npy", matrix, allow_pickle=False)
        metadata = self.metadata()
        metadata["scalarFeatures"]["sha256"] = digest(self.root / "scalars.npy")
        metadata["rows"][0]["scalarFeatures"][0] = float("nan")
        save(self.args.features, metadata)
        with self.assertRaisesRegex(ValueError, "Invalid scalar matrix"):
            self.load()

    def test_phone_conditioned_design_has_no_word_or_age_features(self):
        cohort, _, values, _, _ = self.load()
        design = design_for(cohort)
        matrix = transform(design, cohort["rows"][:2], values[:2])
        self.assertEqual(matrix.shape, (2, 28))
        np.testing.assert_array_equal(matrix[:, :2], np.eye(2))
        np.testing.assert_array_equal(matrix[0, 2:15], values[0])
        np.testing.assert_array_equal(matrix[1, 15:], values[1])
        self.assertEqual(matrix[0, 15:].sum(), 0)
        self.assertEqual(matrix[1, 2:15].sum(), 0)
        changed = deepcopy(cohort["rows"][:2])
        for row in changed:
            row.update(age=99, targetWord="UNSEEN", raterCounts=[5, 0, 0])
        np.testing.assert_array_equal(transform(design, changed, values[:2]), matrix)
        design["columns"][0], design["columns"][1] = design["columns"][1], design["columns"][0]
        with self.assertRaisesRegex(ValueError, "column identity/order"):
            transform(design, changed, values[:2])

    def test_scaling_and_coefficients_use_only_fit_rows(self):
        cohort, splits, values, _, _ = self.load()
        ids = splits["folds"][0]["innerFitRows"]
        rows = [cohort["rows"][i] for i in ids]
        design = design_for(cohort)
        state, diagnostics = fit_state(design, rows, values[ids], .01)
        matrix = transform(design, rows, values[ids])
        np.testing.assert_array_equal(state["head"]["featureMean"], matrix.mean(0))
        np.testing.assert_array_equal(state["head"]["featureScale"], np.where(matrix.std(0) < 1e-6, 1, matrix.std(0)))
        frozen = canonical_sha(state)
        extreme = np.full((2, 13), 1e4)
        p = predict_state(state, cohort["rows"][:2], extreme)
        self.assertEqual(frozen, canonical_sha(state))
        self.assertTrue(np.isfinite(p).all())
        np.testing.assert_allclose(p.sum(1), 1)
        self.assertTrue(np.isfinite(diagnostics["finalObjective"]))

    def test_invalid_counts_missing_phone_and_saved_scale_refused(self):
        cohort, _, values, _, _ = self.load()
        rows, design = deepcopy(cohort["rows"][:2]), design_for(cohort)
        rows[0]["raterCounts"] = [0, 0, 4]
        with self.assertRaisesRegex(ValueError, "five integral"):
            fit_state(design, rows, values[:2], .01)
        with self.assertRaisesRegex(ValueError, "lacks inner-fit"):
            fit_state(design, rows[:1], values[:1], .01)
        state, _ = fit_state(design, cohort["rows"], values, .01)
        state["head"]["featureScale"][0] = 0
        with self.assertRaisesRegex(ValueError, "saved softmax"):
            predict_state(state, cohort["rows"], values)

    def test_selection_uses_macro_nll_then_stronger_l2(self):
        trials = [{"alpha": alpha, "metrics": {"macroTargetLogLoss": value, "perRaterLogLoss": micro}}
                  for alpha, value, micro in zip(TRAINING_RECIPE["l2Candidates"], [.8, .6, .6, .7], [.1, .4, .5, .2])]
        self.assertEqual(choose_trial(trials)["alpha"], .01)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            choose_trial(trials[:-1])

    def test_all_trials_saved_and_checkpoint_replays_exactly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report = run_inner(self.args)
        self.assertEqual(len(report["trials"]), 4)
        self.assertFalse(report["outerOutcomesUsed"])
        for trial in report["trials"]:
            checkpoint = self.args.output / trial["checkpointPath"]
            replay = replay_checkpoint(checkpoint, self.args.cohort, self.args.splits, self.args.features)
            self.assertEqual(replay, json.loads((self.args.output / trial["predictionsPath"]).read_text()))
            self.assertTrue(trial["checkpointReplayExact"])
        checkpoint = self.args.output / report["selected"]["checkpointPath"]
        state = json.loads(checkpoint.read_text())
        state["state"]["head"]["weights"][0][0] += 1
        save(checkpoint, state)
        with self.assertRaisesRegex(ValueError, "Checkpoint digest"):
            replay_checkpoint(checkpoint, self.args.cohort, self.args.splits, self.args.features)

    def test_outer_labels_cannot_change_any_inner_fit_or_score(self):
        with contextlib.redirect_stdout(io.StringIO()):
            original = run_inner(self.args)
        cohort = json.loads(self.args.cohort.read_text())
        splits = json.loads(self.args.splits.read_text())
        for index in splits["folds"][0]["outerHoldoutRows"]:
            cohort["rows"][index]["raterCounts"] = [5, 0, 0]
        changed = fixture(self.root / "changed-outer", cohort)
        with contextlib.redirect_stdout(io.StringIO()):
            rerun = run_inner(changed)
        self.assertEqual(original["selected"]["alpha"], rerun["selected"]["alpha"])
        for before, after in zip(original["trials"], rerun["trials"], strict=True):
            self.assertEqual(before["metrics"], after["metrics"])
            a = json.loads((self.args.output / before["checkpointPath"]).read_text())["state"]
            b = json.loads((changed.output / after["checkpointPath"]).read_text())["state"]
            self.assertEqual(a, b)

    def test_controls_replay_only_identical_inner_rows_and_source(self):
        control_args = SimpleNamespace(cohort=self.args.cohort, splits=self.args.splits, fold=0,
                                       threads=1, max_iterations=30,
                                       families=["prior", "word-age-backoff", "linear-word-age-capture"],
                                       output=self.root / "controls/fold-0-inner")
        with contextlib.redirect_stdout(io.StringIO()):
            run_controls(control_args)
        cohort, splits, _, _, evidence = self.load()
        result = control_comparisons(self.root / "controls", 0, cohort, splits, evidence)
        self.assertEqual(set(result["families"]), set(control_args.families))
        self.assertTrue(result["sameValidationRows"])
        # Rehash the config in selection too: independent split/source checks must reject.
        config_path, selection_path = control_args.output / "config.json", control_args.output / "selection.json"
        original_config = json.loads(config_path.read_text())
        original_selection = json.loads(selection_path.read_text())
        for kind in ("rows", "source"):
            config, selection = deepcopy(original_config), deepcopy(original_selection)
            if kind == "rows":
                config["validationRows"] = config["fitRows"]
            else:
                config["sourceSha256"]["multiphone_controls.py"] = "0" * 64
            save(config_path, config)
            selection["configSha256"] = digest(config_path)
            save(selection_path, selection)
            with self.assertRaises(ValueError):
                control_comparisons(self.root / "controls", 0, cohort, splits, evidence)

    def test_mutation_during_fit_prevents_complete_report(self):
        original = fit_state

        def mutate(*args, **kwargs):
            state = original(*args, **kwargs)
            metadata = self.metadata()
            metadata["newFieldAfterStart"] = True
            save(self.args.features, metadata)
            return state

        with patch("multiphone_local_train.fit_state", side_effect=mutate), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Input/source changed"):
                run_inner(self.args)
        self.assertFalse((self.args.output / "selection.json").exists())


if __name__ == "__main__":
    unittest.main()
