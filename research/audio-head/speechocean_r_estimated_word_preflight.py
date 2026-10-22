"""Private, label-free integration check for estimated canonical word positions.

The CTC path is a forced model hypothesis. Its intervals and contextual frame
means are not reviewed target boundaries, produced phones, or rating evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
import torch

from alignment_pilot import (EXPECTED_FLAGS, HEADS, canonical_to_head, diagnose,
                             interval_iou, r_interval, viterbi_ctc)
from encoders import WavLMEncoder
from pipeline import load_head, validate_ctc_length
from speechocean_audit import mapping, pinned_bytes
from speechocean_r_annotation_pack import source_rows
from speechocean_r_annotation_sample import (METADATA, OUTPUT as SAMPLE,
                                             require_real_generated_path, sha256_file)
from speechocean_r_frame_cache import (HERE, OUTPUT as FRAME_CACHE, expected_index,
                                       prepared_inputs, validate_existing)
from speechocean_r_label_audit import selected_json_objects


RECIPE = HERE / "experiments/speechocean-r-estimated-word-preflight-v1.json"
RECIPE_SHA256 = "5e12279c9ad9ef346de839669e73d81e9910a306a57fb937200de20bf3f87e39"
OUTPUT = HERE / "outputs/speechocean-r-estimated-word-preflight-v1"
AUTHORITY = {"productionEligible": False, "calibrationEligible": False,
             "learnerFeedbackEligible": False, "clinicalUseEligible": False,
             "trainingEligible": False}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_recipe() -> dict:
    require(sha256_file(RECIPE) == RECIPE_SHA256, "Estimated-word recipe changed")
    recipe = json.loads(RECIPE.read_text())
    require(recipe["experiment"] == "speechocean-r-estimated-word-preflight-v1"
            and recipe["authorPartition"] == "train" and recipe["sampleCount"] == 40
            and recipe["alignmentEncoder"] == "wavlm-base-plus"
            and recipe["poolingEncoder"] == "wav2vec2-base"
            and recipe["headSeeds"] == [7, 17, 29] and recipe["headSteps"] == 800
            and recipe["primaryWordSpanHeadSeed"] == 7
            and recipe["flags"] == EXPECTED_FLAGS
            and all(recipe[key] is False for key in AUTHORITY)
            and recipe["noRatings"] is True and recipe["noFit"] is True
            and recipe["noAccuracyClaim"] is True,
            "Estimated-word recipe has unexpected scope")
    return recipe


def word_state_span(path: list[int], phone_counts: list[int], word_index: int) -> tuple[int, int]:
    """Use the first and last canonical phone states of one word; blanks between remain."""
    require(phone_counts and all(type(count) is int and count > 0 for count in phone_counts)
            and type(word_index) is int and 0 <= word_index < len(phone_counts),
            "Invalid canonical word position")
    require(path and all(type(state) is int and 0 <= state <= 2 * sum(phone_counts)
                         for state in path) and all(a <= b for a, b in zip(path, path[1:])),
            "Invalid monotone CTC state path")
    first_phone = sum(phone_counts[:word_index])
    last_phone = first_phone + phone_counts[word_index] - 1
    first_state, last_state = 2 * first_phone + 1, 2 * last_phone + 1
    starts = [i for i, state in enumerate(path) if state == first_state]
    ends = [i for i, state in enumerate(path) if state == last_state]
    require(starts and ends and starts[0] <= ends[-1], "Target word has no complete phone span")
    return starts[0], ends[-1] + 1


def equal_length_offword(frame_count: int, word: tuple[int, int], clip_id: str) -> tuple[int, int] | None:
    require(type(frame_count) is int and frame_count > 0 and len(word) == 2
            and all(type(value) is int for value in word)
            and 0 <= word[0] < word[1] <= frame_count
            and type(clip_id) is str and len(clip_id) == 16,
            "Invalid off-word geometry")
    length = word[1] - word[0]
    left_room, right_room = word[0], frame_count - word[1]
    if max(left_room, right_room) < length:
        return None
    choose_left = (left_room > right_room or
                   left_room == right_room and hashlib.sha256(clip_id.encode()).digest()[0] % 2 == 0)
    if choose_left:
        return (0, length)
    return (frame_count - length, frame_count)


def require_train_rows(rows: list[dict], train: dict[str, str]) -> None:
    selected_ids = [row["sourceId"] for row in rows]
    require(len(rows) == 40 and len(set(selected_ids)) == 40
            and set(selected_ids) <= set(train)
            and all(train[row["sourceId"]] == row["speakerId"] for row in rows),
            "Sample includes non-train or mismatched speaker")


def load_inputs(recipe: dict) -> tuple[list[dict], dict, dict[str, np.ndarray], dict]:
    require(sha256_file(SAMPLE / "internal-manifest.json") == recipe["sampleManifestSha256"]
            and sha256_file(SAMPLE / "reviewer-queue.json") == recipe["sampleQueueSha256"],
            "Pinned 40-clip sample changed")
    rows, _key = source_rows()  # Rebuild train-only sample; verify each WAV against pinned archive.
    require(len(rows) == 40 and len({row["reviewerId"] for row in rows}) == 40,
            "Expected 40 distinct opaque training clips")
    train = mapping(pinned_bytes(METADATA, "train/utt2spk"), r"\d{9}", r"\d{4}")
    require_train_rows(rows, train)
    _samples, index_rows = prepared_inputs(rows)
    cache_evidence = {}
    caches = {}
    for kind in ("wavlm-base-plus", "wav2vec2-base"):
        directory = FRAME_CACHE / kind
        expected = expected_index(kind, index_rows)
        pin = recipe["frameCacheSha256"][kind]
        require(sha256_file(directory / "index.json") == pin["index"]
                and sha256_file(directory / "frames.npy") == pin["frames"],
                f"Pinned {kind} frame cache changed")
        cache_evidence[kind] = validate_existing(directory, expected)
        caches[kind] = np.load(directory / "frames.npy", mmap_mode="r", allow_pickle=False)
    require(all(row["frameCount"] > 0 for row in index_rows), "Empty cached clip")
    selected_ids = {row["sourceId"] for row in rows}
    scores = selected_json_objects(pinned_bytes(METADATA, "resource/scores.json"), selected_ids)
    for row in rows:
        record = scores[row["sourceId"]]
        require(record["text"] == row["targetPrompt"]
                and record["words"][row["wordIndexZeroBased"]]["text"] == row["targetWord"]
                and record["words"][row["wordIndexZeroBased"]]["phones"][row["phoneIndexWithinWordZeroBased"]] == "R"
                and sum(phone == "R" for word in record["words"] for phone in word["phones"]) == 1,
                "Canonical train prompt differs from pinned sample")
    return rows, scores, caches, {"indexRows": index_rows, "cacheValidation": cache_evidence}


def analyze(rows: list[dict], scores: dict, caches: dict[str, np.ndarray],
            index_rows: list[dict], heads: list[tuple], recipe: dict) -> tuple[dict[str, np.ndarray], list[dict]]:
    vocabulary = heads[0][1]["vocabulary"]
    require(all(metadata["vocabulary"] == vocabulary and metadata["encoder"] == WavLMEncoder.identity
                and metadata["headInitializationSeed"] == seed and metadata["steps"] == 800
                and metadata["checkpointSha256"] == recipe["headCheckpointSha256"][str(seed)]
                for seed, (_, metadata) in zip(recipe["headSeeds"], heads, strict=True)),
            "CTC heads differ from pinned WavLM alignment family")
    estimated_word = np.empty((40, 768), dtype=np.float32)
    full_clip = np.empty((40, 768), dtype=np.float32)
    off_word = []
    off_word_row_indices = []
    output_rows = []
    flags = recipe["flags"]
    for i, (row, geometry) in enumerate(zip(rows, index_rows, strict=True)):
        start = geometry["frameOffset"]
        end = start + geometry["frameCount"]
        align_frames = torch.from_numpy(np.array(caches["wavlm-base-plus"][start:end], copy=True))
        pool_frames = np.asarray(caches["wav2vec2-base"][start:end])
        require(tuple(align_frames.shape) == tuple(pool_frames.shape) == (geometry["frameCount"], 768)
                and np.isfinite(pool_frames).all(), "Paired encoder frame geometry differs")
        record = scores[row["sourceId"]]
        phone_counts = [len(word["phones"]) for word in record["words"]]
        phones = [phone for word in record["words"] for phone in word["phones"]]
        target = canonical_to_head(phones, vocabulary)
        validate_ctc_length(target, geometry["frameCount"])
        r_index = phones.index("R")
        head_rows = []
        for seed, (head, _metadata) in zip(recipe["headSeeds"], heads, strict=True):
            with torch.no_grad():
                log_prob = head(align_frames).log_softmax(-1).numpy().astype(np.float64)
            path, _score = viterbi_ctc(log_prob, target)
            word = word_state_span(path, phone_counts, row["wordIndexZeroBased"])
            r = r_interval(path, r_index)
            require(word[0] <= r[0] < r[1] <= word[1], "Forced R lies outside forced target word")
            diagnostics = diagnose(log_prob, target, r_index, vocabulary)
            head_rows.append({"headSeed": seed, "wordFrames": list(word),
                              "rFrames": list(r), "rArgmaxFraction": diagnostics["rArgmaxFraction"],
                              "meanRPosterior": diagnostics["meanRPosterior"],
                              "rDurationSeconds": diagnostics["durationSeconds"],
                              "greedyExactSequence": diagnostics["greedyExactSequence"]})
        r_intervals = [tuple(item["rFrames"]) for item in head_rows]
        centers = [(a + b) * .01 for a, b in r_intervals]
        min_iou = min(interval_iou(r_intervals[a], r_intervals[b])
                      for a in range(3) for b in range(a + 1, 3))
        reasons = []
        if any(item["rArgmaxFraction"] < flags["minimumRArgmaxFraction"] for item in head_rows):
            reasons.append("low-r-argmax-support")
        if any(item["meanRPosterior"] < flags["minimumRMeanPosterior"] for item in head_rows):
            reasons.append("low-r-posterior")
        if any(not flags["minimumRDurationSeconds"] <= item["rDurationSeconds"] <= flags["maximumRDurationSeconds"]
               for item in head_rows):
            reasons.append("implausible-r-duration")
        if max(centers) - min(centers) > flags["maximumCenterSpreadSeconds"]:
            reasons.append("unstable-r-center")
        if min_iou < flags["minimumPairwiseIntervalIou"]:
            reasons.append("low-r-overlap")
        primary = tuple(head_rows[0]["wordFrames"])
        offword = equal_length_offword(geometry["frameCount"], primary, row["reviewerId"])
        estimated_word[i] = pool_frames[primary[0]:primary[1]].mean(axis=0)
        if offword is not None:
            off_word.append(pool_frames[offword[0]:offword[1]].mean(axis=0))
            off_word_row_indices.append(i)
        full_clip[i] = pool_frames.mean(axis=0)
        require(np.isfinite(estimated_word[i]).all() and np.isfinite(full_clip[i]).all()
                and (offword is None or np.isfinite(off_word[-1]).all()),
                "Nonfinite pooled vector")
        output_rows.append({"clipId": row["reviewerId"], "wavSha256": row["wavSha256"],
                            "frameCount": geometry["frameCount"], "headHypotheses": head_rows,
                            "primaryEstimatedWordFrames": list(primary),
                            "equalLengthOffWordFrames": list(offword) if offword else None,
                            "supportFlags": reasons, "internallyUnsupported": bool(reasons),
                            "wordIntervalVerified": False,
                            "offWordAvailable": offword is not None})
    vectors = {"estimatedWord": estimated_word, "fullClip": full_clip,
               "offWord": np.asarray(off_word, dtype=np.float32).reshape(-1, 768),
               "offWordRowIndices": np.asarray(off_word_row_indices, dtype=np.int32)}
    return vectors, output_rows


def publish_private(output: Path, report: dict, vectors: dict[str, np.ndarray]) -> None:
    require_real_generated_path(output, HERE / "outputs")
    require(not output.exists() and not output.is_symlink(), "Preflight output already exists")
    temporary = Path(tempfile.mkdtemp(prefix=".estimated-word-preflight-", dir=output.parent))
    try:
        temporary.chmod(0o700)
        vector_path = temporary / "vectors.npz"
        descriptor = os.open(vector_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as destination:
            np.savez(destination, **vectors)
            destination.flush()
            os.fsync(destination.fileno())
        report["vectorArraySha256"] = sha256_file(vector_path)
        descriptor = os.open(temporary / "report.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
            destination.flush()
            os.fsync(destination.fileno())
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run(output: Path = OUTPUT) -> dict:
    require(output.parent == OUTPUT.parent
            and output.name.startswith("speechocean-r-estimated-word-preflight-"),
            "Preflight output must be a direct sibling of its private research artifact")
    recipe = load_recipe()
    rows, scores, caches, evidence = load_inputs(recipe)
    torch.set_num_threads(2)
    heads = [load_head(path) for path in HEADS]
    vectors, analyzed = analyze(rows, scores, caches, evidence["indexRows"], heads, recipe)
    require(len(analyzed) == 40 and vectors["estimatedWord"].shape == (40, 768)
            and vectors["fullClip"].shape == (40, 768)
            and vectors["offWord"].shape == (len(vectors["offWordRowIndices"]), 768),
            "Incomplete preflight")
    report = {"schemaVersion": 1, "experiment": recipe["experiment"],
              "purpose": recipe["purpose"], "authorPartition": "train",
              "recipeSha256": RECIPE_SHA256, "sourceArchiveSha256": recipe["sourceArchiveSha256"],
              "sampleManifestSha256": recipe["sampleManifestSha256"],
              "sampleQueueSha256": recipe["sampleQueueSha256"],
              "frameCacheSha256": recipe["frameCacheSha256"],
              "sourceCodeSha256": {name: sha256_file(HERE / name) for name in
                                   ("speechocean_r_estimated_word_preflight.py", "alignment_pilot.py",
                                    "speechocean_r_frame_cache.py", "target_pool.py")},
              "headCheckpoints": [{"seed": seed, "checkpointSha256": metadata["checkpointSha256"]}
                                  for seed, (_, metadata) in zip(recipe["headSeeds"], heads, strict=True)],
              "vectorShapes": {name: list(array.shape) for name, array in vectors.items()},
              "vectorRows": "estimatedWord and fullClip follow report rows; offWord follows offWordRowIndices only",
              "rows": analyzed,
              "summary": {"clips": 40, "wordHypotheses": 40,
                          "offWordAvailable": sum(row["offWordAvailable"] for row in analyzed),
                          "offWordUnavailable": sum(not row["offWordAvailable"] for row in analyzed),
                          "flaggedClips": sum(bool(row["supportFlags"]) for row in analyzed),
                          "internallyUnsupported": sum(row["internallyUnsupported"] for row in analyzed),
                          "flagCounts": dict(Counter(flag for row in analyzed for flag in row["supportFlags"]))},
              "limitations": ["Canonical CTC word spans are forced hypotheses, including when the word or R was omitted.",
                              "The three CMU Arctic heads share automatic-label training; agreement is not independent timing evidence.",
                              "Wav2vec2 positions are contextual and can attend to audio outside the selected frame span.",
                              "A geometric off-word edge window may contain leading or trailing silence, so it is not a matched acoustic control.",
                              "The 40-clip sample was rating-balanced for an annotation pilot, not population-representative.",
                              "No ratings were used for a fit or written to this artifact; no localization accuracy was measured."],
              "ratingsUsedForFit": False, "fitPerformed": False, "accuracyMeasured": False,
              "reviewerPacksModified": False, **AUTHORITY}
    publish_private(output, report, vectors)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.output)["summary"], indent=2, sort_keys=True))
