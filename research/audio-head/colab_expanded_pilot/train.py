#!/usr/bin/env python3
"""Cadence pilot trainer: a cached rating head, then matched head-only and
final-layer continuation arms on the frozen wav2vec2 encoder.

Outputs are descriptive research artifacts only. They make no clinical claims
and are never promoted automatically. outer.json, outer_features.npy and the
outer audio are hash-checked up front, but they are parsed only after
freeze.json binds all three chosen checkpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import random
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

import multiphone_models
from multiphone_models import MeanPoolPhoneRatingHead

MODEL_ID = "facebook/wav2vec2-lv-60-espeak-cv-ft"
REVISION = "ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4"
MODEL_FILES = ("config.json", "preprocessor_config.json", "pytorch_model.bin", "vocab.json")
TRANSFORMERS_VERSION = "4.57.6"
SEED, NUM_PHONES, HIDDEN, NUM_SCALARS = 17, 23, 1024, 13
FEATURE_DIM = HIDDEN + NUM_SCALARS
VOTES, MIN_AGE, MAX_AGE, SELECTION_ROWS = 5, 6, 12, 150
NUM_LAYERS, TRAIN_PREFIX = 24, "encoder.layers.23."
FEATURE_TOL, PROB_TOL, REPLAY_TOL = 0.005, 0.001, 1e-6
ARMS = (("headOnly", False), ("finalLayer", True))
ROW_KEYS = {"rowIndex", "id", "clipId", "speakerId", "age", "targetId", "targetPhone", "raterCounts", "window"}
CLIP_KEYS = {"id", "wav", "sampleCount", "frames"}


class StageError(RuntimeError):
    """A violated research constraint, tagged with its pipeline stage."""

    def __init__(self, stage: str, reason: str):
        super().__init__(f"[{stage}] {reason}")
        self.stage = stage


def require(condition, stage: str, reason: str) -> None:
    if not condition:
        raise StageError(stage, reason)


class Deadline:
    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        return self.end - time.monotonic()

    def check(self, stage: str) -> None:
        require(self.remaining() > 0, stage, "wall-clock deadline exceeded")


def _is_int(value) -> bool:
    return type(value) is int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def safe_relpath(rel) -> str:
    """Accept only plain forward-slash relative paths without traversal."""
    parts = rel.split("/") if isinstance(rel, str) else []
    require(parts and "\\" not in rel and ":" not in rel
            and all(part not in ("", ".", "..") for part in parts),
            "bundle", f"unsafe relative path {rel!r}")
    return rel


class Bundle:
    """Read-only view of a hash-pinned bundle; every read re-verifies its hash."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manifest_bytes = (self.root / "manifest.json").read_bytes()
        self.manifest_sha = hashlib.sha256(self.manifest_bytes).hexdigest()
        manifest = json.loads(self.manifest_bytes)
        require(isinstance(manifest, dict) and manifest.get("schema") == 1
                and manifest.get("seed") == SEED and manifest.get("modelId") == MODEL_ID
                and manifest.get("revision") == REVISION,
                "manifest", "schema, seed, modelId or revision mismatch")
        self.model_files, self.files = manifest.get("modelFiles"), manifest.get("files")
        require(isinstance(self.model_files, dict) and set(self.model_files) == set(MODEL_FILES)
                and isinstance(self.files, dict), "manifest", "modelFiles/files malformed")
        for rel, digest in [*self.files.items(), *self.model_files.items()]:
            safe_relpath(rel)
            require(isinstance(digest, str) and len(digest) == 64
                    and set(digest) <= set("0123456789abcdef"), "manifest", f"bad sha256 for {rel}")
        missing = {"train.json", "outer.json", "features.npy", "outer_features.npy"} - set(self.files)
        require(not missing, "manifest", f"missing files {sorted(missing)}")

    def path(self, rel: str) -> Path:
        require(rel in self.files, "bundle", f"{rel!r} is not listed in the manifest")
        path = (self.root / safe_relpath(rel)).resolve()
        require(path.is_relative_to(self.root) and path.is_file(), "bundle", f"{rel!r} escapes the bundle or is missing")
        return path

    def read(self, rel: str) -> bytes:
        data = self.path(rel).read_bytes()
        require(hashlib.sha256(data).hexdigest() == self.files[rel], "bundle", f"hash mismatch for {rel}")
        return data

    def verify_all(self, deadline: Deadline) -> None:
        for rel in sorted(self.files):
            deadline.check("hash")
            require(sha256_file(self.path(rel)) == self.files[rel], "hash", f"hash mismatch for {rel}")


