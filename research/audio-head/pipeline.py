"""Local linear CTC head optimization and uncalibrated posterior export."""
from __future__ import annotations

import platform
from pathlib import Path
import time

import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence

from data import AUTHORITY, BLANK, digest, load_manifest, load_pcm, read_json, validate_vocabulary, write_json
from encoders import load_encoder
from diagnostics import sequence_diagnostics


def validate_ctc_length(target: list[int], frames: int) -> None:
    minimum = len(target) + sum(a == b for a, b in zip(target, target[1:]))
    if frames < minimum:
        raise ValueError(f"CTC target requires {minimum} frames; encoder emitted {frames}")


def pack(rows: list[dict], vocabulary: list[str]):
    features, targets = [], []
    for row in rows:
        feature = row["features"]
        if feature.ndim != 2 or not torch.isfinite(feature).all() or len(feature) == 0:
            raise ValueError("Encoder features must be a finite nonempty frame matrix")
        target = [vocabulary.index(phone) for phone in row["targetPhones"]]
        validate_ctc_length(target, len(feature))
        features.append(feature)
        targets.append(torch.tensor(target, dtype=torch.long))
    return (pad_sequence(features, batch_first=True), torch.cat(targets),
            torch.tensor([len(f) for f in features], dtype=torch.long),
            torch.tensor([len(t) for t in targets], dtype=torch.long))


def ctc_loss(head: nn.Module, batch) -> torch.Tensor:
    features, targets, lengths, target_lengths = batch
    # The loss ignores padded frames via lengths; impossible alignments are rejected by pack.
    probabilities = head(features).log_softmax(-1).transpose(0, 1)
    return nn.functional.ctc_loss(probabilities, targets, lengths, target_lengths,
                                  blank=0, reduction="mean", zero_infinity=False)


def greedy_decode(indices: list[int], vocabulary: list[str]) -> list[str]:
    result, previous = [], None
    for current in indices:
        if current != 0 and current != previous:
            result.append(vocabulary[current])
        previous = current
    return result


def edit_distance(reference: list[str], predicted: list[str]) -> int:
    previous = list(range(len(predicted) + 1))
    for i, actual in enumerate(reference, 1):
        current = [i]
        for j, guess in enumerate(predicted, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (actual != guess)))
        previous = current
    return previous[-1]


@torch.no_grad()
def metrics(head: nn.Module, rows: list[dict], vocabulary: list[str]) -> dict:
    batch = pack(rows, vocabulary)
    frame_indices = [head(row["features"]).argmax(-1).tolist() for row in rows]
    predictions = [greedy_decode(frames, vocabulary) for frames in frame_indices]
    diagnostics = sequence_diagnostics([row["targetPhones"] for row in rows], predictions, frame_indices)
    reference_tokens = sum(len(row["targetPhones"]) for row in rows)
    edits = sum(edit_distance(row["targetPhones"], predicted) for row, predicted in zip(rows, predictions))
    return {"count": len(rows), "ctcLoss": float(ctc_loss(head, batch)),
            "diagnostics": diagnostics,
            "referenceTokenCount": reference_tokens, "tokenEdits": edits,
            "tokenErrorRate": edits / reference_tokens,
            "exactSequenceMatches": sum(p == r["targetPhones"] for p, r in zip(predictions, rows)),
            "sequenceAccuracy": sum(p == r["targetPhones"] for p, r in zip(predictions, rows)) / len(rows)}


