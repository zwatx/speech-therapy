"""Run the locked HuBERT third-encoder comparison on automatic adult speech.

This reuses already-inspected holdouts. It reports every run and selects no
encoder, pronunciation threshold, or learner-facing artifact.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[3]
AREA = ROOT / "research/audio-head"
sys.path.insert(0, str(AREA))

from comparison import compare_runs, load_run
from data import digest, load_manifest, read_json
from encoders import HubertEncoder, Wav2VecEncoder, WavLMEncoder
from pipeline import train


RECIPE = AREA / "experiments/cmu-arctic-hubert-third-v1.json"
MANIFEST = AREA / "outputs/cmu-arctic-four-speaker-v1/manifest.json"
OUTPUT = AREA / "outputs/cmu-arctic-hubert-third-v1"
CACHE = AREA / "outputs/model-cache"
ENCODERS = {"wav2vec2": Wav2VecEncoder.identity,
            "wavlm": WavLMEncoder.identity,
            "hubert": HubertEncoder.identity}
SOURCE_FILES = ("arctic_profiles.py", "labels.py", "data.py", "encoders.py",
                "pipeline.py", "diagnostics.py", "comparison.py", "requirements.lock.txt")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_sources(recipe: dict) -> None:
    expected = recipe.get("sourceSha256")
    require(type(expected) is dict and set(expected) == set(SOURCE_FILES) and
            all(expected[name] == digest((AREA / name).read_bytes()) for name in SOURCE_FILES),
            "Pinned training source or dependency lock changed")
    require(recipe["manifestSha256"] == digest(MANIFEST.read_bytes()) and
            recipe["sourceLockSha256"] == digest((MANIFEST.parent / "source-lock.json").read_bytes()),
            "Pinned adult-speech source changed during execution")


def validate_recipe() -> tuple[dict, str]:
    recipe = read_json(RECIPE)
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("status") == "locked" and
            recipe.get("purpose") == "public-speech-engineering" and
            recipe.get("predeclaredBeforeRuns") is True and
            recipe.get("noWinnerSelection") is True and
            recipe.get("manifest") == "research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json" and
            recipe.get("encoder") == HubertEncoder.identity and
            recipe.get("head") == "linear-v1" and
            [recipe.get(key) for key in ("trainingClips", "calibrationClips", "testClips")] ==
            [192, 12, 12] and
            recipe.get("globalSeed") == 7 and recipe.get("headSeeds") == [7, 17, 29] and
            recipe.get("stepBudgets") == [200, 800] and recipe.get("learningRate") == 0.01 and
            recipe.get("outputPrefix") == "cmu-arctic-hubert-third" and
            recipe.get("labelSource") == "automatic-phone-alignment" and
            all(recipe.get(key) is False for key in
                ("calibrated", "productionEligible", "learnerFeedbackEligible")),
            "HuBERT comparison recipe is not locked to the engineering scope")
    require(recipe.get("runnerSha256") == digest(Path(__file__).read_bytes()),
            "HuBERT comparison runner differs from the locked recipe")
    check_sources(recipe)
    manifest_sha = digest(MANIFEST.read_bytes())
    source_sha = digest((MANIFEST.parent / "source-lock.json").read_bytes())
    require(recipe.get("manifestSha256") == manifest_sha and
            recipe.get("sourceLockSha256") == source_sha and
            recipe.get("corpusSourceLockSha256") == source_sha,
            "Pinned adult-speech manifest or source lock changed")
    manifest, rows = load_manifest(MANIFEST)
    require(manifest["purpose"] == recipe["purpose"] and
            manifest["labelSource"] == recipe["labelSource"] and
            [sum(row["split"] == split for row in rows)
             for split in ("train", "calibration", "test")] == [192, 12, 12],
            "Pinned split or automatic-label scope changed")
    card = Path(hf_hub_download(HubertEncoder.identity["modelId"], "README.md",
                                revision=HubertEncoder.identity["revision"],
                                cache_dir=str(CACHE), local_files_only=True))
    require(digest(card.read_bytes()) == HubertEncoder.identity["licenseEvidence"]["modelCardSha256"],
            "Pinned HuBERT model card changed")
    return recipe, digest(RECIPE.read_bytes())


def directory(encoder: str, steps: int, seed: int) -> Path:
    if encoder == "hubert":
        return AREA / f"outputs/cmu-arctic-hubert-third-{steps}-headseed{seed}"
    return AREA / f"outputs/cmu-arctic-paired-{encoder}-{steps}-headseed{seed}"


def checked_run(encoder: str, steps: int, seed: int, recipe: dict | None = None) -> dict:
    result = load_run(directory(encoder, steps, seed), MANIFEST)
    require(result["encoder"] == ENCODERS[encoder] and result["head"] == "linear-v1" and
            result["steps"] == steps and result["seed"] == 7 and
            result["headInitializationSeed"] == seed and result["learningRate"] == 0.01 and
            result["initialHeadSha256"],
            f"{encoder} run differs from fixed head recipe")
    if encoder == "hubert":
        require(recipe is not None, "New HuBERT run requires locked source pins")
        recorded = read_json(directory(encoder, steps, seed) / "report.json").get("sourceSha256")
        require(type(recorded) is dict and
                all(recorded.get(name) == recipe["sourceSha256"][name]
                    for name in SOURCE_FILES if name.endswith(".py")),
                "HuBERT fit report does not bind the locked training implementation")
    return result


def summarize(runs: dict[tuple[str, int, int], dict], recipe: dict, recipe_sha: str) -> dict:
    groups, comparisons = [], []
    for steps in recipe["stepBudgets"]:
        compared = compare_runs(
            [(directory(encoder, steps, seed), MANIFEST)
             for encoder in ENCODERS for seed in recipe["headSeeds"]],
            allow_encoder_comparison=True)
        require(len(compared["runs"]) == 9 and
                {item["reportSha256"] for item in compared["runs"]} ==
                {runs[(encoder, steps, seed)]["reportSha256"]
                 for encoder in ENCODERS for seed in recipe["headSeeds"]},
                "Compared run hashes differ from verified source runs")
        comparisons.append({"steps": steps, "comparison": compared})
        for encoder in ENCODERS:
            selected = [runs[(encoder, steps, seed)] for seed in recipe["headSeeds"]]
            metrics = {}
            for split in ("train", "calibration", "test"):
                metrics[split] = {}
                for metric in ("ctcLoss", "tokenErrorRate", "sequenceAccuracy"):
                    values = [run["splits"][split][metric] for run in selected]
                    metrics[split][metric] = {
                        "valuesInHeadSeedOrder": values, "mean": statistics.mean(values),
                        "minimum": min(values), "maximum": max(values),
                        "sampleStandardDeviation": statistics.stdev(values)}
            groups.append({"encoder": encoder, "steps": steps, "metrics": metrics})
    initial_hashes = {}
    for seed in recipe["headSeeds"]:
        matched = [runs[(encoder, steps, seed)] for encoder in ENCODERS
                   for steps in recipe["stepBudgets"]]
        require(len({run["initialHeadSha256"] for run in matched}) == 1,
                "Same-width heads did not share initial weights within seed")
        initial_hashes[str(seed)] = matched[0]["initialHeadSha256"]
    require(len(set(initial_hashes.values())) == len(recipe["headSeeds"]),
            "Independent head seeds did not produce independent initializations")
    for split in ("train", "calibration", "test"):
        require(len({run["partitionSha256"][split] for run in runs.values()}) == 1,
                f"{split} recordings or labels differ between encoders")
    return {"schemaVersion": 1, "purpose": "engineering-third-encoder-comparison",
            "recipeSha256": recipe_sha, "runnerSha256": digest(Path(__file__).read_bytes()),
            "encoder": HubertEncoder.identity, "initialHeadSha256BySeed": initial_hashes,
            "runs": [runs[(encoder, steps, seed)] for encoder in ENCODERS
                     for steps in recipe["stepBudgets"] for seed in recipe["headSeeds"]],
            "groups": groups, "comparisons": comparisons,
            "selectionPerformed": False, "calibrated": False,
            "productionEligible": False, "learnerFeedbackEligible": False,
            "limitations": [
                "Automatic alignments on adult read speech are not verified produced-phone or clinical error labels.",
                "The same 24 held-out clips were inspected in earlier engineering runs; no fresh confirmation.",
                "Different upstream training and normalization remain confounded across encoders.",
                "Three head initializations describe initialization variation, not population uncertainty.",
                "No encoder winner, calibration, or learner-facing model is selected."]}


def main() -> None:
    require(not OUTPUT.exists() and not OUTPUT.is_symlink(), "Third-encoder report already exists")
    recipe, recipe_sha = validate_recipe()
    os.umask(0o077)
    # Verify every earlier anchor before producing new HuBERT runs.
    runs = {(encoder, steps, seed): checked_run(encoder, steps, seed)
            for encoder in ("wav2vec2", "wavlm")
            for steps in recipe["stepBudgets"] for seed in recipe["headSeeds"]}
    for steps in recipe["stepBudgets"]:
        for seed in recipe["headSeeds"]:
            check_sources(recipe)
            target = directory("hubert", steps, seed)
            if not target.exists():
                print(f"Training {target.name}", flush=True)
                train(MANIFEST, target, HubertEncoder.identity["kind"], CACHE,
                      steps=steps, seed=recipe["globalSeed"],
                      learning_rate=recipe["learningRate"],
                      allow_download=False, head_seed=seed)
            runs[("hubert", steps, seed)] = checked_run("hubert", steps, seed, recipe)
            check_sources(recipe)
            print(f"Verified {target.name}", flush=True)
    report = summarize(runs, recipe, recipe_sha)
    require(OUTPUT.parent.is_dir() and not OUTPUT.parent.is_symlink(),
            "Research output parent is missing or redirected")
    temporary = Path(tempfile.mkdtemp(prefix=".hubert-third-", dir=OUTPUT.parent))
    try:
        temporary.chmod(0o700)
        path = temporary / "report.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, OUTPUT)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    print(f"Saved {OUTPUT / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