def validate_rows(data, with_splits: bool = True, selection_rows: int = SELECTION_ROWS) -> dict:
    """Validate a train/outer payload; repeated occurrences are separate rows.

    Windows are half-open encoder-frame ranges [start, end) within the clip.
    """
    stage = "validate"
    keys = {"rows", "clips"} | ({"fitRows", "selectionRows"} if with_splits else set())
    require(isinstance(data, dict) and set(data) == keys, stage, f"top-level keys must be {sorted(keys)}")
    require(isinstance(data["rows"], list) and data["rows"] and isinstance(data["clips"], list),
            stage, "rows and clips must be lists")
    clips = {}
    for clip in data["clips"]:
        require(isinstance(clip, dict) and set(clip) == CLIP_KEYS and isinstance(clip["id"], str)
                and clip["id"] not in clips
                and all(_is_int(clip[k]) and clip[k] > 0 for k in ("sampleCount", "frames")),
                stage, f"invalid or duplicate clip {clip!r}")
        clips[clip["id"]] = {**clip, "wav": safe_relpath(clip["wav"])}
    require(len({c["wav"] for c in clips.values()}) == len(clips), stage, "clips share a wav file")
    rows, ids, phones, clip_speaker = data["rows"], set(), {}, {}
    row_positions = {}
    for i, row in enumerate(rows):
        where = f"row {i}"
        require(isinstance(row, dict) and set(row) == ROW_KEYS and _is_int(row["rowIndex"])
                and row["rowIndex"] >= 0 and row["rowIndex"] not in row_positions,
                stage, f"{where}: keys or duplicate/invalid rowIndex")
        row_positions[row["rowIndex"]] = i
        require(isinstance(row["id"], str) and row["id"] not in ids, stage, f"{where}: missing or duplicate id")
        ids.add(row["id"])
        clip = clips.get(row["clipId"])
        require(clip is not None and isinstance(row["speakerId"], str) and row["speakerId"],
                stage, f"{where}: unknown clip or speaker")
        require(clip_speaker.setdefault(row["clipId"], row["speakerId"]) == row["speakerId"],
                stage, f"{where}: clip spans speakers")
        require(_is_int(row["age"]) and MIN_AGE <= row["age"] <= MAX_AGE, stage, f"{where}: age outside child range")
        require(_is_int(row["targetId"]) and 0 <= row["targetId"] < NUM_PHONES
                and isinstance(row["targetPhone"], str)
                and phones.setdefault(row["targetId"], row["targetPhone"]) == row["targetPhone"],
                stage, f"{where}: invalid or inconsistent target")
        counts, window = row["raterCounts"], row["window"]
        require(isinstance(counts, list) and len(counts) == 3 and all(_is_int(v) and v >= 0 for v in counts)
                and sum(counts) == VOTES, stage, f"{where}: rater counts must be 3 ints summing to {VOTES}")
        require(isinstance(window, list) and len(window) == 2 and all(_is_int(v) for v in window)
                and 0 <= window[0] < window[1] <= clip["frames"], stage, f"{where}: invalid window")
    result = {"rows": rows, "clips": clips, "phoneNames": phones}
    if with_splits:
        fit, sel = data["fitRows"], data["selectionRows"]
        require(all(isinstance(s, list) and all(_is_int(v) for v in s) for s in (fit, sel))
                and len(fit + sel) == len(set(fit + sel))
                and set(fit + sel) == set(row_positions),
                stage, "fitRows/selectionRows must exactly partition rows")
        require(len(sel) == selection_rows, stage, f"expected {selection_rows} selection rows, got {len(sel)}")
        fit, sel = [row_positions[i] for i in fit], [row_positions[i] for i in sel]
        for key in ("speakerId", "clipId"):
            shared = {rows[i][key] for i in fit} & {rows[i][key] for i in sel}
            require(not shared, stage, f"fit/selection share {key}: {sorted(shared)[:5]}")
        require({rows[i]["targetId"] for i in fit} == set(range(NUM_PHONES)), stage, "fit rows must cover all phones")
        result.update(fit=fit, sel=sel)
    return result


def load_features(data: bytes, num_rows: int, stage: str) -> np.ndarray:
    features = np.load(io.BytesIO(data), allow_pickle=False)
    require(features.dtype == np.float32 and features.shape == (num_rows, FEATURE_DIM)
            and np.isfinite(features).all(), stage, f"features must be finite float32 [{num_rows},{FEATURE_DIM}]")
    return features


def read_wav(data: bytes, sample_count: int) -> np.ndarray:
    """Decode raw mono 16 kHz PCM16 to float32 in [-1, 1)."""
    with wave.open(io.BytesIO(data), "rb") as handle:
        require(handle.getnchannels() == 1 and handle.getsampwidth() == 2 and handle.getframerate() == 16000
                and handle.getcomptype() == "NONE", "audio", "wav must be mono 16 kHz PCM16")
        count = handle.getnframes()
        raw = handle.readframes(count)
    require(count == sample_count and len(raw) == 2 * count, "audio", f"expected {sample_count} samples, got {count}")
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def soft_targets(counts) -> np.ndarray:
    return np.asarray(counts, dtype=np.float64) / VOTES