def train(manifest_path: Path, output: Path, encoder_kind: str, cache: Path,
          steps: int = 200, seed: int = 7, learning_rate: float = 0.01,
          allow_download: bool = False, head_seed: int | None = None) -> dict:
    if not 1 <= steps <= 2000 or not 0 < learning_rate <= 0.1 or not 0 <= seed < 2**32:
        raise ValueError("Use 1–2000 steps, learning rate (0, 0.1], and a uint32 seed")
    if head_seed is not None and (type(head_seed) is not int or not 0 <= head_seed < 2**32):
        raise ValueError("Head initialization seed must be a uint32 or omitted")
    if output.exists():
        raise ValueError("Output directory already exists; choose a new run name")
    manifest, rows = load_manifest(manifest_path)
    if encoder_kind == "spectral-engineering-v1" and manifest["purpose"] != "synthetic-engineering":
        raise ValueError("Spectral smoke encoder is restricted to synthetic engineering fixtures")
    manifest_sha = digest(manifest_path.read_bytes())
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    encoder = load_encoder(encoder_kind, cache, allow_download)
    load_seconds = time.perf_counter() - started
    feature_start = time.perf_counter()
    with torch.no_grad():
        for row in rows:
            row["features"] = encoder(row["samples"])
    feature_seconds = time.perf_counter() - feature_start
    train_rows = [row for row in rows if row["split"] == "train"]
    vocabulary = manifest["vocabulary"]
    width = encoder.identity["width"]
    if any(row["features"].shape[1] != width for row in rows):
        raise ValueError("Encoder feature width mismatch")
    # Validate every partition before training. Neither held-out partition selects steps or weights.
    for split in ("train", "calibration", "test"):
        pack([row for row in rows if row["split"] == split], vocabulary)
    batch = pack(train_rows, vocabulary)
    # Optional independent initialization isolates the head from encoder-construction RNG use.
    # Omission preserves the established global-seed-before-encoder behavior.
    if head_seed is not None:
        torch.manual_seed(head_seed)
    head = nn.Linear(width, len(vocabulary))
    initial_head_sha = digest(b"".join(parameter.detach().numpy().astype("<f4").tobytes()
                                       for parameter in (head.weight, head.bias)))
    initial = metrics(head, train_rows, vocabulary)
    optimizer = torch.optim.AdamW(head.parameters(), lr=learning_rate, weight_decay=0.001)
    curve = [{"step": 0, "trainCtcLoss": initial["ctcLoss"]}]
    optimization_start = time.perf_counter()
    for step in range(1, steps + 1):
        optimizer.zero_grad(set_to_none=True)
        loss = ctc_loss(head, batch)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite CTC loss; run aborted")
        loss.backward()
        nn.utils.clip_grad_norm_(head.parameters(), 5.0, error_if_nonfinite=True)
        optimizer.step()
        if step % 25 == 0 or step == steps:
            curve.append({"step": step, "trainCtcLoss": float(ctc_loss(head, batch).detach())})
    optimization_seconds = time.perf_counter() - optimization_start
    head.eval()
    results = {split: metrics(head, [r for r in rows if r["split"] == split], vocabulary)
               for split in ("train", "calibration", "test")}
    if not all(torch.isfinite(torch.tensor(m["ctcLoss"])) for m in results.values()):
        raise ValueError("Nonfinite evaluation loss")
    output.mkdir(parents=True)
    weights = output / "head.pt"
    torch.save(head.state_dict(), weights)
    metadata = {"schemaVersion": 1, "purpose": manifest["purpose"], "calibrated": False,
                "labelSource": manifest["labelSource"],
                "splitIdentityBasis": manifest.get("splitIdentityBasis", "speaker-and-household-disjoint"),
                "encoder": encoder.identity, "vocabulary": vocabulary, "head": "linear-v1",
                "checkpointSha256": digest(weights.read_bytes()), "manifestSha256": manifest_sha,
                "seed": seed, "headInitializationSeed": head_seed, "initialHeadSha256": initial_head_sha,
                "steps": steps, "learningRate": learning_rate, **AUTHORITY}
    write_json(output / "checkpoint.json", metadata)
    source_hashes = {p.name: digest(p.read_bytes()) for p in Path(__file__).parent.glob("*.py")}
    report = {**metadata, "initialTrain": initial, "splits": results, "curve": curve,
              "measurements": {"encoderLoadSeconds": load_seconds, "featureExtractionSeconds": feature_seconds,
                               "optimizationSeconds": optimization_seconds, "totalSeconds": time.perf_counter() - started,
                               "headParameters": sum(p.numel() for p in head.parameters()),
                               "checkpointBytes": weights.stat().st_size,
                               "frameCountMin": min(len(r["features"]) for r in rows),
                               "frameCountMax": max(len(r["features"]) for r in rows)},
              "environment": {"python": platform.python_version(), "torch": torch.__version__,
                              "machine": platform.machine(), "platform": platform.platform(), "device": "cpu", "threads": 2},
              "sourceSha256": source_hashes,
              "limitations": ["Engineering experiment only; no clinical validation.",
                              "Automatic alignment agreement is not produced-phone accuracy." if manifest["labelSource"] == "automatic-phone-alignment" else "Fixture labels do not establish clinical validity.",
                              "Household relationships are unknown." if manifest["schemaVersion"] == 2 else "Partition identity validity depends on fixture provenance.",
                              "No calibration fitted; no error/pass decisions.",
                              "No signed bake-off or adaptation authorization produced.",
                              "Features held in memory only; no persistent feature cache or ONNX export."]}
    write_json(output / "report.json", report)
    return report


