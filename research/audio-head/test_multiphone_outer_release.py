"""Release inventory and provenance tests use fabricated metadata, not speech."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import multiphone_outer_release as release
from multiphone_cache import digest
from test_multiphone_controls import synthetic_study
from test_multiphone_local_train import save


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=release.HERE / "outputs", prefix="test-release-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cohort, self.splits = synthetic_study()

    def job(self):
        return next(job for job in release.expected_jobs(self.root)
                    if job["name"] == "local-embedding-child-only" and job["fold"] == 0)

    def make_refit(self):
        job = self.job()
        directory = Path(job["input"])
        directory.mkdir(parents=True)
        config = {"fold": 0, "phase": "outer-refit", "kind": "local", "family": "embedding",
                  "regime": "child-only", "seed": 7, "outerOutcomesUsed": False,
                  "authorTestInferencePerformed": False, "sourceSha256": {}, "innerArtifactsSha256": {},
                  "fixedEpochs": 2, "learningRate": .0003, "selected": {"epochs": 2, "lr": .0003},
                  "fitRows": [i for i in self.splits["folds"][0]["outerFitRows"]
                              if release.is_child(self.cohort["rows"][i])]}
        save(directory / "config.json", config)
        save(directory / "history.json", [{"epoch": 1}, {"epoch": 2}])
        (directory / "checkpoint.pt").write_bytes(b"synthetic metadata fixture; not a trained checkpoint")
        frozen = {"complete": True, "epochsRun": 2, "holdoutPredictionsComputed": False, "outerOutcomesUsed": False,
                  "configSha256": digest(directory / "config.json"), "checkpointSha256": digest(directory / "checkpoint.pt"),
                  "historySha256": digest(directory / "history.json")}
        save(directory / "frozen.json", frozen)
        return job, directory, config, frozen

    def test_inventory_is_complete_and_commands_are_generated_from_known_helpers(self):
        jobs = release.expected_jobs(self.root)
        self.assertEqual(len(jobs), 85)
        self.assertEqual(sum(3 if job["kind"] == "controls" else 1 for job in jobs), 95)
        self.assertEqual(len({(job["name"], job["fold"]) for job in jobs}), 85)
        for job in jobs:
            command = release.evaluation_command(job, self.root)
            self.assertEqual(command[1], str(release.HERE / release.HELPERS[job["kind"]]))
            self.assertEqual(command[2], "evaluate")
            self.assertEqual(command[command.index("--input") + 1], job["input"])

    def test_child_refit_requires_exact_child_fit_rows(self):
        job, directory, config, frozen = self.make_refit()
        release.checked_refit(job, self.cohort, self.splits)
        config["fitRows"] = self.splits["folds"][0]["outerFitRows"]
        save(directory / "config.json", config)
        frozen["configSha256"] = digest(directory / "config.json")
        save(directory / "frozen.json", frozen)
        with self.assertRaisesRegex(ValueError, "scope, rows"):
            release.checked_refit(job, self.cohort, self.splits)

    def test_wrong_head_identity_is_rejected_even_if_hashes_match(self):
        job, directory, config, frozen = self.make_refit()
        config["family"] = "embedding-scalars"
        save(directory / "config.json", config)
        frozen["configSha256"] = digest(directory / "config.json")
        save(directory / "frozen.json", frozen)
        with self.assertRaisesRegex(ValueError, "identity differs"):
            release.checked_refit(job, self.cohort, self.splits)

    def test_changed_checkpoint_and_already_scored_refit_are_rejected(self):
        job, directory, _, _ = self.make_refit()
        path = directory / "checkpoint.pt"
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "checkpoint changed"):
            release.checked_refit(job, self.cohort, self.splits)
        path.write_bytes(original)
        save(directory / "predictions.json", {})
        with self.assertRaisesRegex(ValueError, "scope, rows"):
            release.checked_refit(job, self.cohort, self.splits)

    def test_nested_input_bindings_are_verified_without_invented_hashes(self):
        path = self.root / "features.npy"
        path.write_bytes(b"synthetic")
        sha = digest(path)
        value = {"nested": [{"path": str(path), "sha256": sha}], "featurePath": str(path),
                 "featureSha256": sha, "inputArtifactsSha256": {str(path): sha}}
        self.assertEqual(release.pinned_inputs(value), {str(path): sha})
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Pinned refit input changed"):
            release.pinned_inputs(value)

    def test_partial_inventory_and_command_injection_are_rejected(self):
        manifest = {"complete": True, "phase": "frozen-development-release", "holdoutPredictionsAllowed": True,
                    "authorTestInferenceAllowed": False, "base": str(self.root), "jobs": release.expected_jobs(self.root),
                    "filesSha256": {}}
        with self.assertRaisesRegex(ValueError, "mandatory"):
            release.guard_release(manifest)
        changed = deepcopy(manifest)
        changed["jobs"][0]["command"] = ["untrusted"]
        with self.assertRaisesRegex(ValueError, "job inventory"):
            release.guard_release(changed)
        changed = deepcopy(manifest)
        changed["jobs"].pop()
        with self.assertRaisesRegex(ValueError, "job inventory"):
            release.guard_release(changed)

    def test_incomplete_refits_cannot_publish_release(self):
        save(self.root / "cohort.json", self.cohort)
        save(self.root / "splits.json", self.splits)
        output = self.root / "release.json"
        with self.assertRaises(FileNotFoundError):
            release.freeze(self.root, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