def score(logprobs, counts, target_ids) -> dict:
    """Soft-label NLL (row mean, and macro over phones present), Brier and per-phone support."""
    logp = np.asarray(logprobs, dtype=np.float64)
    counts, ids = np.asarray(counts, dtype=np.int64), np.asarray(target_ids, dtype=np.int64)
    require(logp.ndim == 2 and logp.shape[1] == 3 and len(logp) == len(counts) == len(ids) > 0
            and np.isfinite(logp).all(), "score", "log-probabilities must be finite [N,3]")
    targets = counts / VOTES
    nll = -(targets * logp).sum(axis=1)
    prob = np.exp(logp)
    brier = (prob * prob - 2 * prob * targets).sum(axis=1) + 1
    per_phone = []
    for phone in range(NUM_PHONES):
        mask = ids == phone
        per_phone.append({"targetId": phone, "rows": int(mask.sum()), "votes": counts[mask].sum(axis=0).tolist(),
                          "nll": float(nll[mask].mean()) if mask.any() else None})
    present = [entry["nll"] for entry in per_phone if entry["rows"]]
    return {"rows": len(nll), "nll": float(nll.mean()), "macroPhoneNll": float(np.mean(present)),
            "brier": float(brier.mean()), "perPhone": per_phone}


def score_rows(rows, order, logprobs) -> dict:
    return score(logprobs, [rows[i]["raterCounts"] for i in order], [rows[i]["targetId"] for i in order])


def select_epoch(scores) -> int:
    """Earliest epoch with the minimum score; epoch 0 (the start point) is eligible."""
    require(scores and all(math.isfinite(s) for s in scores), "select", "nonfinite selection score")
    return min(range(len(scores)), key=lambda epoch: (scores[epoch], epoch))


def should_stop(scores, patience: int) -> bool:
    return len(scores) - 1 - select_epoch(scores) >= patience


def fit_normalizer(fit_features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = fit_features.astype(np.float64)
    mean, std = values.mean(axis=0), values.std(axis=0)
    std[std < 1e-6] = 1.0
    return mean.astype(np.float32), std.astype(np.float32)


def pool_windows(hidden: torch.Tensor, windows) -> torch.Tensor:
    """Mean of half-open frame windows [start, end) over one clip's [T,H] states."""
    return torch.stack([hidden[start:end].mean(dim=0) for start, end in windows])


def head_logits(head, normalized: torch.Tensor, ids: torch.Tensor) -> torch.Tensor:
    """Score each normalized row as its own one-frame, one-target clip, so repeats never collide."""
    mask = torch.ones(normalized.shape[0], 1, dtype=torch.bool, device=normalized.device)
    return head(normalized.unsqueeze(1), mask, ids.view(-1, 1), mask)[:, 0]


def pooled_logits(head, pooled, scalars, mean, std, ids) -> torch.Tensor:
    return head_logits(head, (torch.cat((pooled, scalars), dim=1) - mean) / std, ids)


def soft_ce(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    return -(targets * torch.log_softmax(logits, dim=-1)).sum(dim=-1)


def seed_all() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)


def configure_determinism() -> None:
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.set_float32_matmul_precision("highest")
    # Exactness is enforced by the explicit equality checks below, not by this flag.
    torch.use_deterministic_algorithms(True, warn_only=True)


def environment() -> dict:
    import huggingface_hub
    import transformers
    require(transformers.__version__ == TRANSFORMERS_VERSION, "setup",
            f"transformers {transformers.__version__} != {TRANSFORMERS_VERSION}")
    props = torch.cuda.get_device_properties(0)
    return {"python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__,
            "transformers": transformers.__version__, "huggingfaceHub": huggingface_hub.__version__,
            "cuda": torch.version.cuda, "cudnn": torch.backends.cudnn.version(), "gpu": props.name,
            "gpuMemoryBytes": props.total_memory, "tf32": torch.backends.cuda.matmul.allow_tf32,
            "cudnnBenchmark": torch.backends.cudnn.benchmark,
            "cublasWorkspaceConfig": os.environ.get("CUBLAS_WORKSPACE_CONFIG")}


def binding(manifest_sha: str) -> dict:
    return {"modelId": MODEL_ID, "revision": REVISION, "manifestSha256": manifest_sha}


def cpu_state(module) -> dict:
    return {k: v.detach().cpu().clone() for k, v in module.state_dict().items()}


def changed(module, reference: dict) -> bool:
    return any(not torch.equal(v, reference[k].to(v.device)) for k, v in module.state_dict().items())


def state_hash(module, exclude_prefix: str | None = None) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(module.state_dict().items(), key=lambda item: item[0]):
        if exclude_prefix and name.startswith(exclude_prefix):
            continue
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def load_encoder(bundle: Bundle):
    from huggingface_hub import snapshot_download
    from transformers import AutoFeatureExtractor, Wav2Vec2ForCTC

    snapshot = Path(snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=list(MODEL_FILES)))
    with tempfile.TemporaryDirectory() as tmp:
        # Load from a directory holding only the four verified files so that no
        # cached safetensors or stray file can be preferred over them.
        for name in MODEL_FILES:
            source = (snapshot / name).resolve()
            require(sha256_file(source) == bundle.model_files[name], "model", f"hash mismatch for {name}")
            os.symlink(source, Path(tmp) / name)
        extractor = AutoFeatureExtractor.from_pretrained(tmp, local_files_only=True)
        ctc = Wav2Vec2ForCTC.from_pretrained(tmp, local_files_only=True, attn_implementation="eager",
                                             torch_dtype=torch.float32, use_safetensors=False)
    encoder = ctc.wav2vec2.float().cuda().eval().requires_grad_(False)
    del ctc
    require(extractor.sampling_rate == 16000 and len(encoder.encoder.layers) == NUM_LAYERS
            and encoder.config.hidden_size == HIDDEN and encoder.config._attn_implementation == "eager"
            and all(p.dtype == torch.float32 for p in encoder.parameters()),
            "model", "unexpected encoder configuration")
    return extractor, encoder


