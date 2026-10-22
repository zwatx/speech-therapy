"""Offline research replay of a locked whole-clip SpeechOcean /R/ rater head.

Only exact public author-training WAVs in the pinned feature index are accepted.
The probabilities describe subjective corpus rating classes, not produced /R/.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

import speechocean_r_rater_cv as trainer
import speechocean_r_rater_final_fit as final_fit
from speechocean_r_probe import AUDIO, CACHE, HERE, read_rating_pcm, sha256_file
from speechocean_r_rater_cv import predict_softmax
from speechocean_r_rater_final_fit import load_recipe
from speechocean_train_cv import ENCODERS

OUTPUT = HERE / "outputs/speechocean-r-rater-final-fit-v1"
REPORT_SHA256 = "e7647c98e0c8ee4a88334aab68b60b20dea551cd82ed9872b74ecc7b5087476e"
PROVENANCE_SHA256 = "b4c60bcd24633b59555750ccd0022e8873af06990abaa7fa43b169596d32853a"
FALSE_FLAGS = ("productionEligible", "calibrationEligible", "learnerFeedbackEligible",
               "clinicalUseEligible", "clinicalReliabilityEstablished")
FIELDS = ("featureMean", "featureScale", "weights", "intercept", "alpha")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def verified_head(kind: str, recipe: dict, output: Path = OUTPUT) -> dict:
    require(kind in ENCODERS, "Unsupported frozen encoder")
    report_path, provenance_path, heads_path = (output / name for name in
                                                 ("report.json", "provenance.json", "heads.npz"))
    require(sha256_file(report_path) == REPORT_SHA256 and
            sha256_file(provenance_path) == PROVENANCE_SHA256,
            "Locked final-fit report or provenance SHA-256 mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    require(report.get("headsSha256") == sha256_file(heads_path) and
            report.get("provenanceSha256") == PROVENANCE_SHA256 and
            report.get("recipeSha256") == sha256_file(HERE / "experiments/speechocean-r-rater-final-fit-v1.json") and
            provenance.get("recipeSha256") == report["recipeSha256"] and
            provenance.get("sourceArchiveSha256") == recipe["sourceArchiveSha256"] and
            provenance.get("selectedTrainIdsSha256") == recipe["selectedTrainIdsSha256"] and
            provenance.get("trainerSha256") == sha256_file(Path(trainer.__file__)) and
            provenance.get("finalFitCodeSha256") == sha256_file(Path(final_fit.__file__)) and
            report.get("experiment") == recipe["experiment"] and
            provenance.get("experiment") == recipe["experiment"] and
            report.get("authorPartition") == provenance.get("authorPartition") == "train" and
            all(report.get(flag) is False and provenance.get(flag) is False
                for flag in FALSE_FLAGS),
            "Final-fit head or research provenance mismatch")
    pin = recipe["inputs"][kind]
    require(provenance.get("cacheEvidence", {}).get(kind) ==
            {"directory": pin["directory"], "encoder": ENCODERS[kind].identity,
             "recipeVersion": pin["recipeVersion"],
             "featureIndexSha256": pin["featureIndexSha256"],
             "featureProgressSha256": pin["featureProgressSha256"],
             "featureArraySha256": pin["featureArraySha256"]} and
            report.get("fixedAlpha", {}).get(kind) == recipe["fixedSoftmaxL2"][kind],
            "Final-fit encoder or feature preprocessing mismatch")
    with np.load(heads_path, allow_pickle=False) as arrays:
        require(set(arrays.files) == {f"{name}_{field}" for name in ENCODERS
                                            for field in FIELDS},
                "Unexpected final-fit head arrays")
        head = {field: np.asarray(arrays[f"{kind}_{field}"]).copy() for field in FIELDS}
    width = ENCODERS[kind].identity["width"]
    require(all(value.dtype == np.dtype("float64") and np.isfinite(value).all()
                for value in head.values()) and
            head["featureMean"].shape == (width,) and
            head["featureScale"].shape == (width,) and
            np.all(head["featureScale"] > 0) and
            head["weights"].shape == (width, 3) and
            head["intercept"].shape == (3,) and
            head["alpha"].shape == () and
            float(head["alpha"]) == recipe["fixedSoftmaxL2"][kind],
            "Final-fit head shape, scale, or alpha mismatch")
    return head


def verified_public_train_row(audio: Path, kind: str, recipe: dict) -> dict:
    require(audio.is_file() and audio.stat().st_size <= 2_000_000 and
            audio.suffix.lower() == ".wav" and
            audio.resolve().is_relative_to((AUDIO / "WAVE").resolve()),
            "Only local pinned public SpeechOcean WAVs are accepted")
    pin = recipe["inputs"][kind]
    index_path = HERE / pin["directory"] / "feature-index.json"
    require(sha256_file(index_path) == pin["featureIndexSha256"],
            "Pinned feature index SHA-256 mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    require(index.get("encoder") == ENCODERS[kind].identity and
            index.get("recipeVersion") == pin["recipeVersion"] and
            index.get("sourceArchiveSha256") == recipe["sourceArchiveSha256"] and
            type(index.get("rows")) is list,
            "Feature index encoder or preprocessing mismatch")
    matches = [row for row in index["rows"] if row.get("split") == "train" and
               Path(row.get("audioPath", "")).resolve() == audio.resolve()]
    require(len(matches) == 1, "WAV is not one selected public author-training clip")
    row = matches[0]
    require(set(row) == {"id", "split", "speaker", "audioPath", "audioSha256", "rating"} and
            sha256_file(audio) == row["audioSha256"],
            "Public author-training WAV identity or SHA-256 mismatch")
    return row


def infer(audio: Path, kind: str = "wav2vec2-base") -> dict:
    recipe = load_recipe()
    head = verified_head(kind, recipe)
    row = verified_public_train_row(audio, kind, recipe)
    samples = read_rating_pcm(audio, row["audioSha256"])
    # Encoder constructor checks all three pinned upstream files. Offline mode is
    # explicit as well as local_files_only=True inside the encoder implementation.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    encoder = ENCODERS[kind](CACHE, allow_download=False)
    require(encoder.identity == ENCODERS[kind].identity,
            "Loaded encoder differs from pinned final-fit identity")
    pooled = encoder(samples).mean(dim=0).numpy().astype(np.float32).astype(np.float64)
    require(pooled.shape == (ENCODERS[kind].identity["width"],) and
            np.isfinite(pooled).all(), "Invalid full-clip mean-pooled features")
    probabilities = predict_softmax(head, pooled[None, :])[0]
    require(probabilities.shape == (3,) and np.isfinite(probabilities).all() and
            np.all((probabilities >= 0) & (probabilities <= 1)) and
            abs(float(probabilities.sum()) - 1.0) <= 1e-10,
            "Invalid subjective rating probability vector")
    return {"experiment": recipe["experiment"], "inputSource": "pinned-public-author-train",
            "runPurpose": "artifact-replay-smoke-inference",
            "encoder": kind, "headSha256": sha256_file(OUTPUT / "heads.npz"),
            "wholeClipMeanPooled": True, "corpusRatingClasses": [0, 1, 2],
            "subjectiveCorpusRatingProbabilities": [float(x) for x in probabilities],
            "calibrated": False, "productionEligible": False,
            "calibrationEligible": False, "learnerFeedbackEligible": False,
            "clinicalUseEligible": False, "clinicalReliabilityEstablished": False,
            "interpretation": "Uncalibrated subjective whole-clip corpus-rating probabilities; not target /R/ correctness or a produced-phone judgment."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Exact local public author-training WAV from the pinned index")
    parser.add_argument("--encoder", choices=tuple(ENCODERS), default="wav2vec2-base")
    args = parser.parse_args()
    print(json.dumps(infer(args.audio, args.encoder), indent=2, allow_nan=False))
