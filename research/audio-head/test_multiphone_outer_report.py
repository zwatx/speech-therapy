"""Fabricated85-job publication fixtures; no corpus, model inference or real outer reads."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import multiphone_outer_report as report
from multiphone_data import build_splits
import test_multiphone_outer_evaluate_queue as queue_fixtures


class OuterReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = queue_fixtures.EvaluationQueueTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root = f.base
        # One child's held-out target word occurs only on an adult fit row.
        fold = next(x for x in f.splits["folds"] if any(report.child.is_child(f.cohort["rows"][i]) for i in x["outerHoldoutRows"]))
        target = next(i for i in fold["outerHoldoutRows"] if report.child.is_child(f.cohort["rows"][i]))
        adult = next(i for i in fold["outerFitRows"] if not report.child.is_child(f.cohort["rows"][i]))
        f.cohort["rows"][target]["targetWord"] = f.cohort["rows"][adult]["targetWord"]
        f.splits = build_splits(f.cohort)
        self.word_case = target
        for name, value in (("cohort.json", f.cohort), ("splits.json", f.splits)):
            f.save(self.root / name, value)
            f.files[str(self.root / name)] = report.digest(self.root / name)
        f.files.update({str((report.HERE / name).resolve()): sha for name, sha in report.source_hashes().items()})
        f.manifest.update(fittedPipelineCount=19, fittedPipelineFoldCount=95, childPriorStateByFold={})
        for fold in f.splits["folds"]:
            child_rows = [f.cohort["rows"][i] for i in fold["outerFitRows"] if report.child.is_child(f.cohort["rows"][i])]
            f.manifest["childPriorStateByFold"][str(fold["fold"])] = report.child.fit_priors(child_rows)
        for job in f.jobs:
            directory = Path(job["input"])
            indices = [i for i in f.splits["folds"][job["fold"]]["outerFitRows"]
                       if job["regime"] == "all-age" or report.child.is_child(f.cohort["rows"][i])]
            config = report.read_json(directory / "config.json")
            config.update(fold=job["fold"], fitRows=indices,
                          priorState=report.child.fit_priors([f.cohort["rows"][i] for i in indices]))
            f.save(directory / "config.json", config)
            if job["kind"] == "controls":
                f.save(directory / "frozen.json", {"states": {family: {"setting": .01} for family in report.controls.FAMILIES}})
            for name in ("config.json", "frozen.json"):
                f.files[str(directory / name)] = report.digest(directory / name)
        f.commit_release()
        records = []
        for job in f.jobs:
            f.publish(job)
            output, directory = Path(job["output"]), Path(job["input"])
            indices = f.splits["folds"][job["fold"]]["outerHoldoutRows"]
            rows = [f.cohort["rows"][i] for i in indices]
            config = report.read_json(directory / "config.json")
            prior = report.prior_values(config["priorState"], rows)
            saved = report.read_json(output / "report.json")
            if job["kind"] == "controls":
                for family in report.controls.FAMILIES:
                    path = output / (family + "-predictions.json")
                    values = prior if family == "prior" else np.tile([.2, .1, .7], (len(rows), 1))
                    f.save(path, {"rowIndices": indices, "probabilities": values.tolist()})
                    saved["results"][family] = {"setting": .01, "metrics": report.controls.score_predictions(values, rows)}
                f.save(output / "report.json", saved)
                verified = report.read_json(output / "verified.json")
                verified.update(reportSha256=report.digest(output / "report.json"), predictionArtifactsSha256={
                    str(output / (family + "-predictions.json")): report.digest(output / (family + "-predictions.json"))
                    for family in report.controls.FAMILIES})
                f.save(output / "verified.json", verified)
            else:
                values = report.read_json(output / "predictions.json")["probabilities"]
                saved["evaluation"] = report.child.score_predictions(np.asarray(values), rows)
                if job["kind"] in ("global", "head"):
                    f.save(output / "prior.json", {"rowIndices": indices, "probabilities": prior.tolist(),
                                                   "evaluation": report.child.score_predictions(prior, rows)})
                    saved["priorSha256"] = report.digest(output / "prior.json")
                f.save(output / "report.json", saved)
            artifact_map = report.evaluation_queue.verify_output(job, f.manifest, f.cohort)
            records.append({**job, "state": "complete", "exitCode": 0, "verified": {"artifactSha256": artifact_map}})
        self.ledger = {"complete": True, "releasePath": str(f.path), "releaseSha256": f.sha, "jobs": records}
        self.ledger_path = self.root / "ledger.json"
        self.commit_ledger()
        self.size_patch = patch.object(report, "EXPECTED_ROWS", len(f.cohort["rows"]))
        self.size_patch.start()
        self.addCleanup(self.size_patch.stop)

    def commit_ledger(self):
        self.fixture.save(self.ledger_path, self.ledger)
        self.ledger_sha = report.digest(self.ledger_path)

    def refresh_output_pins(self, record):
        record["verified"]["artifactSha256"] = {path: report.digest(Path(path)) for path in record["verified"]["artifactSha256"]}
        self.commit_ledger()

    def load(self):
        return report.load_predictions(self.fixture.path, self.fixture.sha, self.ledger_path, self.ledger_sha)

    def test_complete85_jobs_align20_models_with_exact_priors_and_regime_vocabularies(self):
        bundle = self.load()
        self.assertEqual(len(bundle["models"]), 20)
        self.assertEqual(bundle["rowIndices"], list(range(len(self.fixture.cohort["rows"]))))
        for values in bundle["models"].values():
            self.assertEqual(values.shape, (20, 3))
            np.testing.assert_allclose(values.sum(1), 1)
        self.assertTrue(bundle["seenTargetWords"]["global-wavlm-mean"][self.word_case])
        self.assertFalse(bundle["seenTargetWords"]["local-embedding-child-only"][self.word_case])
        self.assertFalse(bundle["seenTargetWords"][report.CHILD_PRIOR][self.word_case])
        result = report.build_report(bundle, replicates=20)
        self.assertFalse(result["winnerSelectionPerformed"])
        self.assertEqual(len(result["perFold"]), 5)
        for name in bundle["models"]:
            self.assertEqual(sum(result["targetWordSlices"][name][part]["allAges"]["support"]["positions"]
                                 for part in ("seenTargetWord", "unseenTargetWord")), 20)
        pairs = result["statistics"]["referencePairs"]
        self.assertIn(report.CHILD_PRIOR, pairs["phonetic-target-child-only"])
        self.assertIn("phonetic-global-all-age", pairs["phonetic-target-all-age"])
        self.assertIn("scalar-local-scalars", pairs[report.FULL13])
        text = report.markdown(result)
        self.assertIn("No outer winner", text)
        self.assertIn("does not establish improvement", text)
        self.assertIn("not word-disjoint", result["targetWordSliceDefinition"])

    def test_partial_duplicate_and_extra_directory_inventory_are_rejected(self):
        original = deepcopy(self.ledger)
        for records in (original["jobs"][:-1], original["jobs"][:-1] + [original["jobs"][0]]):
            self.ledger["jobs"] = records
            self.commit_ledger()
            with self.assertRaises(ValueError):
                self.load()
        self.ledger = original
        self.commit_ledger()
        (self.root / "outer-evaluation-v1" / "extra").mkdir()
        with self.assertRaisesRegex(ValueError, "Extra or missing"):
            self.load()

    def test_rehashed_wrong_metrics_are_rejected_after_ledger_integrity_passes(self):
        record = self.ledger["jobs"][0]
        path = Path(record["output"]) / "report.json"
        saved = report.read_json(path)
        saved["evaluation"]["allAges"]["macroTargetLogLoss"] += .1
        self.fixture.save(path, saved)
        self.refresh_output_pins(record)
        with self.assertRaisesRegex(ValueError, "metrics differ from probabilities"):
            self.load()

    def test_row_order_and_duplicate_rows_fail_even_with_updated_hashes(self):
        record = self.ledger["jobs"][0]
        output = Path(record["output"])
        p = report.read_json(output / "predictions.json")
        original = deepcopy(p)
        for indices in (p["rowIndices"][::-1], [p["rowIndices"][0]] * len(p["rowIndices"])):
            changed = {**original, "rowIndices": indices}
            self.fixture.save(output / "predictions.json", changed)
            saved = report.read_json(output / "report.json")
            saved["predictionsSha256"] = report.digest(output / "predictions.json")
            self.fixture.save(output / "report.json", saved)
            self.refresh_output_pins(record)
            with self.assertRaisesRegex(ValueError, "outer rows"):
                self.load()

    def test_ledger_hash_source_pin_and_artifact_tampering_are_independent_guards(self):
        with self.assertRaisesRegex(ValueError, "artifact digest"):
            report.load_predictions(self.fixture.path, self.fixture.sha, self.ledger_path, "0" * 64)
        with patch.object(report, "source_hashes", return_value={"multiphone_outer_report.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "reporting implementation"):
                self.load()
        path = Path(self.ledger["jobs"][0]["output"]) / "report.json"
        path.write_text(path.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "artifact digest"):
            self.load()

    def test_child_prior_target_values_must_match_released_fit_counts(self):
        record = next(j for j in self.ledger["jobs"] if j["regime"] == "child-only")
        output = Path(record["output"])
        prior = report.read_json(output / "prior.json")
        prior["probabilities"][0] = [.8, .1, .1]
        rows = [self.fixture.cohort["rows"][i] for i in prior["rowIndices"]]
        prior["evaluation"] = report.child.score_predictions(np.asarray(prior["probabilities"]), rows)
        self.fixture.save(output / "prior.json", prior)
        saved = report.read_json(output / "report.json")
        saved["priorSha256"] = report.digest(output / "prior.json")
        self.fixture.save(output / "report.json", saved)
        self.refresh_output_pins(record)
        with self.assertRaisesRegex(ValueError, "Stored head prior differs"):
            self.load()

    def test_negative_probability_is_rejected_with_self_consistent_hashes(self):
        record = self.ledger["jobs"][0]
        output = Path(record["output"])
        saved = report.read_json(output / "predictions.json")
        saved["probabilities"][0] = [-.1, .1, 1.]
        self.fixture.save(output / "predictions.json", saved)
        data = report.read_json(output / "report.json")
        data["predictionsSha256"] = report.digest(output / "predictions.json")
        self.fixture.save(output / "report.json", data)
        self.refresh_output_pins(record)
        with self.assertRaisesRegex(ValueError, "probabilities"):
            self.load()

    def test_late_artifact_mutation_prevents_report_publication(self):
        output = self.root / "summary"
        original = report.build_report
        def mutate(bundle):
            result = original(bundle, replicates=10)
            path = Path(self.ledger["jobs"][0]["output"]) / "report.json"
            path.write_text(path.read_text() + " ")
            return result
        with patch.object(report, "build_report", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                report.run_report(self.fixture.path, self.fixture.sha, self.ledger_path, self.ledger_sha, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
