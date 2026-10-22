"""Verify a completed frozen release, align its20 models and report development evidence.

The release and completed evaluation ledger require caller-supplied digests.
No model is fitted, selected, or replayed here; saved probabilities and their
reported measures are checked against the independently verified queue.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import multiphone_child_train as child
import multiphone_controls as controls
import multiphone_outer_release as release
import multiphone_outer_statistics as statistics
import multiphone_outer_evaluate_queue as evaluation_queue
from multiphone_cache import digest

HERE = Path(__file__).resolve().parent
EXPECTED_ROWS = 14837
CHILD_PRIOR = "child-only-phone-prior"
ALL_PRIOR = "control-prior"
FULL13 = "scalar-full13"
SOURCES = sorted(set((*child.SOURCES, "multiphone_controls.py", "multiphone_outer_report.py",
                      "multiphone_outer_release.py", "multiphone_outer_statistics.py", "multiphone_outer_evaluate_queue.py")))
require = controls.require


def read_json(path):
    return json.loads(Path(path).read_text())


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCES}


def same_metrics(left, right):
    if isinstance(left, dict):
        return isinstance(right, dict) and left.keys() == right.keys() and all(same_metrics(v, right[k]) for k, v in left.items())
    if isinstance(left, list):
        return isinstance(right, list) and len(left) == len(right) and all(same_metrics(a, b) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        return isinstance(right, (int, float)) and np.isfinite(left) and np.isfinite(right) and bool(np.isclose(left, right, rtol=1e-12, atol=1e-12))
    return left == right


def checked_file(path, expected, pins):
    path = Path(path).resolve()
    require(isinstance(expected, str) and len(expected) == 64 and digest(path) == expected,
            "Pinned release/evaluation artifact digest differs")
    require(str(path) not in pins or pins[str(path)] == expected, "Conflicting artifact pins")
    pins[str(path)] = expected
    return path


def source_and_refit_links(report, config, job, manifest):
    require(report["sourceSha256"] == config["sourceSha256"], "Evaluation source differs from frozen refit")
    required = {str((Path(job["input"]) / name).resolve()) for name in
                ("config.json", "frozen.json", "checkpoint.pt" if job["kind"] in ("global", "head") else "checkpoint.json")}
    links = report["frozenArtifactsSha256"]
    require(required <= set(links) and all(manifest["filesSha256"].get(path) == sha for path, sha in links.items()),
            "Evaluation is not linked to the released refit")


def checked_probabilities(path, expected_rows):
    value = read_json(path)
    require(value["rowIndices"] == expected_rows and len(set(value["rowIndices"])) == len(expected_rows),
            "Prediction row order, coverage or identity differs")
    p = np.asarray(value["probabilities"], dtype=np.float64)
    require(p.shape == (len(expected_rows), 3) and np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all()
            and np.allclose(p.sum(1), 1, rtol=0, atol=1e-6), "Invalid finite probability distribution")
    return value, p


def prior_values(priors, rows):
    require(all(row["targetPhone"] in priors for row in rows), "Prior misses a target binding")
    return np.asarray([priors[row["targetPhone"]]["probabilities"] for row in rows], dtype=np.float64)


def guard_bundle(bundle):
    require(source_hashes() == bundle["sourceSha256"], "Report implementation changed")
    require(all(digest(Path(path)) == sha for path, sha in bundle["artifactSha256"].items()),
            "Released or evaluated artifact changed during analysis")
    release.guard_release(bundle["manifest"])


def load_predictions(release_path, release_sha256, ledger_path, ledger_sha256):
    pins = {}
    release_path = checked_file(release_path, release_sha256, pins)
    ledger_path = checked_file(ledger_path, ledger_sha256, pins)
    manifest, ledger = read_json(release_path), read_json(ledger_path)
    release.guard_release(manifest)
    sources = source_hashes()
    require(all(manifest["filesSha256"].get(str((HERE / name).resolve())) == sha for name, sha in sources.items()),
            "Release omitted or changed the reporting implementation")
    pins.update(manifest["filesSha256"])
    require(ledger["complete"] is True and Path(ledger["releasePath"]).resolve() == release_path
            and ledger["releaseSha256"] == release_sha256 and len(ledger["jobs"]) == 85,
            "Expected a completed evaluation ledger bound to this release")
    jobs = manifest["jobs"]
    require(len(jobs) == 85 and len({item["output"] for item in ledger["jobs"]}) == 85,
            "Duplicate or incomplete evaluation job inventory")
    by_output = {item["output"]: item for item in ledger["jobs"]}
    require(set(by_output) == {job["output"] for job in jobs}, "Evaluation ledger job set differs")
    output_root = Path(manifest["base"]) / "outer-evaluation-v1"
    require({str(p.resolve()) for p in output_root.iterdir() if p.is_dir()} == set(by_output),
            "Extra or missing evaluation directory")
    cohort, splits, _ = controls.load_study(Path(manifest["base"]) / "cohort.json", Path(manifest["base"]) / "splits.json")
    require(manifest["fittedPipelineCount"] == 19 and manifest["fittedPipelineFoldCount"] == 95
            and set(manifest["childPriorStateByFold"]) == {str(i) for i in range(5)}, "Release pipeline or prior inventory differs")
    eligible = [i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]]
    require(manifest["eligibleRows"] == eligible and len(eligible) == EXPECTED_ROWS,
            "Release eligible row set or declared cohort size differs")
    require(manifest["expectedEvaluationRowsByFold"] == {str(f["fold"]): f["outerHoldoutRows"] for f in splits["folds"]},
            "Released evaluation partitions differ")
    positions = {index: i for i, index in enumerate(eligible)}
    rows = [cohort["rows"][i] for i in eligible]
    require(all(row["targetPhone"] == cohort["targetPhones"][row["targetId"]] for row in rows), "Canonical target identity differs")
    row_folds = [-1] * len(rows)
    child_prior = np.full((len(rows), 3), np.nan)
    for fold in splits["folds"]:
        child_fit = [cohort["rows"][i] for i in fold["outerFitRows"] if child.is_child(cohort["rows"][i])]
        expected_prior = child.fit_priors(child_fit)
        require(manifest["childPriorStateByFold"][str(fold["fold"])] == expected_prior, "Released child prior differs from exact fit rows")
        targets = [cohort["rows"][i] for i in fold["outerHoldoutRows"]]
        locations = [positions[i] for i in fold["outerHoldoutRows"]]
        require(all(row_folds[i] == -1 for i in locations), "Duplicate outer row across folds")
        child_prior[locations] = prior_values(expected_prior, targets)
        for i in locations:
            row_folds[i] = fold["fold"]
    models, seen_words, regimes, filled = {}, {}, {}, {}

    def append(name, p, indices, fit_indices, regime):
        if name not in models:
            models[name], seen_words[name] = np.full((len(rows), 3), np.nan), np.zeros(len(rows), dtype=bool)
            regimes[name], filled[name] = regime, set()
        require(regimes[name] == regime and not filled[name].intersection(indices), "Duplicate model/row or inconsistent regime")
        locations = [positions[i] for i in indices]
        vocabulary = {cohort["rows"][i]["targetWord"] for i in fit_indices}
        models[name][locations] = p
        seen_words[name][locations] = [cohort["rows"][i]["targetWord"] in vocabulary for i in indices]
        filled[name].update(indices)

    for job in jobs:
        entry = by_output[job["output"]]
        require(all(entry.get(key) == value for key, value in job.items()) and entry["state"] == "complete"
                and entry["exitCode"] == 0, "Evaluation job identity or completion differs")
        output, input_path = Path(job["output"]), Path(job["input"])
        file_map = entry["verified"]["artifactSha256"]
        require(all(Path(path).resolve().is_relative_to(output.resolve()) for path in file_map), "Evaluation pin escapes its job directory")
        for path, sha in file_map.items():
            checked_file(path, sha, pins)
        require(evaluation_queue.verify_output(job, manifest, cohort) == file_map,
                "Evaluation artifact set differs from verified queue publication")
        required = {str((output / "report.json").resolve())}
        predictions = [family + "-predictions.json" for family in controls.FAMILIES] if job["kind"] == "controls" else ["predictions.json"]
        required.update(str((output / name).resolve()) for name in predictions)
        if job["kind"] in ("global", "head"):
            required.add(str((output / "prior.json").resolve()))
        if job["kind"] == "controls":
            required.update(str((output / name).resolve()) for name in ("verified.json", "config.json"))
        require(required <= set(file_map) and {p.name for p in output.glob("*predictions.json")} == set(predictions),
                "Unpinned or extra prediction/report artifacts")
        report, config = read_json(output / "report.json"), read_json(input_path / "config.json")
        require(report["authorTestInferencePerformed"] is False and report["clinicalUseEligible"] is False
                and report["learnerFeedbackEligible"] is False, "Evaluation scope differs")
        fold = splits["folds"][job["fold"]]
        indices = fold["outerHoldoutRows"]
        target_rows = [cohort["rows"][i] for i in indices]
        fit_indices = [i for i in fold["outerFitRows"] if job["regime"] == "all-age" or child.is_child(cohort["rows"][i])]
        require(config["fitRows"] == fit_indices and config["fold"] == job["fold"], "Refit population differs from pipeline")
        if job["kind"] == "controls":
            verified, eval_config = read_json(output / "verified.json"), read_json(output / "config.json")
            require(verified["complete"] is True and verified["phase"] == "evaluate"
                    and verified["reportSha256"] == digest(output / "report.json")
                    and report["configSha256"] == digest(output / "config.json")
                    and eval_config["fold"] == job["fold"] and eval_config["evaluationRows"] == indices
                    and report["evaluationPartition"] == "outerHoldoutRows"
                    and set(report["results"]) == set(controls.FAMILIES), "Control evaluation publication differs")
            require(all(manifest["filesSha256"].get(path) == sha for path, sha in verified["frozenInputArtifactsSha256"].items()),
                    "Control frozen links differ from release")
            for family in controls.FAMILIES:
                path = output / (family + "-predictions.json")
                require(verified["predictionArtifactsSha256"].get(str(path.resolve())) == digest(path), "Control prediction digest differs")
                _, p = checked_probabilities(path, indices)
                require(same_metrics(report["results"][family]["metrics"], controls.score_predictions(p, target_rows)),
                        "Saved control metrics differ from probabilities")
                frozen = read_json(input_path / "frozen.json")
                require(report["results"][family]["setting"] == frozen["states"][family]["setting"], "Control setting differs")
                if family == "prior":
                    require(np.array_equal(p, prior_values(child.fit_priors([cohort["rows"][i] for i in fit_indices]), target_rows)),
                            "All-age prior differs from its exact fit population")
                append("control-" + family, p, indices, fit_indices, "all-age")
        else:
            require(report["complete"] is True and report["phase"] == "outer-evaluation" and report["fold"] == job["fold"],
                    "Incomplete or wrong-fold evaluation")
            source_and_refit_links(report, config, job, manifest)
            require(report["predictionsSha256"] == digest(output / "predictions.json"), "Prediction digest differs from report")
            _, p = checked_probabilities(output / "predictions.json", indices)
            require("evaluationRows" not in report or report["evaluationRows"] == indices, "Reported evaluation rows differ")
            require(same_metrics(report["evaluation"], child.score_predictions(p, target_rows)), "Saved model metrics differ from probabilities")
            if job["kind"] == "head":
                require(report["kind"] == job["encoderKind"] and report["family"] == job["family"]
                        and report["regime"] == job["regime"], "Reported head pipeline differs")
            if job["kind"] in ("global", "head"):
                require(report["priorSha256"] == digest(output / "prior.json"), "Stored head prior digest differs")
                saved_prior, p_prior = checked_probabilities(output / "prior.json", indices)
                expected_prior = child.fit_priors([cohort["rows"][i] for i in fit_indices])
                require(config["priorState"] == expected_prior and np.array_equal(p_prior, prior_values(expected_prior, target_rows))
                        and same_metrics(saved_prior["evaluation"], child.score_predictions(p_prior, target_rows)),
                        "Stored head prior differs from exact fit rows or target binding")
                if job["regime"] == "child-only":
                    require(np.array_equal(p_prior, child_prior[[positions[i] for i in indices]]), "Head and released child priors differ")
            append(job["name"], p, indices, fit_indices, job["regime"])
    require(len(models) == 19 and all(indices == set(eligible) for indices in filled.values()) and min(row_folds) >= 0,
            "Incomplete19-pipeline canonical row alignment")
    models[CHILD_PRIOR], regimes[CHILD_PRIOR] = child_prior, "child-only"
    seen_words[CHILD_PRIOR] = np.zeros(len(rows), dtype=bool)
    for fold in splits["folds"]:
        vocab = {cohort["rows"][i]["targetWord"] for i in fold["outerFitRows"] if child.is_child(cohort["rows"][i])}
        for i in fold["outerHoldoutRows"]:
            seen_words[CHILD_PRIOR][positions[i]] = cohort["rows"][i]["targetWord"] in vocab
    statistics.validate_inputs(models, rows, row_folds, {})
    bundle = {"manifest": manifest, "releasePath": str(release_path), "releaseSha256": release_sha256,
              "evaluationLedgerPath": str(ledger_path), "evaluationLedgerSha256": ledger_sha256,
              "sourceSha256": sources, "artifactSha256": pins, "rowIndices": eligible,
              "rows": rows, "rowFolds": row_folds, "models": models, "regimes": regimes, "seenTargetWords": seen_words}
    guard_bundle(bundle)
    return bundle


def declared_pairs(model_names, regimes):
    pairs = {name: [ref for ref in (ALL_PRIOR, FULL13) if ref != name] for name in model_names}
    for name in model_names:
        if regimes[name] == "child-only" and name != CHILD_PRIOR:
            pairs[name].append(CHILD_PRIOR)
    pairs[FULL13].append("scalar-local-scalars")
    for regime in ("all-age", "child-only"):
        for suffix in ("", "-scalars"):
            pairs[f"phonetic-target{suffix}-{regime}"].append(f"phonetic-global{suffix}-{regime}")
    return {name: list(dict.fromkeys(refs)) for name, refs in pairs.items()}


def point_slice(p, rows):
    counts = np.asarray([r["raterCounts"] for r in rows], dtype=float).reshape(-1, 3)
    support = statistics.support_for(rows, counts)
    if not rows:
        return {"support": support, "point": {metric: None for metric in statistics.METRICS}, "perPhone": {}}
    phones, speakers = sorted({r["targetPhone"] for r in rows}), sorted({r["speakerId"] for r in rows})
    phone_ids = np.asarray([phones.index(r["targetPhone"]) for r in rows])
    speaker_ids = np.asarray([speakers.index(r["speakerId"]) for r in rows])
    fixed = {}
    for event in statistics.EVENTS:
        fixed[event] = []
        for i, phone in enumerate(phones):
            c = counts[phone_ids == i].sum(0)
            pos, neg = (c[0], c[1] + c[2]) if event == "rating0" else (c[0] + c[1], c[2])
            if pos > 0 and neg > 0:
                fixed[event].append(phone)
    values, per_phone = statistics.score_model(np.asarray(p), counts, phone_ids, speaker_ids, phones,
                                                np.ones((1, len(speakers))), fixed, 64)
    return {"support": support, "fixedProperPhones": phones, "fixedRankingPhones": fixed,
            "point": {metric: statistics.finite_or_none(value[0]) for metric, value in values.items()}, "perPhone": per_phone}


def age_points(p, rows):
    result = {}
    for age in statistics.SLICES:
        mask = np.asarray([age == "allAges" or statistics.age_slice(r["age"]) == age for r in rows], dtype=bool)
        result[age] = point_slice(p[mask], [r for r, ok in zip(rows, mask) if ok])
    return result


def build_report(bundle, replicates=2000):
    pairs = declared_pairs(bundle["models"], bundle["regimes"])
    measures = statistics.compute_statistics(bundle["models"], bundle["rows"], bundle["rowFolds"], pairs,
                                             replicates=replicates, seed=20260926)
    folds, lexical = {}, {}
    for fold in range(5):
        mask = np.asarray(bundle["rowFolds"]) == fold
        rows = [r for r, ok in zip(bundle["rows"], mask) if ok]
        folds[str(fold)] = {name: age_points(p[mask], rows) for name, p in bundle["models"].items()}
    for name, p in bundle["models"].items():
        lexical[name] = {}
        for label, mask in (("seenTargetWord", bundle["seenTargetWords"][name]),
                            ("unseenTargetWord", ~bundle["seenTargetWords"][name])):
            lexical[name][label] = age_points(p[mask], [r for r, ok in zip(bundle["rows"], mask) if ok])
    return {"complete": True, "phase": "development-cross-fit-report", "releasePath": bundle["releasePath"],
            "releaseSha256": bundle["releaseSha256"], "evaluationLedgerPath": bundle["evaluationLedgerPath"],
            "evaluationLedgerSha256": bundle["evaluationLedgerSha256"], "sourceSha256": bundle["sourceSha256"],
            "artifactSha256": bundle["artifactSha256"], "alignedRowIndices": bundle["rowIndices"],
            "fittedPipelines": 19, "additionalComparators": [CHILD_PRIOR], "regimes": bundle["regimes"],
            "statistics": measures, "perFold": folds, "targetWordSlices": lexical,
            "targetWordSliceDefinition": "Exact targetWord membership in that prediction's own outer-fold/regime fit target-row vocabulary; words can still occur elsewhere in fitting utterances, so this is not word-disjoint evaluation.",
            "authorTestInferencePerformed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False,
            "winnerSelectionPerformed": False,
            "interpretation": "Development cross-fit only: architecture decisions used overlapping inner outcomes. Child-only fitting and selection change together. No independent child-SSD validation or ages2–5 evidence."}


def markdown(report):
    s = report["statistics"]["slices"]
    def fmt(value):
        return "undefined" if value is None else f"{value:.4f}"
    lines = ["# Frozen development cross-fit comparison", "",
             "All 19 fixed pipelines and the child-fit prior are reported. These speaker-disjoint predictions remain development evidence: architecture choices used overlapping inner outcomes. No outer winner was selected.", "",
             "| Pipeline | All-age macro NLL | Child macro NLL | Child ΔNLL vs matched prior | Child rating0 within-phone AUC | Child below2 within-phone AUC |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name in report["statistics"]["modelNames"]:
        all_point, point = s["allAges"]["models"][name]["point"], s["ages6to12"]["models"][name]["point"]
        prior = CHILD_PRIOR if report["regimes"][name] == "child-only" else ALL_PRIOR
        reference = s["ages6to12"]["models"][prior]["point"]["macroTargetLogLoss"]
        delta = None if point["macroTargetLogLoss"] is None or reference is None else point["macroTargetLogLoss"] - reference
        lines.append(f"| {name} | {fmt(all_point['macroTargetLogLoss'])} | {fmt(point['macroTargetLogLoss'])} | {fmt(delta)} | {fmt(point['macroTarget.rating0.auroc'])} | {fmt(point['macroTarget.ratingBelow2.auroc'])} |")
    lines += ["", "Lower NLL measures better probability fit; higher AUC measures ranking. Report both: an improvement in one does not establish improvement in the other. Average precision, per-rater Brier, expected-rating MAE, all paired intervals and per-phone support remain in the JSON report.", "",
              "| Ages | Speakers | Clips | Target rows | Rater counts 0/1/2 |", "| --- | ---: | ---: | ---: | --- |"]
    for age in statistics.SLICES[1:]:
        support = s[age]["support"]
        lines.append(f"| {age} | {support['speakers']} | {support['clips']} | {support['positions']} | {' / '.join(map(str,support['observedRaterCounts']))} |")
    lines += ["", "The JSON retains all five fold results and each pipeline's seen/unseen target-word slices. Those slices use its actual fitting population and do not establish word-disjoint generalization.", "",
              "Intervals use 2,000 paired speaker resamples within outer-fold × age strata, conditional on the frozen models. Fixed phone sets are retained; intervals with fewer than 95% valid draws are withheld. Undefined ranking is never replaced with zero.", "",
              "These are subjective corpus ratings at canonical positions. CTC windows are estimates; contextual features include surrounding speech. Ages 2–5 and an independent child speech-sound-disorder cohort are absent. Author-test stayed closed. No learner pronunciation judgment or clinical feedback is authorized by these results.", ""]
    return "\n".join(lines)


def run_report(release_path, release_sha256, ledger_path, ledger_sha256, output):
    staging = output.with_name(output.name + ".partial")
    require(output.resolve().is_relative_to((HERE / "outputs").resolve()) and not output.exists()
            and not staging.exists(), "Choose a fresh ignored report directory")
    bundle = load_predictions(release_path, release_sha256, ledger_path, ledger_sha256)
    report = build_report(bundle)
    rendered = markdown(report)
    guard_bundle(bundle)
    staging.mkdir(parents=True, mode=0o700)
    for name, value in (("report.json", json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"), ("report.md", rendered)):
        with (staging / name).open("x") as stream:
            stream.write(value)
    guard_bundle(bundle)
    staging.rename(output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--ledger-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_report(args.release, args.release_sha256, args.ledger, args.ledger_sha256, args.output)
    print(f"Verified {result['fittedPipelines']} fixed pipelines plus child prior; {args.output}")