def load_audio(bundle, extractor, encoder, clips, clip_ids, deadline, stage) -> dict:
    inputs = {}
    for clip_id in clip_ids:
        deadline.check(stage)
        clip = clips[clip_id]
        audio = read_wav(bundle.read(clip["wav"]), clip["sampleCount"])
        expected = int(encoder._get_feat_extract_output_lengths(torch.tensor(clip["sampleCount"])))
        require(expected == clip["frames"], stage, f"clip {clip_id}: frames {clip['frames']} != encoder {expected}")
        batch = extractor(audio, sampling_rate=16000, return_tensors="pt", return_attention_mask=True)
        require(bool(batch["attention_mask"].all()) and tuple(batch["input_values"].shape) == (1, len(audio)),
                stage, f"clip {clip_id}: unexpected feature-extractor output")
        inputs[clip_id] = batch["input_values"].float()
    return inputs


def encode(encoder, input_values, frames: int, grad: bool) -> torch.Tensor:
    require(not encoder.training, "encoder", "encoder must stay in eval mode")
    values = input_values.cuda()
    with torch.set_grad_enabled(grad):
        hidden = encoder(values, attention_mask=torch.ones_like(values, dtype=torch.long)).last_hidden_state[0]
    require(tuple(hidden.shape) == (frames, HIDDEN) and bool(torch.isfinite(hidden).all()),
            "encoder", "unexpected or nonfinite hidden states")
    return hidden


def clip_batches(rows, clips, features, row_ids) -> list:
    """Group rows by clip (first-appearance order) with GPU-ready targets and scalars."""
    grouped = {}
    for i in row_ids:
        grouped.setdefault(rows[i]["clipId"], []).append(i)
    return [{"clip": clip_id, "frames": clips[clip_id]["frames"], "rows": index,
             "windows": [tuple(rows[i]["window"]) for i in index],
             "ids": torch.tensor([rows[i]["targetId"] for i in index], device="cuda"),
             "targets": torch.tensor(soft_targets([rows[i]["raterCounts"] for i in index]),
                                     dtype=torch.float32, device="cuda"),
             "scalars": torch.from_numpy(features[index, HIDDEN:]).cuda()}
            for clip_id, index in grouped.items()]


def predict(ctx, batches, inputs, stage):
    """Raw-audio float32 log-probabilities and pooled states, in batch row order."""
    ctx.head.eval()
    logits, pooled = [], []
    with torch.no_grad():
        for batch in batches:
            ctx.deadline.check(stage)
            vectors = pool_windows(encode(ctx.encoder, inputs[batch["clip"]], batch["frames"], False), batch["windows"])
            logits.append(pooled_logits(ctx.head, vectors, batch["scalars"], ctx.mean, ctx.std, batch["ids"]))
            pooled.append(vectors)
        logprobs = torch.log_softmax(torch.cat(logits), dim=-1)
    order = np.array([i for batch in batches for i in batch["rows"]], dtype=np.int64)
    return logprobs.cpu().numpy(), torch.cat(pooled).cpu().numpy(), order


