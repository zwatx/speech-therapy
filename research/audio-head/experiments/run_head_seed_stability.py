"""Replay the fixed three-head-seed experiment; no selection or new downloads."""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
AREA = ROOT / "research/audio-head"
sys.path.insert(0, str(AREA))

from comparison import compare_runs, load_run
from data import AUTHORITY, digest, read_json
from encoders import Wav2VecEncoder, WavLMEncoder
from pipeline import train


def main():
    recipe_path = AREA / "experiments/cmu-arctic-head-seed-stability-v1.json"
    output = AREA / "outputs/cmu-arctic-head-seed-stability-v1.json"
    if output.exists():
        raise ValueError("Completed stability report exists; preserve it")
    recipe = read_json(recipe_path)
    manifest = AREA / "outputs/cmu-arctic-four-speaker-v1/manifest.json"
    identities = {"wav2vec2": Wav2VecEncoder.identity, "wavlm": WavLMEncoder.identity}
    assert recipe["runnerSha256"] == digest(Path(__file__).read_bytes())
    assert recipe["manifestSha256"] == digest(manifest.read_bytes())
    assert recipe["corpusSourceLockSha256"] == digest((manifest.parent / "source-lock.json").read_bytes())
    assert recipe["pairedRecipeSha256"] == digest((AREA / "experiments/cmu-arctic-paired-encoders-v2.json").read_bytes())
    assert recipe["encoders"] == identities
    assert recipe["headSeeds"] == [7, 17, 29] and recipe["newHeadSeeds"] == [17, 29]
    assert recipe["globalSeed"] == 7 and recipe["stepBudgets"] == [200, 800] and recipe["learningRate"] == 0.01
    assert all(recipe[key] is False for key in AUTHORITY)

    def directory(encoder, steps, seed):
        return AREA / f"outputs/cmu-arctic-paired-{encoder}-{steps}-headseed{seed}"

    def checked_run(encoder, steps, seed):
        evidence = load_run(directory(encoder, steps, seed), manifest)
        assert evidence["encoder"] == identities[encoder] and evidence["head"] == "linear-v1"
        assert evidence["steps"] == steps and evidence["seed"] == 7 and evidence["learningRate"] == 0.01
        assert evidence["headInitializationSeed"] == seed and evidence["initialHeadSha256"]
        return evidence

    # Verify every existing seed-7 anchor before starting additional optimization.
    for encoder in identities:
        for steps in recipe["stepBudgets"]:
            checked_run(encoder, steps, 7)
    for seed in recipe["newHeadSeeds"]:
        for encoder, identity in identities.items():
            for steps in recipe["stepBudgets"]:
                destination = directory(encoder, steps, seed)
                if not destination.exists():
                    print(f"Training fixed run: {destination.name}", flush=True)
                    train(manifest, destination, identity["kind"], AREA / "outputs/model-cache",
                          steps=steps, seed=7, learning_rate=0.01, allow_download=False, head_seed=seed)
                checked_run(encoder, steps, seed)
                print(f"Verified completed run: {destination.name}", flush=True)

    groups, runs = [], []
    for encoder in identities:
        for steps in recipe["stepBudgets"]:
            # Each existing comparison stays within its 2–10-run bound.
            compared = compare_runs([(directory(encoder, steps, seed), manifest) for seed in recipe["headSeeds"]])
            evidence = [checked_run(encoder, steps, seed) for seed in recipe["headSeeds"]]
            assert [r["reportSha256"] for r in evidence] == [r["reportSha256"] for r in compared["runs"]]
            runs.extend(evidence)
            aggregate = {}
            for split in ("train", "calibration", "test"):
                aggregate[split] = {}
                for metric in ("ctcLoss", "tokenErrorRate", "sequenceAccuracy"):
                    values = [run["splits"][split][metric] for run in evidence]
                    aggregate[split][metric] = {"valuesInHeadSeedOrder": values, "mean": statistics.mean(values),
                        "minimum": min(values), "maximum": max(values), "sampleStandardDeviation": statistics.stdev(values)}
            groups.append({"encoder": encoder, "steps": steps, "headSeeds": recipe["headSeeds"],
                           "runs": [r["name"] for r in evidence], "metrics": aggregate})
    assert len(runs) == 12 and len({run["name"] for run in runs}) == 12
    assert len({run["manifestSha256"] for run in runs}) == 1
    for split in ("train", "calibration", "test"):
        assert len({run["partitionSha256"][split] for run in runs}) == 1
    initial_hashes = {}
    for seed in recipe["headSeeds"]:
        paired = [run for run in runs if run["headInitializationSeed"] == seed]
        assert len(paired) == 4 and len({run["initialHeadSha256"] for run in paired}) == 1
        initial_hashes[str(seed)] = paired[0]["initialHeadSha256"]
    assert len(set(initial_hashes.values())) == 3
    report = {"schemaVersion": 1, "purpose": "engineering-head-initialization-stability", **AUTHORITY,
              "calibrated": False, "selectionPerformed": False, "recipeSha256": digest(recipe_path.read_bytes()),
              "runnerSha256": recipe["runnerSha256"], "recipe": recipe, "initialHeadSha256BySeed": initial_hashes,
              "runs": runs, "groups": groups,
              "limitations": ["Three head initializations on identical already-inspected holdouts; no population confidence interval.",
                  "Mean, range, and sample standard deviation describe initialization variability only, not independent speakers or cohorts.",
                  "All runs and fixed step budgets are reported; no winner, tuning, or deployment approval.",
                  "Automatic labels from adult read speech are not reviewed child productions or clinical error judgments.",
                  "Different upstream encoder pretraining and preprocessing remain; pretraining-corpus overlap was not audited.",
                  "No new noise experiment or new model download was performed for these additional seeds."]}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(f"Saved all twelve runs and initialization-only aggregates: {output}", flush=True)


if __name__ == "__main__":
    main()
