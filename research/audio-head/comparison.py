"""Compare engineering runs on identical holdouts without choosing a winner."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from data import AUTHORITY, digest, load_manifest, read_json
from pipeline import load_head


def partition_signature(rows: list[dict], split: str) -> str:
    # Relative paths can differ between imports. Recording, label, and identity
    # evidence must remain identical, including item membership and phone order.
    evidence = [{"id": row["id"], "audioSha256": row["audioSha256"],
                 "alignmentSha256": row.get("alignmentSha256"),
                 "targetPhones": row["targetPhones"], "speakerHash": row["speakerHash"],
                 "householdHash": row["householdHash"]}
                for row in rows if row["split"] == split]
    evidence.sort(key=lambda row: row["id"])
    return digest(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode())


def check_metrics(value: dict, rows: list[dict]) -> None:
    count, tokens = len(rows), sum(len(row["targetPhones"]) for row in rows)
    if value.get("count") != count or value.get("referenceTokenCount") != tokens:
        raise ValueError("Report partition counts differ from its manifest")
    for field in ("tokenEdits", "exactSequenceMatches"):
        if type(value.get(field)) is not int or value[field] < 0:
            raise ValueError(f"Invalid report metric: {field}")
    if value["exactSequenceMatches"] > count:
        raise ValueError("Exact matches exceed sequence count")
    for field in ("ctcLoss", "tokenErrorRate", "sequenceAccuracy"):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid report metric: {field}")
    if (not math.isclose(value["tokenErrorRate"], value["tokenEdits"] / tokens, abs_tol=1e-12)
            or not math.isclose(value["sequenceAccuracy"], value["exactSequenceMatches"] / count, abs_tol=1e-12)):
        raise ValueError("Report rate differs from its numerator and denominator")


def load_run(directory: Path, manifest_path: Path) -> dict:
    manifest, rows = load_manifest(manifest_path)
    _, metadata = load_head(directory)
    report_path = directory / "report.json"
    report = read_json(report_path)
    if any(report.get(key) != value for key, value in metadata.items()):
        raise ValueError("Report and checkpoint metadata disagree")
    if metadata["manifestSha256"] != digest(manifest_path.read_bytes()):
        raise ValueError("Run was trained with a different manifest")
    if any(metadata.get(key) != manifest[key] for key in ("purpose", "labelSource", "vocabulary")):
        raise ValueError("Run changes manifest purpose, label provenance, or vocabulary")
    if metadata.get("splitIdentityBasis") != manifest.get("splitIdentityBasis", "speaker-and-household-disjoint"):
        raise ValueError("Run changes partition identity provenance")
    for split in ("train", "calibration", "test"):
        value = report.get("splits", {}).get(split)
        if not isinstance(value, dict):
            raise ValueError("Report is missing a partition")
        check_metrics(value, [row for row in rows if row["split"] == split])
    return {"name": directory.name, "reportSha256": digest(report_path.read_bytes()),
            "checkpointSha256": metadata["checkpointSha256"],
            "manifestSha256": metadata["manifestSha256"],
            "purpose": metadata["purpose"], "labelSource": metadata["labelSource"],
            "splitIdentityBasis": metadata["splitIdentityBasis"],
            "vocabulary": metadata["vocabulary"], "encoder": metadata["encoder"],
            "head": metadata["head"], "seed": metadata["seed"], "steps": metadata["steps"],
            "headInitializationSeed": metadata.get("headInitializationSeed"),
            "initialHeadSha256": metadata.get("initialHeadSha256"),
            "learningRate": metadata["learningRate"], "splits": report["splits"],
            "partitionSha256": {split: partition_signature(rows, split)
                                for split in ("train", "calibration", "test")}}


def compare_runs(runs: list[tuple[Path, Path]], *, allow_encoder_comparison: bool = False) -> dict:
    if not 2 <= len(runs) <= 10 or len({directory.resolve() for directory, _ in runs}) != len(runs):
        raise ValueError("Compare 2–10 distinct run directories")
    loaded = [load_run(directory, manifest) for directory, manifest in runs]
    reference = loaded[0]
    for candidate in loaded[1:]:
        for field in ("purpose", "labelSource", "splitIdentityBasis", "vocabulary", "head"):
            if candidate[field] != reference[field]:
                raise ValueError(f"Runs have incompatible {field}")
        if candidate["encoder"] != reference["encoder"] and not allow_encoder_comparison:
            raise ValueError("Runs have incompatible encoder; explicitly enable encoder comparison")
        for split in ("calibration", "test"):
            if candidate["partitionSha256"][split] != reference["partitionSha256"][split]:
                raise ValueError(f"Runs do not use identical {split} recordings, labels, and identities")
        candidate["differenceFromFirst"] = {
            split: {"tokenErrorRatePercentagePoints":
                    100 * (candidate["splits"][split]["tokenErrorRate"] - reference["splits"][split]["tokenErrorRate"]),
                    "ctcLoss": candidate["splits"][split]["ctcLoss"] - reference["splits"][split]["ctcLoss"]}
            for split in ("calibration", "test")
        }
    return {"schemaVersion": 1, "purpose": "engineering-run-comparison", **AUTHORITY,
            "calibrated": False, "selectionPerformed": False,
            "encoderComparisonEnabled": allow_encoder_comparison,
            "encodersDiffer": any(run["encoder"] != reference["encoder"] for run in loaded[1:]),
            "referenceRun": reference["name"], "runs": loaded,
            "limitations": [
                "All runs are reported in supplied order; no winner or deployment approval is selected.",
                "Holdout records are identical across these runs; this does not establish that they were previously unseen.",
                "Metrics are checked for provenance and arithmetic consistency, not independently recomputed here.",
                "Agreement with automatic alignments is not produced-phone accuracy or clinical error detection.",
                "Encoder contrasts can also differ in training data, normalization, and features; inspect the complete recorded recipe.",
            ]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", nargs=2, type=Path, required=True,
                        metavar=("RUN_DIRECTORY", "MANIFEST"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-encoder-comparison", action="store_true",
                        help="Compare different pinned encoders on identical holdouts; does not select a winner")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output exists; choose a new comparison name")
        report = compare_runs(args.run, allow_encoder_comparison=args.allow_encoder_comparison)
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        print(f"Saved comparison of {len(report['runs'])} engineering runs: {args.output}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