def fit_cached_head(features, rows, fit, sel, mean, std, deadline):
    """Fit the head on cached normalized rows; select by original-selection macro-phone NLL."""
    seed_all()
    head = MeanPoolPhoneRatingHead(feature_dim=FEATURE_DIM, num_phones=NUM_PHONES, hidden_dim=128, dropout=0.1).cuda()
    init = cpu_state(head)
    mean_t, std_t = torch.from_numpy(mean).cuda(), torch.from_numpy(std).cuda()

    def tensors(index):
        x = (torch.from_numpy(features[index]).cuda() - mean_t) / std_t
        ids = torch.tensor([rows[i]["targetId"] for i in index], device="cuda")
        targets = torch.tensor(soft_targets([rows[i]["raterCounts"] for i in index]), dtype=torch.float32, device="cuda")
        return x, ids, targets

    (fit_x, fit_ids, fit_t), (sel_x, sel_ids, _) = tensors(fit), tensors(sel)

    def evaluate():
        head.eval()
        with torch.no_grad():
            logprobs = torch.log_softmax(head_logits(head, sel_x, sel_ids), dim=-1).cpu().numpy()
        return score_rows(rows, sel, logprobs)

    optimizer = torch.optim.AdamW(head.parameters(), lr=3e-4, weight_decay=0.01)
    generator = torch.Generator().manual_seed(SEED)
    history, states = [{"epoch": 0, "trainLoss": None, "selection": evaluate()}], [init]
    for epoch in range(1, 21):
        head.train()
        total = 0.0
        for index in torch.randperm(len(fit), generator=generator).split(64):
            deadline.check("cached-head")
            index = index.cuda()
            loss = soft_ce(head_logits(head, fit_x[index], fit_ids[index]), fit_t[index]).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total += loss.item() * len(index)
        history.append({"epoch": epoch, "trainLoss": total / len(fit), "selection": evaluate()})
        states.append(cpu_state(head))
        if should_stop([h["selection"]["macroPhoneNll"] for h in history], 4):
            break
    chosen = select_epoch([h["selection"]["macroPhoneNll"] for h in history])
    head.load_state_dict(states[chosen])
    return head, {"arm": "baseline", "epoch": chosen, "selectedEpoch": chosen, "init": init, "head": states[chosen],
                  "layer": None, "mean": torch.from_numpy(mean), "std": torch.from_numpy(std), "history": history}


def save_checkpoint(ctx, path: Path, arm: str, epoch: int, adapt: bool) -> None:
    torch.save({"arm": arm, "epoch": epoch, **binding(ctx.manifest_sha), "head": cpu_state(ctx.head),
                "layer": cpu_state(ctx.layer) if adapt else None, "mean": ctx.mean.cpu(), "std": ctx.std.cpu(),
                "torchRng": torch.get_rng_state(), "cudaRng": torch.cuda.get_rng_state_all()}, path)


def restore(ctx, path: Path, sha: str, stage: str) -> None:
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, stage, f"{path.name} changed after freeze")
    ckpt = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
    require(all(ckpt.get(k) == v for k, v in binding(ctx.manifest_sha).items())
            and torch.equal(ckpt["mean"], ctx.mean.cpu()) and torch.equal(ckpt["std"], ctx.std.cpu()),
            stage, f"{path.name} is bound to another model, bundle or normalizer")
    ctx.head.load_state_dict(ckpt["head"])
    ctx.layer.load_state_dict(ckpt["layer"] if ckpt["layer"] is not None else ctx.orig_layer)


