"""Research-only SpeechOcean762 /R/ utterance rating probe.

Canonical phones locate one scored /R/ position. They are never produced-phone
labels or CTC targets. All audio is public corpus audio, read at full duration.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time
import wave

import numpy as np
import torch

from encoders import Wav2VecEncoder, WavLMEncoder
from speechocean_audit import FILES, REVISION, mapping, pinned_bytes, unique_json, validate_scores


HERE = Path(__file__).resolve().parent
METADATA = HERE / "outputs/speechocean762-metadata-v1"
AUDIO = HERE / "outputs/speechocean762-audio-v1/speechocean762"
ARCHIVE = AUDIO.parent / "speechocean762.tar.gz"
OUTPUT = HERE / "outputs/speechocean-r-probe-v2"
WAVLM_OUTPUT = HERE / "outputs/speechocean-r-probe-wavlm-v1"
WAVLM_RECIPE = HERE / "experiments/speechocean-r-wavlm-v1.json"
CACHE = HERE / "outputs/model-cache"
ARCHIVE_SHA256 = "876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5"
SEED = 20260923
VAL_SPEAKERS = 25
RIDGE_ALPHAS = (1.0, 10.0, 100.0, 1000.0)
SMOOTHING = (1.0, 5.0, 20.0)
MAX_SECONDS = 30
RECIPE_VERSION = "one-r-full-clip-frozen-wav2vec2-meanpool-ridge-v2"
WAVLM_RECIPE_VERSION = "one-r-full-clip-frozen-wavlm-meanpool-ridge-v1"
AUTHORITY = {"productionEligible": False, "calibrationEligible": False,
             "learnerFeedbackEligible": False, "clinicalUseEligible": False}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: dict | list) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def load_wavlm_recipe(path: Path = WAVLM_RECIPE) -> dict:
    require(path.resolve() == WAVLM_RECIPE.resolve(), "WavLM recipe path differs from predeclared experiment")
    recipe = unique_json(path.read_bytes())
    require(recipe.get("experiment") == "speechocean-r-wavlm-v1" and
            recipe.get("knownHoldout") is True and recipe.get("confirmatory") is False and
            recipe.get("encoderKind") == "wavlm-base-plus" and
            recipe.get("encoderRevision") == WavLMEncoder.identity["revision"] and
            recipe.get("recipeVersion") == WAVLM_RECIPE_VERSION and
            recipe.get("outputDirectory") == "outputs/speechocean-r-probe-wavlm-v1" and
            recipe.get("validationSeed") == SEED and
            recipe.get("validationSpeakerCount") == VAL_SPEAKERS and
            recipe.get("ridgeAlphas") == list(RIDGE_ALPHAS) and
            recipe.get("baselineSmoothing") == list(SMOOTHING) and
            recipe.get("selectionMetric") == "validation MAE; lowest alpha breaks ties" and
            all(recipe.get(key) is False for key in AUTHORITY),
            "WavLM recipe differs from predeclared comparison")
    reference = recipe.get("reference")
    require(type(reference) is dict and
            reference.get("report") == "outputs/speechocean-r-probe-v2/report.json" and
            reference.get("encoderKind") == Wav2VecEncoder.identity["kind"],
            "WavLM reference report differs from predeclaration")
    report_path = HERE / reference["report"]
    require(sha256_file(report_path) == reference.get("reportSha256"),
            "Predeclared wav2vec reference report SHA-256 mismatch")
    report = unique_json(report_path.read_bytes())
    require(report.get("headSha256") == reference.get("headSha256") and
            report.get("encoder") == Wav2VecEncoder.identity and
            report["test"]["audioRidge"]["mae"] == reference.get("testAudioRidgeMaE") and
            report["test"]["audioRidge"]["mse"] == reference.get("testAudioRidgeMse") and
            report["test"]["trainMean"]["mae"] == reference.get("testTrainMeanMaE") and
            report["test"]["trainMean"]["mse"] == reference.get("testTrainMeanMse") and
            report["test"]["targetWord"]["mae"] == reference.get("testTargetWordMaE") and
            report["test"]["constantTwo"]["mae"] == reference.get("testConstantTwoMaE"),
            "Predeclared wav2vec reference metrics differ from report")
    return recipe


def selected_r(row: dict) -> tuple[str, float] | None:
    positions = [(word["text"], float(score))
                 for word in row["words"]
                 for phone, score in zip(word["phones"], word["phones-accuracy"])
                 if phone == "R"]
    return positions[0] if len(positions) == 1 else None


def wav_map(path: Path, expected: dict[str, str], audio_root: Path) -> dict[str, Path]:
    result = {}
    for line in path.read_text().splitlines():
        columns = line.split()
        require(len(columns) == 2, "Invalid wav.scp row")
        utterance, relative = columns
        require(utterance in expected and utterance not in result, "Unexpected or duplicate WAV ID")
        require(relative == f"WAVE/SPEAKER{expected[utterance]}/{utterance}.WAV",
                "WAV path differs from speaker map")
        actual = audio_root / relative
        require(actual.is_file() and actual.resolve().is_relative_to(audio_root.resolve()),
                "WAV missing or outside corpus")
        result[utterance] = actual
    require(set(result) == set(expected), "WAV mapping does not cover speaker map")
    return result


def verify_selected_archive_audio(archive: Path, audio_root: Path, rows: list[dict]) -> dict[str, str]:
    """Bind every selected extracted WAV to the hash-pinned archive member."""
    expected = {}
    for row in rows:
        path = Path(row["audioPath"])
        relative = path.relative_to(audio_root)
        member = "speechocean762/" + relative.as_posix()
        require(member not in expected, "Selected archive member repeated")
        expected[member] = sha256_file(path)
    found = {}
    with tarfile.open(archive, mode="r|gz") as source:
        for member in source:
            if member.name not in expected:
                continue
            require(member.isfile() and member.name not in found, "Duplicate or non-file selected archive member")
            payload = source.extractfile(member)
            require(payload is not None, "Selected archive member unreadable")
            hasher = hashlib.sha256()
            for block in iter(lambda: payload.read(1024 * 1024), b""):
                hasher.update(block)
            found[member.name] = hasher.hexdigest()
            require(found[member.name] == expected[member.name],
                    f"Extracted WAV differs from pinned archive: {member.name}")
    require(set(found) == set(expected), "Selected WAV missing from pinned archive")
    return expected


def prepare_rows(metadata: Path = METADATA, audio: Path = AUDIO,
                 archive: Path = ARCHIVE) -> tuple[list[dict], dict]:
    require(sha256_file(archive) == ARCHIVE_SHA256, "Official audio archive SHA-256 mismatch")
    pinned = {name: pinned_bytes(metadata, name) for name in FILES}
    scores = unique_json(pinned["resource/scores.json"])
    detail = unique_json(pinned["resource/scores-detail.json"])
    for name in ("resource/scores-detail.json", "train/utt2spk", "test/utt2spk"):
        require((audio / name).read_bytes() == pinned[name],
                f"Audio archive metadata differs from pinned author file: {name}")
    archive_scores = unique_json((audio / "resource/scores.json").read_bytes())
    require(set(archive_scores) == set(scores), "Audio archive score IDs differ from pinned author scores")
    selective_note_utterances = 0
    selective_note_words = 0
    for utterance in scores:
        canonical = scores[utterance]
        archived = archive_scores[utterance]
        canonical_without_notes = {**canonical, "words": [
            {key: value for key, value in word.items() if key != "mispronunciations"}
            for word in canonical["words"]]}
        archived_without_notes = {**archived, "words": [
            {key: value for key, value in word.items() if key != "mispronunciations"}
            for word in archived["words"]]}
        require(canonical_without_notes == archived_without_notes,
                "Archive and author aggregate ratings or prompts differ")
        different = sum(a.get("mispronunciations") != b.get("mispronunciations")
                        for a, b in zip(canonical["words"], archived["words"]))
        selective_note_words += different
        selective_note_utterances += different > 0
    splits = {split: mapping(pinned[f"{split}/utt2spk"], r"\d{9}", r"\d{4}")
              for split in ("train", "test")}
    ages = {split: mapping(pinned[f"{split}/spk2age"], r"\d{4}", r"\d{1,3}")
            for split in ("train", "test")}
    genders = {split: mapping(pinned[f"{split}/spk2gender"], r"\d{4}", r"[mf]")
               for split in ("train", "test")}
    rating_audit = validate_scores(scores, detail, splits, ages, genders)
    require(set(splits["train"]) | set(splits["test"]) == set(scores) == set(detail),
            "Score IDs differ from author split maps")
    require(not set(splits["train"]).intersection(splits["test"]), "Utterance split overlap")
    require(not set(splits["train"].values()).intersection(splits["test"].values()),
            "Speaker split overlap")
    require(all(set(ages[split]) == set(splits[split].values()) for split in splits),
            "Speaker age map differs from split")
    rows = []
    all_maps = {split: wav_map(audio / split / "wav.scp", speakers, audio)
                for split, speakers in splits.items()}
    for split in ("train", "test"):
        for utterance, speaker in sorted(splits[split].items()):
            row = scores[utterance]
            selection = selected_r(row)
            if selection is None:
                continue
            word, score = selection
            require(0 <= score <= 2 and abs(score * 5 - round(score * 5)) < 1e-8,
                    "Expected five-rater aggregate 0–2 score")
            rows.append({"id": utterance, "split": split, "speaker": speaker,
                         "age": int(ages[split][speaker]),
                         "text": row["text"], "targetWord": word, "rating": score,
                         "audioPath": str(all_maps[split][utterance])})
    require(sum(r["split"] == "train" for r in rows) == 766 and
            sum(r["split"] == "test" for r in rows) == 759,
            "One-/R/ selection count changed")
    archive_hashes = verify_selected_archive_audio(archive, audio, rows)
    for row in rows:
        member = "speechocean762/" + Path(row["audioPath"]).relative_to(audio).as_posix()
        row["audioSha256"] = archive_hashes[member]
    provenance = {"corpus": "SpeechOcean762", "corpusHomepage": "https://openslr.org/101/",
                  "corpusLicense": "CC BY 4.0", "audioArchiveSha256": ARCHIVE_SHA256,
                  "authorMetadataRevision": REVISION,
                  "authorMetadataSha256": {name: expected for name, (_, expected) in FILES.items()},
                  "ratingAudit": {"validatedUtterances": rating_audit["utterances"],
                                  "validatedCanonicalPhonePositions": rating_audit["canonicalPhonePositions"]},
                  "archiveVsPinnedAuthorScores": {"onlySelectiveMispronunciationNotesDiffer": True,
                                                   "utterances": selective_note_utterances,
                                                   "words": selective_note_words,
                                                   "allRatingsAndPromptsMatch": True},
                  "selection": "Exactly one canonical R; its five-rater aggregate phone score is a continuous 0–2 label",
                  "excluded": "Zero or multiple canonical R positions",
                  "speakerSplit": "Published disjoint author train/test; 25 train speakers reserved for tuning",
                  "validationSeed": SEED, "ridgeAlphas": RIDGE_ALPHAS,
                  "baselineSmoothing": SMOOTHING,
                  "descriptiveAgeBands": {"child": "age <= 15", "adult": "age >= 19"},
                  "audio": "Full mono PCM16 16 kHz WAV, maximum allowed duration 30 seconds; no truncation",
                  "selectedWavCountBoundToPinnedArchive": len(archive_hashes),
                  "featureRecipeVersion": RECIPE_VERSION,
                  **AUTHORITY}
    return rows, provenance


def read_rating_pcm(path: Path, expected_sha256: str | None = None) -> torch.Tensor:
    require(path.stat().st_size <= 2_000_000, "WAV exceeds bounded reader size")
    data = path.read_bytes()
    if expected_sha256 is not None:
        require(hashlib.sha256(data).hexdigest() == expected_sha256,
                "WAV changed after archive verification")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            require((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype())
                    == (1, 2, 16000, "NONE"), "Expected mono PCM16 16 kHz WAV")
            frames = wav.getnframes()
            require(1600 <= frames <= MAX_SECONDS * 16000, "WAV duration outside 0.1–30 seconds")
            payload = wav.readframes(frames)
            require(len(payload) == 2 * frames, "Truncated WAV")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Malformed WAV") from exc
    return torch.from_numpy(np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.0)


def validation_partition(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    train = [i for i, row in enumerate(rows) if row["split"] == "train"]
    test = np.asarray([i for i, row in enumerate(rows) if row["split"] == "test"], dtype=int)
    speakers = sorted({rows[i]["speaker"] for i in train},
                      key=lambda speaker: hashlib.sha256(f"{SEED}:{speaker}".encode()).hexdigest())
    require(len(speakers) == 124, "Unexpected one-/R/ train speaker count")
    validation_speakers = set(speakers[:VAL_SPEAKERS])
    fit = np.asarray([i for i in train if rows[i]["speaker"] not in validation_speakers], dtype=int)
    validation = np.asarray([i for i in train if rows[i]["speaker"] in validation_speakers], dtype=int)
    require(not {rows[i]["speaker"] for i in fit}.intersection(
        {rows[i]["speaker"] for i in validation}), "Validation speaker overlap")
    return fit, validation, test


def metrics(prediction: np.ndarray, truth: np.ndarray) -> dict:
    delta = prediction - truth
    return {"mae": float(np.mean(np.abs(delta))), "mse": float(np.mean(delta ** 2))}


def rating_baseline(fit_rows: list[dict], fit_y: np.ndarray,
                    predict_rows: list[dict], smoothing: float, key: str) -> np.ndarray:
    overall = float(np.mean(fit_y))
    groups: dict[str, list[float]] = defaultdict(list)
    for row, y in zip(fit_rows, fit_y):
        groups[row[key]].append(float(y))
    return np.asarray([(sum(groups[row[key]]) + smoothing * overall) /
                       (len(groups[row[key]]) + smoothing) for row in predict_rows])


def transcript_word_baseline(fit_rows: list[dict], fit_y: np.ndarray,
                             predict_rows: list[dict], smoothing: float) -> np.ndarray:
    word = rating_baseline(fit_rows, fit_y, predict_rows, smoothing, "targetWord")
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row, y in zip(fit_rows, fit_y):
        groups[(row["text"], row["targetWord"])].append(float(y))
    return np.asarray([(sum(groups[(row["text"], row["targetWord"])]) + smoothing * fallback) /
                       (len(groups[(row["text"], row["targetWord"])]) + smoothing)
                       for row, fallback in zip(predict_rows, word)])


def fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale = np.where(scale < 1e-6, 1.0, scale)
    normalized = (x - mean) / scale
    target_mean = float(y.mean())
    gram = normalized.T @ normalized
    gram.flat[::gram.shape[0] + 1] += alpha
    weights = np.linalg.solve(gram, normalized.T @ (y - target_mean))
    return {"featureMean": mean, "featureScale": scale,
            "weights": weights, "intercept": target_mean}


def predict_ridge(head: dict, x: np.ndarray) -> np.ndarray:
    return ((x - head["featureMean"]) / head["featureScale"]) @ head["weights"] + head["intercept"]


def extract_features(rows: list[dict], output: Path, cache: Path,
                     encoder_kind: str = "wav2vec2-base") -> tuple[np.ndarray, dict]:
    require(encoder_kind in ("wav2vec2-base", "wavlm-base-plus"), "Unsupported rating probe encoder")
    encoder_class = WavLMEncoder if encoder_kind == "wavlm-base-plus" else Wav2VecEncoder
    recipe_version = WAVLM_RECIPE_VERSION if encoder_kind == "wavlm-base-plus" else RECIPE_VERSION
    index = {"recipeVersion": recipe_version, "encoder": encoder_class.identity,
             "sourceArchiveSha256": ARCHIVE_SHA256,
             "rows": [{key: row[key] for key in ("id", "split", "speaker", "audioPath", "audioSha256", "rating")}
                      for row in rows]}
    index_path = output / "feature-index.json"
    progress_path = output / "feature-progress.json"
    feature_path = output / "features.npy"
    if index_path.exists():
        require(json.loads(index_path.read_text()) == index, "Feature cache index changed")
        features = np.lib.format.open_memmap(feature_path, mode="r+")
        require(features.shape == (len(rows), 768), "Feature cache shape changed")
        progress = json.loads(progress_path.read_text())
        completed = progress["completed"]
        require(type(completed) is int and 0 <= completed <= len(rows), "Invalid feature progress")
        require(progress["featureArraySha256"] == sha256_file(feature_path),
                "Feature cache bytes differ from recorded SHA-256")
        require(progress["featureIndexSha256"] == sha256_file(index_path),
                "Feature cache index differs from recorded SHA-256")
    else:
        require(not feature_path.exists() and not progress_path.exists(), "Partial feature cache without index")
        write_json(index_path, index)
        features = np.lib.format.open_memmap(feature_path, mode="w+", dtype="float32",
                                             shape=(len(rows), 768))
        completed = 0
        features.flush()
        write_json(progress_path, {"completed": completed,
                                   "featureArraySha256": sha256_file(feature_path),
                                   "featureIndexSha256": sha256_file(index_path)})
    if completed == len(rows):
        birth = getattr(feature_path.stat(), "st_birthtime", None)
        elapsed = (progress_path.stat().st_mtime - birth) if birth is not None else None
        evidence = {"encodedClips": len(rows), "resumedAt": completed,
                    "featureArraySha256": sha256_file(feature_path),
                    "featureIndexSha256": sha256_file(index_path),
                    "initialFeaturePassWallSecondsFromFileTimestamps": elapsed,
                    "timingBasis": "Feature array creation to final atomic progress write; includes pinned encoder load"}
        prior_report = output / "report.json"
        if prior_report.exists():
            previous = json.loads(prior_report.read_text()).get("featureExtraction", {})
            if previous.get("featureArraySha256") == evidence["featureArraySha256"]:
                prior_seconds = previous.get("extractionSecondsThisRun")
                if type(prior_seconds) in (int, float) and prior_seconds > 0:
                    evidence["initialExtractionSecondsMeasured"] = prior_seconds
        return features, evidence
    encoder = encoder_class(cache, allow_download=False)
    started = time.perf_counter()
    for index_number in range(completed, len(rows)):
        row = rows[index_number]
        samples = read_rating_pcm(Path(row["audioPath"]), row["audioSha256"])
        pooled = encoder(samples).mean(dim=0).numpy()
        require(pooled.shape == (768,) and np.isfinite(pooled).all(), "Invalid pooled encoder feature")
        features[index_number] = pooled
        if (index_number + 1) % 10 == 0 or index_number + 1 == len(rows):
            features.flush()
            write_json(progress_path, {"completed": index_number + 1,
                                       "featureArraySha256": sha256_file(feature_path),
                                       "featureIndexSha256": sha256_file(index_path)})
        if (index_number + 1) % 50 == 0:
            print(f"Encoded {index_number + 1}/{len(rows)} clips in {time.perf_counter()-started:.1f}s", flush=True)
    return features, {"encodedClips": len(rows), "resumedAt": completed,
                      "featureArraySha256": sha256_file(feature_path),
                      "featureIndexSha256": sha256_file(index_path),
                      "extractionSecondsThisRun": time.perf_counter() - started}


def run(output: Path = OUTPUT, metadata: Path = METADATA, audio: Path = AUDIO,
        archive: Path = ARCHIVE, cache: Path = CACHE,
        encoder_kind: str = "wav2vec2-base") -> dict:
    require(encoder_kind in ("wav2vec2-base", "wavlm-base-plus"), "Unsupported rating probe encoder")
    recipe = load_wavlm_recipe() if encoder_kind == "wavlm-base-plus" else None
    if recipe is not None:
        require(output.resolve() == WAVLM_OUTPUT.resolve(), "WavLM output differs from predeclared directory")
    encoder_class = WavLMEncoder if recipe is not None else Wav2VecEncoder
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    rows, provenance = prepare_rows(metadata, audio, archive)
    if recipe is not None:
        provenance.update({"encoder": encoder_class.identity,
                           "featureRecipeVersion": WAVLM_RECIPE_VERSION,
                           "recipeSha256": sha256_file(WAVLM_RECIPE),
                           "predeclaredReference": recipe["reference"],
                           "knownHoldout": True, "confirmatory": False})
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "provenance.json", provenance)
    features, extraction = extract_features(rows, output, cache, encoder_kind)
    x = np.asarray(features, dtype=np.float64)
    y = np.asarray([r["rating"] for r in rows], dtype=np.float64)
    fit, val, test = validation_partition(rows)
    train = np.asarray([i for i, r in enumerate(rows) if r["split"] == "train"], dtype=int)
    ridge_trials = []
    for alpha in RIDGE_ALPHAS:
        head = fit_ridge(x[fit], y[fit], alpha)
        ridge_trials.append({"alpha": alpha, **metrics(predict_ridge(head, x[val]), y[val])})
    alpha = min(ridge_trials, key=lambda row: (row["mae"], row["alpha"]))["alpha"]
    baseline_trials = {}
    for name, baseline in (("targetWord", lambda a, b, c, s: rating_baseline(a, b, c, s, "targetWord")),
                           ("transcriptAndTargetWord", transcript_word_baseline)):
        trials = [{"smoothing": s, **metrics(baseline([rows[i] for i in fit], y[fit],
                                                    [rows[i] for i in val], s), y[val])}
                  for s in SMOOTHING]
        baseline_trials[name] = trials
    selected_smoothing = {name: min(trials, key=lambda row: (row["mae"], row["smoothing"]))["smoothing"]
                          for name, trials in baseline_trials.items()}
    final = fit_ridge(x[train], y[train], alpha)
    prediction = predict_ridge(final, x[test])
    np.savez(output / "rating-head.npz", weights=final["weights"],
             feature_mean=final["featureMean"], feature_scale=final["featureScale"],
             intercept=np.asarray(final["intercept"]), alpha=np.asarray(alpha))
    train_rows = [rows[i] for i in train]
    test_rows = [rows[i] for i in test]
    repeated_prompts = set(row["text"] for row in train_rows) & set(row["text"] for row in test_rows)
    test_baselines = {"trainMean": metrics(np.full(len(test), y[train].mean()), y[test]),
                      "constantTwo": metrics(np.full(len(test), 2.0), y[test])}
    for name, baseline in (("targetWord", lambda a, b, c, s: rating_baseline(a, b, c, s, "targetWord")),
                           ("transcriptAndTargetWord", transcript_word_baseline)):
        test_baselines[name] = metrics(baseline(train_rows, y[train], test_rows,
                                               selected_smoothing[name]), y[test])
    age_bands = {}
    for name, keep in (("childAgeAtMost15", lambda age: age <= 15),
                       ("adultAgeAtLeast19", lambda age: age >= 19)):
        positions = np.asarray([index for index, row in enumerate(test_rows) if keep(row["age"])], dtype=int)
        require(len(positions) > 0, "Empty descriptive age band")
        age_bands[name] = {"count": len(positions),
                           "audioRidge": metrics(prediction[positions], y[test][positions]),
                           "trainMean": metrics(np.full(len(positions), y[train].mean()), y[test][positions]),
                           "constantTwo": metrics(np.full(len(positions), 2.0), y[test][positions])}
    require(sum(band["count"] for band in age_bands.values()) == len(test),
            "Age bands do not cover test selection")
    report = {"purpose": "research-only continuous utterance-level /R/ rating probe",
              "labelSource": "SpeechOcean762 five-rater aggregate phone rating",
              "encoder": encoder_class.identity,
              **({"featureRecipeVersion": WAVLM_RECIPE_VERSION} if recipe is not None else {}),
              "pooling": "arithmetic mean of all frozen encoder frames over full clip",
              "head": "standardized linear ridge regression with unpenalized intercept",
              "trainCount": len(train), "validationCount": len(val), "testCount": len(test),
              "trainSpeakerCount": len({rows[i]["speaker"] for i in train}),
              "fitSpeakerCount": len({rows[i]["speaker"] for i in fit}),
              "validationSpeakerCount": len({rows[i]["speaker"] for i in val}),
              "testSpeakerCount": len({rows[i]["speaker"] for i in test}),
              "ridgeValidationTrials": ridge_trials,
              "baselineValidationTrials": baseline_trials,
              "selectedAlpha": alpha, "selectedSmoothing": selected_smoothing,
              "test": {"audioRidge": metrics(prediction, y[test]), **test_baselines},
              "interpretation": (recipe["interpretation"] if recipe is not None else
                                 "Exploratory known-holdout result: only a small change from train mean, worse MAE than target-word and constant-2 baselines; no meaningful gain over strong baselines."),
              "descriptiveHeldOutAgeBands": age_bands,
              "ratingRange": [0, 2], "clippedPredictions": False,
              "testPredictionRange": [float(prediction.min()), float(prediction.max())],
              "testPredictionsOutsideRatingRange": int(np.count_nonzero((prediction < 0) | (prediction > 2))),
              "exactPromptsSharedAcrossPublishedSplits": len(repeated_prompts),
              "headSha256": sha256_file(output / "rating-head.npz"),
              "featureExtraction": extraction,
              **({"predeclaredRecipeSha256": sha256_file(WAVLM_RECIPE),
                  "referenceWav2vec": recipe["reference"],
                  "knownHoldout": True, "confirmatory": False} if recipe is not None else {}),
              "limitations": ["Only one canonical /R/ position per utterance; utterance pooling cannot isolate its acoustic interval.",
                              "Five-rater pronunciation scores are subjective weak supervision, not verified produced phones.",
                              "Published speaker separation does not establish household or recording-condition independence.",
                              "Some exact prompts repeat across published splits, so text and target-word effects can transfer to test.",
                              "The author test score distribution and simple baselines were inspected before this recipe; this is an exploratory known holdout, not a blind confirmatory test.",
                              "English learner corpus and rating scale do not establish clinical validity or individual feedback calibration."],
              **AUTHORITY}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", choices=("wav2vec2-base", "wavlm-base-plus"), default="wav2vec2-base")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or (WAVLM_OUTPUT if args.encoder == "wavlm-base-plus" else OUTPUT)
    print(json.dumps(run(output=destination, encoder_kind=args.encoder), indent=2))