def load_head(checkpoint: Path):
    metadata = read_json(checkpoint / "checkpoint.json")
    if (metadata.get("schemaVersion") != 1 or metadata.get("head") != "linear-v1"
            or metadata.get("calibrated") is not False
            or metadata.get("purpose") not in {"synthetic-engineering", "permitted-engineering", "public-speech-engineering"}
            or any(metadata.get(k) is not False for k in AUTHORITY)):
        raise ValueError("Checkpoint must be an uncalibrated engineering artifact")
    if metadata["purpose"] == "public-speech-engineering" and (
            metadata.get("labelSource") != "automatic-phone-alignment"
            or metadata.get("splitIdentityBasis") != "speaker-disjoint-households-unknown"):
        raise ValueError("Public speech checkpoint must preserve automatic-label and household limitations")
    vocabulary = validate_vocabulary(metadata.get("vocabulary"))
    weights = checkpoint / "head.pt"
    if digest(weights.read_bytes()) != metadata["checkpointSha256"]:
        raise ValueError("Head checkpoint SHA-256 mismatch")
    from encoders import HubertEncoder, SpectralEncoder, Wav2VecEncoder, WavLMEncoder
    identity = metadata.get("encoder")
    if identity not in (SpectralEncoder.identity, Wav2VecEncoder.identity,
                        WavLMEncoder.identity, HubertEncoder.identity):
        raise ValueError("Unsupported or altered encoder identity")
    head = nn.Linear(identity["width"], len(vocabulary))
    head.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True), strict=True)
    if any(not torch.isfinite(p).all() for p in head.parameters()):
        raise ValueError("Nonfinite checkpoint weights")
    head.eval()
    return head, metadata


def frame_posteriors(head: nn.Module, features: torch.Tensor, vocabulary: list[str]) -> list[dict]:
    if features.ndim != 2 or not len(features) or not torch.isfinite(features).all():
        raise ValueError("Invalid frame features")
    with torch.no_grad():
        probabilities = head(features).softmax(-1)
    if probabilities.shape[1] != len(vocabulary) or not torch.isfinite(probabilities).all():
        raise ValueError("Invalid posterior matrix")
    if not torch.allclose(probabilities.sum(-1), torch.ones(len(features)), atol=1e-6):
        raise ValueError("Posterior rows do not sum to one")
    return [dict(zip(vocabulary, values)) for values in probabilities.tolist()]


def infer(checkpoint: Path, audio: Path, output: Path, cache: Path, allow_download=False) -> dict:
    if output.exists():
        raise ValueError("Output already exists")
    head, metadata = load_head(checkpoint)
    samples = load_pcm(audio)
    torch.set_num_threads(2)
    encoder = load_encoder(metadata["encoder"]["kind"], cache, allow_download)
    start = time.perf_counter()
    frames = frame_posteriors(head, encoder(samples), metadata["vocabulary"])
    result = {"schemaVersion": 1, "purpose": "engineering-inference", "calibrated": False,
              "labelSource": metadata.get("labelSource", "produced-phones"),
              "splitIdentityBasis": metadata.get("splitIdentityBasis", "speaker-and-household-disjoint"),
              "checkpointSha256": metadata["checkpointSha256"], "encoder": metadata["encoder"],
              "audioSha256": digest(audio.read_bytes()), "blankToken": BLANK,
              "frames": frames, "inferenceMilliseconds": (time.perf_counter() - start) * 1000,
              **AUTHORITY}
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    return result