def run_arm(ctx, name: str, adapt: bool, out: Path) -> dict:
    """One continuation arm from the chosen head and original encoder, max 2 epochs."""
    stage = f"arm-{name}"
    seed_all()
    ctx.head.load_state_dict(ctx.chosen_head)
    ctx.layer.load_state_dict(ctx.orig_layer)
    ctx.encoder.requires_grad_(False)
    ctx.layer.requires_grad_(adapt)
    trainable = [n for n, p in ctx.encoder.named_parameters() if p.requires_grad]
    allowed = [n for n, _ in ctx.encoder.named_parameters() if n.startswith(TRAIN_PREFIX)] if adapt else []
    require(trainable == allowed and (trainable or not adapt), stage, "unexpected trainable encoder parameters")
    require(state_hash(ctx.encoder) == ctx.full_hash, stage, "encoder not reset to original weights")
    groups = [{"params": list(ctx.head.parameters()), "lr": 3e-4}]
    if adapt:
        groups.append({"params": list(ctx.layer.parameters()), "lr": 1e-6})
    optimizer = torch.optim.AdamW(groups, weight_decay=0.01)
    params = [p for group in groups for p in group["params"]]
    logprobs, _, order = predict(ctx, ctx.sel_b, ctx.inputs, stage)
    require(np.array_equal(logprobs, ctx.baseline_lp), stage, "epoch 0 differs from the frozen baseline")
    preds, steps, exposures = [logprobs], 0, 0
    history = [{"epoch": 0, "steps": 0, "rowExposures": 0, "trainLoss": None, "maxGradNorm": None,
                "selection": score_rows(ctx.rows, order, logprobs)}]
    save_checkpoint(ctx, out / f"{name}_best.pt", name, 0, adapt)
    for epoch in (1, 2):
        ctx.head.train()
        batches = [ctx.fit_b[i] for i in ctx.orders[epoch - 1]]
        loss_total, max_norm = 0.0, 0.0
        for start in range(0, len(batches), 4):
            group = batches[start:start + 4]
            occurrences = sum(len(batch["rows"]) for batch in group)
            optimizer.zero_grad(set_to_none=True)
            for batch in group:
                ctx.deadline.check(stage)
                hidden = encode(ctx.encoder, ctx.inputs[batch["clip"]], batch["frames"], grad=adapt)
                logits = pooled_logits(ctx.head, pool_windows(hidden, batch["windows"]), batch["scalars"],
                                       ctx.mean, ctx.std, batch["ids"])
                loss = soft_ce(logits, batch["targets"]).sum() / occurrences
                loss.backward()
                loss_total += loss.item() * occurrences
            require(all(p.grad is not None for p in params)
                    and bool(torch.stack([p.grad.isfinite().all() for p in params]).all()),
                    stage, "missing or nonfinite gradients")
            norm = torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
            optimizer.step()
            steps, exposures, max_norm = steps + 1, exposures + occurrences, max(max_norm, norm.item())
        require(all(bool(p.isfinite().all()) for p in params), stage, "nonfinite parameters")
        require(changed(ctx.head, ctx.chosen_head) and (not adapt or changed(ctx.layer, ctx.orig_layer)),
                stage, "no parameter update after an epoch")
        logprobs, _, order = predict(ctx, ctx.sel_b, ctx.inputs, stage)
        preds.append(logprobs)
        history.append({"epoch": epoch, "steps": steps, "rowExposures": exposures, "maxGradNorm": max_norm,
                        "trainLoss": loss_total / sum(len(b["rows"]) for b in batches),
                        "selection": score_rows(ctx.rows, order, logprobs)})
        print(json.dumps({"stage": stage, "epoch": epoch, "steps": steps,
                          "selectionMacroNll": history[-1]["selection"]["macroPhoneNll"]}), flush=True)
        write_json(out / f"{name}_history.json", history)
        save_checkpoint(ctx, out / f"{name}_last.pt", name, epoch, adapt)
        if select_epoch([h["selection"]["macroPhoneNll"] for h in history]) == epoch:
            save_checkpoint(ctx, out / f"{name}_best.pt", name, epoch, adapt)
    require(state_hash(ctx.encoder, TRAIN_PREFIX) == ctx.frozen_hash
            and (adapt or state_hash(ctx.encoder) == ctx.full_hash), stage, "encoder changed outside the allowlist")
    best = select_epoch([h["selection"]["macroPhoneNll"] for h in history])
    ctx.layer.load_state_dict(ctx.orig_layer)
    ctx.layer.requires_grad_(False)
    require(state_hash(ctx.encoder) == ctx.full_hash, stage, "encoder restore failed")
    return {"history": history, "selectedEpoch": best, "trainableEncoderParams": trainable,
            "selectionLogprobs": preds[best]}


