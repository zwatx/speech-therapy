"""Train-only speaker-block label-permutation sanity control for /R/ ratings.

One fixed permutation is descriptive, not a null distribution or significance test.
The published author test partition is never loaded for labels or evaluation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from speechocean_r_rater_cv import (AUTHORITY, V2_RECIPE, evaluate,
                                    load_rater_counts, load_recipe as load_cv_recipe,
                                    load_train_features, require)
from speechocean_train_cv import HERE, outer_speaker_folds, sha256_file, write_json


RECIPE = HERE / "experiments/speechocean-r-rater-negative-control-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-rater-negative-control-v1"
EXPECTED_FIELDS = {
    "schemaVersion", "experiment", "purpose", "authorPartition", "referenceRecipe",
    "referenceRecipeSha256", "referenceReport", "referenceReportSha256",
    "referenceOutOfFoldSha256", "expectedTrainClips", "expectedTrainSpeakers",
    "expectedRaterScoresPerClip", "permutationSeed", "permutation",
    "nestedEvaluation", "permutationReplicates", "outputDirectory", "knownAuthorTest",
    "authorTestUsedForSettings", *AUTHORITY,
}


def load_control_recipe(path: Path = RECIPE) -> tuple[dict, dict, dict]:
    require(path.resolve() == RECIPE.resolve(), "Control recipe path differs from locked recipe")
    control = json.loads(path.read_text())
    require(set(control) == EXPECTED_FIELDS and
            control["schemaVersion"] == 1 and
            control["experiment"] == "speechocean-r-rater-negative-control-v1" and
            control["authorPartition"] == "train" and
            control["referenceRecipe"] == "experiments/speechocean-r-rater-cv-convergence-v2.json" and
            control["referenceRecipeSha256"] ==
                "f17a024acb7837679a0818d7fbd5f617c0b1ba0ec3cb56c127531adabe22c5f5" and
            control["referenceReport"] ==
                "outputs/speechocean-r-rater-cv-convergence-v2/report.json" and
            control["referenceReportSha256"] ==
                "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa" and
            control["referenceOutOfFoldSha256"] ==
                "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c" and
            control["expectedTrainClips"] == 766 and
            control["expectedTrainSpeakers"] == 124 and
            control["expectedRaterScoresPerClip"] == 5 and
            control["permutationSeed"] == 20260923 and
            control["permutationReplicates"] == 1 and
            control["outputDirectory"] == "outputs/speechocean-r-rater-negative-control-v1" and
            control["knownAuthorTest"] is True and
            control["authorTestUsedForSettings"] is False and
            all(control[key] is False for key in AUTHORITY),
            "Control recipe differs from predeclaration")
    require(sha256_file(V2_RECIPE) == control["referenceRecipeSha256"],
            "Reference v2 recipe SHA-256 mismatch")
    reference_path = HERE / control["referenceReport"]
    require(sha256_file(reference_path) == control["referenceReportSha256"],
            "Reference v2 report SHA-256 mismatch")
    reference = json.loads(reference_path.read_text())
    require(reference["outOfFoldSha256"] == control["referenceOutOfFoldSha256"] and
            reference["authorPartition"] == "train" and
            reference["authorTestUsedForSettings"] is False and
            all(reference[key] is False for key in AUTHORITY),
            "Reference v2 report is not the pinned train-only result")
    return control, load_cv_recipe(V2_RECIPE), reference


def permute_rating_blocks(rows: list[dict], counts: np.ndarray, folds: dict[str, int],
                          seed: int) -> tuple[np.ndarray, list[int], dict]:
    """Move intact five-rating objects between equal-size speakers in each fold."""
    require(len(rows) == len(counts) and counts.shape[1:] == (3,) and
            len({row["id"] for row in rows}) == len(rows) and
            set(folds) == {row["speaker"] for row in rows} and
            np.all(counts.sum(axis=1) == 5), "Invalid speaker-block permutation input")
    indices_by_speaker: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        indices_by_speaker[row["speaker"]].append(index)
    for speaker, indices in indices_by_speaker.items():
        indices_by_speaker[speaker] = sorted(indices, key=lambda index: rows[index]["id"])
    groups: dict[tuple[int, int], list[str]] = defaultdict(list)
    for speaker, indices in indices_by_speaker.items():
        groups[(folds[speaker], len(indices))].append(speaker)

    source_indices = list(range(len(rows)))
    strata = []
    for (fold, size), speakers in sorted(groups.items()):
        ordered = sorted(speakers, key=lambda speaker: hashlib.sha256(
            f"{seed}:{fold}:{size}:{speaker}".encode()).hexdigest())
        for position, target_speaker in enumerate(ordered):
            source_speaker = ordered[(position + 1) % len(ordered)]
            for target_index, source_index in zip(indices_by_speaker[target_speaker],
                                                   indices_by_speaker[source_speaker]):
                source_indices[target_index] = source_index
        strata.append({"outerFold": fold, "clipsPerSpeaker": size,
                       "speakers": len(ordered), "clips": len(ordered) * size,
                       "unchangedBecauseSingleton": len(ordered) == 1})

    require(sorted(source_indices) == list(range(len(rows))) and
            all(folds[rows[target]["speaker"]] == folds[rows[source]["speaker"]] and
                len(indices_by_speaker[rows[target]["speaker"]]) ==
                    len(indices_by_speaker[rows[source]["speaker"]])
                for target, source in enumerate(source_indices)),
            "Permutation did not preserve all fold and speaker-block memberships")
    permuted = counts[source_indices].copy()
    for fold in set(folds.values()):
        indices = [i for i, row in enumerate(rows) if folds[row["speaker"]] == fold]
        require(Counter(map(tuple, counts[indices])) == Counter(map(tuple, permuted[indices])),
                "Five-rating objects changed within an outer fold")
    moved = sum(target != source for target, source in enumerate(source_indices))
    vector_changed = int(np.count_nonzero(np.any(permuted != counts, axis=1)))
    require(moved > 0 and vector_changed > 0, "Permutation did not disrupt any feature-label pairing")
    mapping = "".join(f"{rows[target]['id']}:{rows[source]['id']}\n"
                      for target, source in enumerate(source_indices))
    diagnostics = {"sourceMappingSha256": hashlib.sha256(mapping.encode()).hexdigest(),
                   "speakerBlocksMoved": sum(item["speakers"] for item in strata
                                             if not item["unchangedBecauseSingleton"]),
                   "speakerBlocksUnchanged": sum(item["speakers"] for item in strata
                                                 if item["unchangedBecauseSingleton"]),
                   "clipSourceIdsMoved": moved,
                   "clipSourceIdsUnchanged": len(rows) - moved,
                   "fiveScoreVectorsChanged": vector_changed,
                   "fiveScoreVectorsUnchanged": len(rows) - vector_changed,
                   "strata": strata}
    return permuted, source_indices, diagnostics


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Control output must be the unused locked research directory")
    control, cv_recipe, reference = load_control_recipe()
    torch.manual_seed(cv_recipe["outerSeed"])
    torch.set_num_threads(cv_recipe["maxCpuMathThreads"])
    rows, matrices, cache_evidence = load_train_features(cv_recipe)
    counts = load_rater_counts(rows, cv_recipe["selectedTrainIdsSha256"])
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      cv_recipe["outerFolds"], cv_recipe["outerSeed"])
    require(all(set(fold["holdoutSpeakerIds"]) ==
                {speaker for speaker, assignment in assignments.items() if assignment == fold["fold"]}
                for fold in reference["folds"]), "Outer folds differ from pinned reference")
    permuted_counts, source_indices, permutation = permute_rating_blocks(
        rows, counts, assignments, control["permutationSeed"])
    summary, oof, heads = evaluate(rows, matrices, permuted_counts, cv_recipe)
    require(all(row["fiveRaterCounts"] == permuted_counts[index].tolist()
                for index, row in enumerate(oof)), "Control evaluation did not use permuted labels")
    output.mkdir(parents=True)
    write_json(output / "out-of-fold.json", oof)
    np.savez(output / "outer-fold-heads.npz", **heads)
    provenance = {"experiment": control["experiment"],
                  "recipeSha256": sha256_file(RECIPE),
                  "referenceRecipeSha256": control["referenceRecipeSha256"],
                  "referenceReportSha256": control["referenceReportSha256"],
                  "referenceOutOfFoldSha256": control["referenceOutOfFoldSha256"],
                  "sourceArchiveSha256": cv_recipe["sourceArchiveSha256"],
                  "sourceMetadataSha256": cv_recipe["sourceMetadataSha256"],
                  "cacheEvidence": cache_evidence, "authorPartition": "train",
                  "knownAuthorTest": True, "authorTestUsedForSettings": False,
                  **AUTHORITY}
    write_json(output / "provenance.json", provenance)
    report = {"experiment": control["experiment"], "purpose": control["purpose"],
              "recipeSha256": sha256_file(RECIPE),
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
              "outerFoldHeadsSha256": sha256_file(output / "outer-fold-heads.npz"),
              "permutation": permutation,
              "referencePooledOutOfFold": reference["pooledOutOfFold"],
              "controlPooledOutOfFold": summary["pooledOutOfFold"],
              "controlMinusReference": {
                  name: {metric: summary["pooledOutOfFold"][name][metric] -
                          reference["pooledOutOfFold"][name][metric]
                         for metric in ("perRaterLogLoss", "perRaterBrier")}
                  for name in summary["pooledOutOfFold"]},
              "folds": summary["folds"], "outOfFoldClips": summary["outOfFoldClips"],
              "outOfFoldRaterScores": summary["outOfFoldRaterScores"],
              "outOfFoldSpeakers": summary["outOfFoldSpeakers"],
              "individualRaterScoreCounts": summary["individualRaterScoreCounts"],
              "probabilityBounds": summary["probabilityBounds"],
              "elapsedSeconds": time.perf_counter() - started,
              "interpretation": "One deterministic train-only leakage/sanity control; no p-value, significance test, clinical reliability, or model-winner conclusion.",
              "limitations": [
                  "Singleton equal-size speaker strata retain their original feature-label pairings.",
                  "Many five-rating vectors are identical; a moved source ID need not change its target rating vector.",
                  "The permutation breaks any audio-prompt relationship in a moved block; it cannot isolate phonetic information from prompt or recording cues.",
                  "This one fixed permutation does not estimate a null distribution.",
                  "The same public author-train clips and folds as the reference were reused; this is not external validation."],
              "authorPartition": "train", "knownAuthorTest": True,
              "authorTestUsedForSettings": False, **AUTHORITY}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"permutation": {key: value for key, value in result["permutation"].items()
                                      if key != "strata"},
                      "reference": result["referencePooledOutOfFold"],
                      "control": result["controlPooledOutOfFold"]}))
