"""Compare the app's CTC implementation with PyTorch on preserved local exports."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import torch

from comparison import load_run
from data import AUTHORITY, BLANK, digest, load_manifest, read_json

AREA = Path(__file__).resolve().parent
ABSOLUTE_TOLERANCE = 1e-8


def torch_log_probability(frames, phones, blank):
    vocabulary = list(frames[0])
    probabilities = torch.tensor([[frame[token] for token in vocabulary] for frame in frames], dtype=torch.float64)
    targets = torch.tensor([vocabulary.index(phone) for phone in phones], dtype=torch.long)
    loss = torch.nn.functional.ctc_loss(probabilities.log().unsqueeze(1), targets,
        torch.tensor([len(frames)]), torch.tensor([len(phones)]),
        blank=vocabulary.index(blank), reduction="sum", zero_infinity=False)
    return -float(loss)


def synthetic_cases():
    def case(name, matrix, phones):
        return {"id": name, "frames": [dict(zip([BLANK, "a", "b"], row)) for row in matrix],
                "phones": phones, "blankToken": BLANK}
    cases = [
        case("single-frame", [[.25, .75, 0]], ["a"]),
        case("repeated-phone-impossible", [[.1, .8, .1]] * 2, ["a", "a"]),
        case("repeat-through-blank", [[0, 1, 0], [1, 0, 0], [0, 1, 0]], ["a", "a"]),
        case("blank-only-impossible", [[1, 0, 0]] * 3, ["a"]),
        case("residual-vocabulary-mass", [[.2, .3, .5]] * 4, ["a"]),
        case("low-probability-long-path", [[.995, .000001, .004999]] * 64, ["a", "b", "a"]),
    ]
    generator = torch.Generator().manual_seed(7)
    for length in (3, 8, 17, 64):
        matrix = torch.rand((length, 3), generator=generator, dtype=torch.float64)
        matrix /= matrix.sum(dim=1, keepdim=True)
        cases.append(case(f"variable-length-{length}", matrix.tolist(), ["a"] if length == 3 else ["a", "b", "b"]))
    invalid = [
        {**case("reject-unknown-phone", [[.2, .3, .5]], ["missing"]), "expectRejection": True},
        {**case("reject-blank-target", [[.2, .3, .5]], [BLANK]), "expectRejection": True},
        {**case("reject-renormalization-error", [[.2, .3, .4]], ["a"]), "expectRejection": True},
        {**case("reject-empty-target", [[.2, .3, .5]], []), "expectRejection": True},
    ]
    return cases + invalid


def export_cases(directory: Path, manifest_path: Path, export_path: Path | None = None,
                 recording_id: str | None = None):
    run = load_run(directory, manifest_path)
    _, rows = load_manifest(manifest_path)
    path = export_path if export_path is not None else directory / "posteriors-slt-a0201.json"
    exported = read_json(path)
    if (exported.get("schemaVersion") != 1 or exported.get("purpose") != "engineering-inference"
            or exported.get("calibrated") is not False or exported.get("blankToken") != BLANK
            or any(exported.get(key) is not False for key in AUTHORITY)
            or any(exported.get(key) != run[key] for key in
                   ("checkpointSha256", "encoder", "labelSource", "splitIdentityBasis"))):
        raise ValueError("Export changes checkpoint provenance or research-only authority")
    matching = [row for row in rows if row["audioSha256"] == exported.get("audioSha256")
                and (recording_id is None or row["id"] == recording_id)]
    if len(matching) != 1 or matching[0]["split"] not in {"calibration", "test"}:
        raise ValueError("Export must identify one verified held-out recording")
    frames = exported.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("Export must have frames")
    for frame in frames:
        if (not isinstance(frame, dict) or set(frame) != set(run["vocabulary"])
                or any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in frame.values())
                or not math.isclose(sum(frame.values()), 1, rel_tol=0, abs_tol=1e-6)):
            raise ValueError("Export has invalid full-vocabulary posteriors")
    row = matching[0]
    prefix = directory.name if recording_id is None else f"{directory.name}/{recording_id}"
    return [{"id": f"{prefix}/{label}", "frames": frames, "phones": phones, "blankToken": BLANK}
            for label, phones in (("automatic-reference", row["targetPhones"]),
                                  ("repeated-phone-probe", [row["targetPhones"][0]] * 2))], {
        "run": run, "exportSha256": digest(path.read_bytes()), "audioSha256": row["audioSha256"],
        "frameCount": len(frames), "recordingId": row["id"],
        **({"exportPath": str(path)} if export_path is not None else {}),
    }


def verify_cases(cases):
    bridge = AREA / "ctc_parity_bridge.ts"
    result = subprocess.run(["node", str(bridge)], input=json.dumps(cases, allow_nan=False),
                            capture_output=True, text=True, check=True, timeout=30)
    observed = json.loads(result.stdout)
    if len(observed) != len(cases):
        raise ValueError("Bridge omitted cases")
    checks = []
    for case, actual in zip(cases, observed):
        if actual.get("id") != case["id"]:
            raise ValueError("Bridge changed case order or identity")
        if case.get("expectRejection"):
            if actual.get("rejected") is not True:
                raise ValueError(f"Invalid input was accepted: {case['id']}")
            checks.append({"id": case["id"], "rejected": True})
            continue
        expected = torch_log_probability(case["frames"], case["phones"], case["blankToken"])
        if expected == -math.inf:
            if actual.get("logProbability") != "-Infinity":
                raise ValueError(f"Impossible path mismatch: {case['id']}")
            checks.append({"id": case["id"], "impossible": True})
        else:
            if not math.isfinite(expected):
                raise ValueError(f"Invalid oracle result: {case['id']}")
            score = actual.get("logProbability")
            if type(score) not in (int, float) or not math.isfinite(score) or abs(score - expected) > ABSOLUTE_TOLERANCE:
                raise ValueError(f"CTC numeric mismatch: {case['id']}")
            checks.append({"id": case["id"], "torchLogProbability": expected,
                           "typescriptLogProbability": score, "absoluteDifference": abs(score - expected)})
    return checks


def validate_explicit_entries(entries):
    recording_ids = sorted({entry[2] for entry in entries})
    run_names = {Path(entry[0]).resolve() for entry in entries}
    pairs = {(Path(entry[0]).resolve(), entry[2]) for entry in entries}
    if (not 2 <= len(recording_ids) <= 3 or len(pairs) != len(entries)
            or len(pairs) != len(run_names) * len(recording_ids)
            or any(len({entry[1] for entry in entries if Path(entry[0]).resolve() == run}) != 1
                   for run in run_names)):
        raise ValueError("Explicit exports require 2–3 distinct recordings under every distinct checkpoint and manifest")
    return recording_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", nargs=2, type=Path,
                        metavar=("CHECKPOINT_DIRECTORY", "MANIFEST"))
    parser.add_argument("--export", action="append", nargs=4,
                        metavar=("CHECKPOINT_DIRECTORY", "MANIFEST", "RECORDING_ID", "EXPORT_PATH"),
                        help="Explicit held-out recording export; repeat for each checkpoint and recording")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.run) == bool(args.export):
        parser.error("Choose either legacy --run or explicit --export entries")
    if args.output.exists():
        parser.error("Output exists; preserve earlier evidence")
    cases, exports = synthetic_cases(), []
    entries = args.run or args.export
    recording_ids = validate_explicit_entries(entries) if args.export else None
    for entry in entries:
        directory, manifest = map(Path, entry[:2])
        recording_id, path = (entry[2], Path(entry[3])) if args.export else (None, None)
        real_cases, evidence = export_cases(directory, manifest, path, recording_id)
        cases.extend(real_cases)
        exports.append(evidence)
    checks = verify_cases(cases)
    report = {"schemaVersion": 2 if args.export else 1, "purpose": "engineering-cross-language-ctc-parity", **AUTHORITY,
              "calibrated": False, "selectionPerformed": False, "absoluteLogProbabilityTolerance": ABSOLUTE_TOLERANCE,
              "oracle": "torch.nn.functional.ctc_loss, float64, sum reduction, zero_infinity=False",
              "torchVersion": torch.__version__, "nodeVersion": subprocess.check_output(["node", "--version"], text=True).strip(),
              "sourceSha256": {str(path.relative_to(AREA.parents[1])): digest(path.read_bytes()) for path in
                  (Path(__file__), AREA / "ctc_parity_bridge.ts", AREA.parents[1] / "packages/audio-scoring/src/ctc.ts")},
              "exports": exports, "checks": checks,
              **({"recordingIds": recording_ids} if args.export else {}),
              "limitations": ["Verifies exported-probability CTC math; does not validate waveform/model accuracy or calibrated clinical feedback.",
                              ("Real exports cover multiple preselected held-out public recordings under preserved checkpoints."
                               if args.export else "Real exports cover one previously inspected public recording under four checkpoints when run with the documented recipe."),
                              "Synthetic repeat probes are mathematical test paths, not judgments about the recording."]}
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(f"Verified {len(checks)} CTC parity and rejection cases: {args.output}")


if __name__ == "__main__":
    main()