def run(args, out: Path, report: dict) -> None:
    started = time.monotonic()
    deadline = Deadline(args.seconds)

    def stage(name):
        report["stage"] = name
        print(json.dumps({"stage": name, "remainingSeconds": round(deadline.remaining(), 1)}), flush=True)
        write_json(out / "report.json", report)

    stage("setup")
    require(torch.cuda.is_available(), "setup", "a CUDA device is required")
    configure_determinism()
    torch.cuda.reset_peak_memory_stats()
    bundle = Bundle(Path(args.bundle))
    here, models_path = Path(__file__).resolve(), Path(multiphone_models.__file__).resolve()
    report.update(environment=environment(), deadlineSeconds=args.seconds, manifestSha256=bundle.manifest_sha,
                  sourceSha256={here.name: sha256_file(here), models_path.name: sha256_file(models_path)})
    stage("hash")
    bundle.verify_all(deadline)

    stage("train-data")
    train = validate_rows(json.loads(bundle.read("train.json")), with_splits=True)
    rows, clips, fit, sel = train["rows"], train["clips"], train["fit"], train["sel"]
    features = load_features(bundle.read("features.npy"), len(rows), "train-data")

    stage("cached-head")
    mean, std = fit_normalizer(features[fit])
    head, cached = fit_cached_head(features, rows, fit, sel, mean, std, deadline)
    cached.update(binding(bundle.manifest_sha))
    torch.save(cached, out / "cached_head.pt")
    report["cachedHead"] = {"selectedEpoch": cached["selectedEpoch"], "history": cached["history"]}

    stage("encoder")
    extractor, encoder = load_encoder(bundle)
    fit_b, sel_b = clip_batches(rows, clips, features, fit), clip_batches(rows, clips, features, sel)
    report["data"] = {"rows": len(rows), "fitRows": len(fit), "selectionRows": len(sel),
                      "fitClips": len(fit_b), "selectionClips": len(sel_b)}
    ctx = SimpleNamespace(encoder=encoder, head=head, deadline=deadline, rows=rows, fit_b=fit_b, sel_b=sel_b,
                          mean=torch.from_numpy(mean).cuda(), std=torch.from_numpy(std).cuda(),
                          layer=encoder.encoder.layers[NUM_LAYERS - 1], manifest_sha=bundle.manifest_sha,
                          chosen_head={k: v.detach().clone() for k, v in head.state_dict().items()})
    ctx.orig_layer = {k: v.detach().clone() for k, v in ctx.layer.state_dict().items()}
    ctx.full_hash, ctx.frozen_hash = state_hash(encoder), state_hash(encoder, TRAIN_PREFIX)

    stage("audio")
    ctx.inputs = load_audio(bundle, extractor, encoder, clips, [b["clip"] for b in fit_b + sel_b], deadline, "audio")

    stage("parity")
    report["parity"] = []
    longest = max(fit_b, key=lambda b: clips[b["clip"]]["sampleCount"])
    for batch in [fit_b[0]] + ([longest] if longest is not fit_b[0] else []):
        raw_lp, pooled, order = predict(ctx, [batch], ctx.inputs, "parity")
        with torch.no_grad():
            cached_x = (torch.from_numpy(features[order]).cuda() - ctx.mean) / ctx.std
            cached_lp = torch.log_softmax(head_logits(head, cached_x, batch["ids"]), dim=-1).cpu().numpy()
        entry = {"clip": batch["clip"], "rows": len(order),
                 "maxAbsFeature": float(np.abs(pooled - features[order, :HIDDEN]).max()),
                 "maxAbsProb": float(np.abs(np.exp(raw_lp) - np.exp(cached_lp)).max())}
        report["parity"].append(entry)
        require(entry["maxAbsFeature"] < FEATURE_TOL and entry["maxAbsProb"] < PROB_TOL, "parity", f"mismatch {entry}")

    stage("baseline")
    timer = time.monotonic()
    ctx.baseline_lp, _, sel_order = predict(ctx, sel_b, ctx.inputs, "baseline")
    per_clip = (time.monotonic() - timer) / len(sel_b)
    report["baselineSelection"] = score_rows(rows, sel_order, ctx.baseline_lp)
    train_wavs = {c["wav"] for c in clips.values()}
    outer_wavs = sum(1 for rel in bundle.files if rel.endswith(".wav") and rel not in train_wavs)
    estimate = 1.5 * per_clip * (6 * len(fit_b) + 9 * len(sel_b) + 3 * outer_wavs) + 120
    report["estimatedRemainingSeconds"] = estimate
    require(deadline.remaining() > estimate, "estimate", f"need ~{estimate:.0f}s, {deadline.remaining():.0f}s left")

    rng = np.random.default_rng(SEED)
    ctx.orders = [rng.permutation(len(fit_b)).tolist() for _ in range(2)]
    arms_started, results = time.monotonic(), {}
    for name, adapt in ARMS:
        stage(f"arm-{name}")
        results[name] = run_arm(ctx, name, adapt, out)
        report.setdefault("arms", {})[name] = {k: v for k, v in results[name].items() if k != "selectionLogprobs"}
    report["armsSeconds"] = time.monotonic() - arms_started

    stage("freeze")
    checkpoints = {"baseline": out / "cached_head.pt", **{name: out / f"{name}_best.pt" for name, _ in ARMS}}
    freeze = {"checkpointSha256": {k: sha256_file(p) for k, p in checkpoints.items()},
              "selectedEpochs": {"baseline": cached["selectedEpoch"],
                                 **{k: r["selectedEpoch"] for k, r in results.items()}},
              "cachedHeadHistory": cached["history"], "armHistories": {k: r["history"] for k, r in results.items()},
              "sourceSha256": report["sourceSha256"], **binding(bundle.manifest_sha)}
    selection_values = {"baseline": ctx.baseline_lp, **{k: r["selectionLogprobs"] for k, r in results.items()}}
    for name, logvalues in selection_values.items():
        np.savez(out / f"selection_{name}.npz",
                 rowIndices=np.array([rows[i]["rowIndex"] for i in sel_order], dtype=np.int64),
                 logprobabilities=logvalues.astype(np.float64), probabilities=np.exp(logvalues.astype(np.float64)),
                 raterCounts=np.array([rows[i]["raterCounts"] for i in sel_order], dtype=np.int64),
                 targetIds=np.array([rows[i]["targetId"] for i in sel_order], dtype=np.int64))
    freeze["selectionFiles"] = {name: sha256_file(out / f"selection_{name}.npz") for name in selection_values}
    write_json(out / "freeze.json", freeze)
    report["freezeSha256"] = sha256_file(out / "freeze.json")

    stage("replay")
    expected = {"baseline": ctx.baseline_lp, **{k: r["selectionLogprobs"] for k, r in results.items()}}
    report["replay"] = {}
    for name, path in checkpoints.items():
        restore(ctx, path, freeze["checkpointSha256"][name], "replay")
        logprobs, _, _ = predict(ctx, sel_b, ctx.inputs, "replay")
        delta = float(np.abs(logprobs - expected[name]).max())
        report["replay"][name] = {"maxAbsLogprobDelta": delta, "exact": bool(np.array_equal(logprobs, expected[name]))}
        require(delta <= REPLAY_TOL, "replay", f"{name} checkpoint replay differs by {delta}")

    stage("outer")
    outer = validate_rows(json.loads(bundle.read("outer.json")), with_splits=False)
    orows, oclips = outer["rows"], outer["clips"]
    ofeatures = load_features(bundle.read("outer_features.npy"), len(orows), "outer")
    for key in ("speakerId", "clipId", "id"):
        shared = {r[key] for r in orows} & {r[key] for r in rows}
        require(not shared, "outer", f"outer shares {key} with fit/selection: {sorted(shared)[:5]}")
    require(not {c["wav"] for c in oclips.values()} & train_wavs, "outer", "outer shares wav files with train")
    require(all(train["phoneNames"].get(k, v) == v for k, v in outer["phoneNames"].items()),
            "outer", "targetPhone names disagree with train")
    outer_b = clip_batches(orows, oclips, ofeatures, range(len(orows)))
    outer_inputs = load_audio(bundle, extractor, encoder, oclips, [b["clip"] for b in outer_b], deadline, "outer")
    report["outer"], outer_lp = {}, {}
    for name, path in checkpoints.items():
        restore(ctx, path, freeze["checkpointSha256"][name], "outer")
        logprobs, pooled, order = predict(ctx, outer_b, outer_inputs, "outer")
        outer_lp[name], logp = logprobs, logprobs.astype(np.float64)
        np.savez(out / f"outer_{name}.npz", rowIndices=np.array([orows[i]["rowIndex"] for i in order], dtype=np.int64),
                 logprobabilities=logp, probabilities=np.exp(logp),
                 raterCounts=np.array([orows[i]["raterCounts"] for i in order], dtype=np.int64),
                 targetIds=np.array([orows[i]["targetId"] for i in order], dtype=np.int64))
        report["outer"][name] = score_rows(orows, order, logprobs)
        if name == "baseline":  # cached columns are a descriptive comparison only, never model input
            report["outer"][name]["cacheMaxAbsFeature"] = float(np.abs(pooled - ofeatures[order, :HIDDEN]).max())
    for name, _ in ARMS:
        require(results[name]["selectedEpoch"] != 0 or np.array_equal(outer_lp[name], outer_lp["baseline"]),
                "outer", f"{name} selected epoch 0 but differs from the frozen baseline")
    ctx.layer.load_state_dict(ctx.orig_layer)
    require(state_hash(encoder) == ctx.full_hash, "outer", "encoder not restored after evaluation")

    report.update(stage="done", complete=True, trainingRuntimeSeconds=time.monotonic() - started,
                  gpuMemoryPeakBytes=torch.cuda.max_memory_allocated())
    write_json(out / "report.json", report)


def main(argv=None) -> int:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # before any cuBLAS use
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--output", required=True, help="fresh directory; must not exist")
    parser.add_argument("--seconds", type=float, default=1800.0)
    args = parser.parse_args(argv)
    out, bundle_root = Path(args.output).resolve(), Path(args.bundle).resolve()
    if not args.seconds > 0 or out.exists() or out.is_relative_to(bundle_root):
        parser.error("--seconds must be positive and --output a fresh path outside the bundle")
    out.mkdir(parents=True)
    report = {"complete": False, "learnerFeedbackEligible": False, "promotionEligible": False,
              "authorTestRead": False, "clinicalUseEligible": False, "billingUnits": "not measured here; the local controller handles billing",
              "scope": "descriptive pilot only; no tuning on outer rows and no clinical claims"}
    try:
        run(args, out, report)
    except BaseException as exc:
        report.update(complete=False, failedStage=getattr(exc, "stage", report.get("stage")),
                      error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        if torch.cuda.is_available():
            report["gpuMemoryPeakBytes"] = torch.cuda.max_memory_allocated()
        write_json(out / "report.json", report)
        print(f"FAILED at {report['failedStage']}: {report['error']}", file=sys.stderr)
        return 1
    print(json.dumps({"complete": True, "output": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
