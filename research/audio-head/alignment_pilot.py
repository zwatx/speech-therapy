"""Training-only, research-only canonical-phone forced-alignment pilot.

The constrained CTC path is a model hypothesis, not an observed phone boundary.
SpeechOcean ratings and canonical prompts never become produced-phone targets.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import torch

from encoders import WavLMEncoder
from pipeline import edit_distance, greedy_decode, load_head, validate_ctc_length
from speechocean_audit import REVISION, mapping, pinned_bytes, unique_json
from speechocean_r_probe import (ARCHIVE, ARCHIVE_SHA256, AUDIO, CACHE, METADATA, HERE,
                                  read_rating_pcm, sha256_file, verify_selected_archive_audio,
                                  wav_map, write_json)


RECIPE = HERE / "experiments/speechocean-r-alignment-pilot-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-alignment-pilot-v1/report.json"
HEADS = [HERE / f"outputs/cmu-arctic-paired-wavlm-800-headseed{seed}"
         for seed in (7, 17, 29)]
AUTHORITY = {"productionEligible": False, "calibrationEligible": False,
             "learnerFeedbackEligible": False, "clinicalUseEligible": False}
EXPECTED_FLAGS = {"minimumRArgmaxFraction": 0.5, "minimumRMeanPosterior": 0.25,
                  "minimumRDurationSeconds": 0.04, "maximumRDurationSeconds": 0.5,
                  "maximumCenterSpreadSeconds": 0.15, "minimumPairwiseIntervalIou": 0.25}


def validate_recipe(recipe: dict) -> None:
    if (recipe.get("experiment") != "speechocean-r-alignment-pilot-v1" or
            recipe.get("split") != "author train only" or
            recipe.get("sampleCount") != 20 or
            recipe.get("selectionSeed") != 20260923 or
            recipe.get("headSeeds") != [7, 17, 29] or
            recipe.get("headSteps") != 800 or
            recipe.get("flags") != EXPECTED_FLAGS or
            any(recipe.get(key) is not False for key in AUTHORITY)):
        raise ValueError("Unexpected pilot recipe")


def canonical_to_head(phones: list[str], vocabulary: list[str]) -> list[int]:
    """Map the *expected* ARPAbet prompt, never a produced-phone annotation."""
    if not phones or not all(re.fullmatch(r"[A-Z]+[012]?", p) for p in phones):
        raise ValueError("Invalid canonical phones")
    normalized = [re.sub(r"[012]$", "", p).lower() for p in phones]
    missing = sorted(set(normalized) - set(vocabulary[1:]))
    if vocabulary[0] != "<blank>" or missing:
        raise ValueError(f"Canonical phones absent from CTC vocabulary: {missing}")
    return [vocabulary.index(phone) for phone in normalized]


def viterbi_ctc(log_prob: np.ndarray, target: list[int], blank: int = 0) -> tuple[list[int], float]:
    """Max-sum CTC state path for a fixed target, including repeated tokens."""
    if log_prob.ndim != 2 or not len(log_prob) or not np.isfinite(log_prob).all():
        raise ValueError("Expected a finite nonempty [frame, token] log probability matrix")
    if not target or any(type(token) is not int or token == blank or
                         token < 0 or token >= log_prob.shape[1] for token in target):
        raise ValueError("Invalid CTC target")
    validate_ctc_length(target, len(log_prob))
    states = [blank]
    for token in target:
        states.extend((token, blank))
    count = len(states)
    previous = np.full(count, -np.inf, dtype=np.float64)
    previous[0] = log_prob[0, blank]
    previous[1] = log_prob[0, target[0]]
    back = np.full((len(log_prob), count), -1, dtype=np.int32)
    for frame in range(1, len(log_prob)):
        current = np.full(count, -np.inf, dtype=np.float64)
        for state, token in enumerate(states):
            predecessors = [state]
            if state:
                predecessors.append(state - 1)
            if state >= 2 and token != blank and token != states[state - 2]:
                predecessors.append(state - 2)
            winner = max(predecessors, key=lambda source: previous[source])
            if np.isfinite(previous[winner]):
                current[state] = previous[winner] + log_prob[frame, token]
                back[frame, state] = winner
        previous = current
    end = count - 2 if previous[count - 2] >= previous[count - 1] else count - 1
    if not np.isfinite(previous[end]):
        raise ValueError("No valid CTC path despite sufficient frames")
    score = float(previous[end])
    path = [int(end)]
    for frame in range(len(log_prob) - 1, 0, -1):
        path.append(int(back[frame, path[-1]]))
    path.reverse()
    return path, score


def r_interval(path: list[int], r_index: int) -> tuple[int, int]:
    state = 2 * r_index + 1
    occupied = [frame for frame, value in enumerate(path) if value == state]
    if not occupied or occupied != list(range(occupied[0], occupied[-1] + 1)):
        raise ValueError("R state absent or fragmented")
    return occupied[0], occupied[-1] + 1


def interval_iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    overlap = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return overlap / union


def select_train_rows(vocabulary: list[str], count: int, seed: int) -> tuple[list[dict], dict]:
    scores = unique_json(pinned_bytes(METADATA, "resource/scores.json"))
    speakers = mapping(pinned_bytes(METADATA, "train/utt2spk"), r"\d{9}", r"\d{4}")
    wavs = wav_map(AUDIO / "train/wav.scp", speakers, AUDIO)
    candidates = defaultdict(list)
    coverage = Counter()
    for utterance, speaker in sorted(speakers.items()):
        record = scores[utterance]
        phones = [phone for word in record["words"] for phone in word["phones"]]
        if phones.count("R") != 1:
            continue
        coverage["oneRTrain"] += 1
        try:
            target = canonical_to_head(phones, vocabulary)
        except ValueError:
            coverage["unmapped"] += 1
            continue
        coverage["mapped"] += 1
        candidates[speaker].append({"id": utterance, "speaker": speaker,
                                    "split": "train", "audioPath": str(wavs[utterance]),
                                    "text": record["text"], "phones": phones,
                                    "target": target, "rIndex": phones.index("R")})
    if len(candidates) < count:
        raise ValueError("Insufficient distinct train speakers with mappable R")
    ranked_speakers = sorted(candidates, key=lambda speaker: hashlib.sha256(
        f"{seed}:{speaker}".encode()).digest())
    rows = []
    for speaker in ranked_speakers[:count]:
        rows.append(min(candidates[speaker], key=lambda row: hashlib.sha256(
            f"{seed}:{row['id']}".encode()).digest()))
    return rows, dict(coverage)


def diagnose(log_prob: np.ndarray, target: list[int], r_index: int,
             vocabulary: list[str]) -> dict:
    path, score = viterbi_ctc(log_prob, target)
    interval = r_interval(path, r_index)
    r_token = target[r_index]
    frame_prob = np.exp(log_prob[interval[0]:interval[1], r_token])
    decoded = greedy_decode(log_prob.argmax(-1).tolist(), vocabulary)
    expected = [vocabulary[token] for token in target]
    return {"intervalFrames": list(interval), "durationSeconds": (interval[1] - interval[0]) * .02,
            "meanRPosterior": float(frame_prob.mean()),
            "rArgmaxFraction": float(np.mean(log_prob[interval[0]:interval[1]].argmax(-1) == r_token)),
            "greedyPhoneEdits": edit_distance(expected, decoded),
            "canonicalPhoneCount": len(target), "greedyExactSequence": decoded == expected,
            "viterbiLogProbabilityPerFrame": score / len(log_prob)}


def run(output: Path = OUTPUT) -> dict:
    if output.exists():
        raise ValueError("Pilot report already exists")
    recipe = json.loads(RECIPE.read_text())
    validate_recipe(recipe)
    torch.set_num_threads(2)
    heads = [load_head(path) for path in HEADS]
    vocabulary = heads[0][1]["vocabulary"]
    if any(metadata["vocabulary"] != vocabulary or metadata["encoder"] != WavLMEncoder.identity or
           metadata["headInitializationSeed"] != seed or metadata["steps"] != recipe["headSteps"]
           for seed, (_, metadata) in zip(recipe["headSeeds"], heads)):
        raise ValueError("Head vocabulary, encoder, seed, or training steps mismatch")
    if sha256_file(ARCHIVE) != ARCHIVE_SHA256:
        raise ValueError("Official SpeechOcean audio archive SHA-256 mismatch")
    rows, coverage = select_train_rows(vocabulary, recipe["sampleCount"], recipe["selectionSeed"])
    archive_hashes = verify_selected_archive_audio(ARCHIVE, AUDIO, rows)
    encoder = WavLMEncoder(CACHE, allow_download=False)
    flags = recipe["flags"]
    results = []
    for row in rows:
        member = "speechocean762/" + Path(row["audioPath"]).relative_to(AUDIO).as_posix()
        samples = read_rating_pcm(Path(row["audioPath"]), archive_hashes[member])
        with torch.no_grad():
            features = encoder(samples)
        validate_ctc_length(row["target"], len(features))
        analyses = []
        for seed, (head, _) in zip(recipe["headSeeds"], heads):
            log_prob = head(features).log_softmax(-1).detach().numpy().astype(np.float64)
            analyses.append({"headSeed": seed, **diagnose(log_prob, row["target"], row["rIndex"], vocabulary)})
        intervals = [tuple(a["intervalFrames"]) for a in analyses]
        centers = [(start + end) * .01 for start, end in intervals]
        center_spread = max(centers) - min(centers)
        min_iou = min(interval_iou(intervals[i], intervals[j])
                      for i in range(3) for j in range(i + 1, 3))
        reason = []
        if any(a["rArgmaxFraction"] < flags["minimumRArgmaxFraction"] for a in analyses):
            reason.append("low-r-argmax-support")
        if any(a["meanRPosterior"] < flags["minimumRMeanPosterior"] for a in analyses):
            reason.append("low-r-posterior")
        if any(not flags["minimumRDurationSeconds"] <= a["durationSeconds"] <=
               flags["maximumRDurationSeconds"] for a in analyses):
            reason.append("implausible-r-duration")
        if center_spread > flags["maximumCenterSpreadSeconds"]:
            reason.append("unstable-r-center")
        if min_iou < flags["minimumPairwiseIntervalIou"]:
            reason.append("low-r-overlap")
        results.append({"id": row["id"], "speaker": row["speaker"], "text": row["text"],
                        "audioSha256": archive_hashes[member], "canonicalPhoneCount": len(row["target"]),
                        "rPhoneIndex": row["rIndex"], "audioSeconds": len(samples) / 16000,
                        "encoderFrames": len(features), "heads": analyses,
                        "rCenterSpreadSeconds": center_spread, "minimumRIntervalIoU": min_iou,
                        "flags": reason})
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": hashlib.sha256(RECIPE.read_bytes()).hexdigest(),
              "sourceArchiveSha256": ARCHIVE_SHA256, "pinnedMetadataRevision": REVISION,
              "split": "train", "selectedCount": len(results), "selectedSpeakers": len({r["speaker"] for r in results}),
              "candidateCoverage": coverage, "heads": [{"path": str(path.relative_to(HERE)),
                   "checkpointSha256": metadata["checkpointSha256"]}
                   for path, (_, metadata) in zip(HEADS, heads)],
              "encoder": WavLMEncoder.identity, "rows": results,
              "summary": {"anyFlagCount": sum(bool(r["flags"]) for r in results),
                          "flagCounts": dict(Counter(flag for row in results for flag in row["flags"])),
                          "greedyExactAllHeadsCount": sum(all(h["greedyExactSequence"] for h in r["heads"])
                                                          for r in results),
                          "medianCenterSpreadSeconds": float(np.median([r["rCenterSpreadSeconds"] for r in results])),
                          "medianMinimumIntervalIoU": float(np.median([r["minimumRIntervalIoU"] for r in results]))},
              "limitations": ["Forced canonical alignment gives a location even when the learner did not produce /R/.",
                              "No ground-truth phone times are available in SpeechOcean; interval accuracy is unmeasured.",
                              "Heads were trained on CMU Arctic automatic alignments, not SpeechOcean produced phones.",
                              "Stress-stripped ARPAbet spelling does not prove cross-corpus phone equivalence.",
                              "Head agreement and posterior support are internal diagnostics, not calibrated confidence.",
                              "Small deterministic training-side pilot; no published test audio inspected."],
              **AUTHORITY}
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    summary = run(args.output)["summary"]
    print(json.dumps(summary, indent=2, sort_keys=True))
