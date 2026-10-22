"""Portable feature-only research mixture for ages 6-12 (completed years).

Research use only: the bundle is not validated for learner feedback, clinical
use, or promotion. Every bundle byte is verified against a caller-supplied
manifest hash before parsing; no code is imported from the bundle.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import numbers
import os
import re
from pathlib import Path

import numpy as np
import torch

import multiphone_models
from multiphone_models import MeanPoolPhoneRatingHead

PHONES = ("B", "P", "M", "T", "D", "N", "K", "G", "F", "V", "S", "Z", "SH", "CH",
          "JH", "L", "R", "W", "Y", "HH", "TH", "DH", "NG")
KIND = "cadence-expanded-child-mixture"
TARGET_WIDTH, SCALAR_WIDTH, PCA_WIDTH = 1024, 13, 16
FEATURE_WIDTH = TARGET_WIDTH + SCALAR_WIDTH
BATCH_SIZE, THREADS = 64, 2
MANIFEST = "manifest.json"
FILE_NAMES = ("scalar.pt", "compact.pt", "projection.pt", "provenance.json")
_FLAGS = ("learnerFeedbackEligible", "clinicalUseEligible", "promotionEligible")
_MANIFEST_KEYS = frozenset({"schemaVersion", "kind", "ageRangeYears", "featureWidth", "targetPhones",
                            "mixtureWeights", "modelSourceSha256", "files", *_FLAGS})
_HEAD_KEYS = frozenset({"model", "mean", "std", "epochs"})
_HEX = re.compile(r"[0-9a-f]{64}")


def sha256(path: str | os.PathLike[str]) -> str:
    """Return the lowercase hex SHA-256 of a file's bytes."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON keys")
    return dict(pairs)


def _reject_constant(name: str) -> object:
    raise ValueError(f"nonstandard JSON constant {name}")


def _same(actual: object, expected: object) -> bool:
    # Type-strict equality so JSON true/1/1.0 cannot stand in for each other.
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(map(_same, actual, expected))
    return actual == expected


def _parse_manifest(data: bytes) -> dict[str, object]:
    try:
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                              parse_constant=_reject_constant)
    except ValueError as exc:
        raise ValueError(f"manifest.json is not valid strict JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must be a JSON object")
    missing, extra = _MANIFEST_KEYS - set(manifest), set(manifest) - _MANIFEST_KEYS
    if missing or extra:
        raise ValueError(f"manifest.json keys differ from schema: missing {sorted(missing)}, "
                         f"unexpected {sorted(extra)}")
    files = manifest["files"]
    if not isinstance(files, dict):
        raise ValueError("manifest.json files must be an object")
    for name in files:
        if name in ("", ".", "..") or "\\" in name or os.path.basename(name) != name:
            raise ValueError(f"manifest.json file path {name!r} is not a plain basename")
    if set(files) != set(FILE_NAMES):
        raise ValueError(f"manifest.json files must be exactly {list(FILE_NAMES)}")
    for name, digest in files.items():
        if not isinstance(digest, str) or not _HEX.fullmatch(digest):
            raise ValueError(f"manifest.json hash for {name} is not 64 lowercase hex characters")
    expected = {
        "schemaVersion": 1, "kind": KIND, "ageRangeYears": [6, 12], "featureWidth": FEATURE_WIDTH,
        "targetPhones": list(PHONES), "mixtureWeights": [0.5, 0.5], **{flag: False for flag in _FLAGS},
        "modelSourceSha256": sha256(multiphone_models.__file__),
    }
    for key, value in expected.items():
        if not _same(manifest[key], value):
            raise ValueError(f"manifest.json {key} must be {value!r}, got {manifest[key]!r}")
    return manifest


def _check_tensor(value: object, label: str, dtype: torch.dtype,
                  shape: tuple[int, ...] | None = None) -> torch.Tensor:
    if (not isinstance(value, torch.Tensor) or value.layout != torch.strided or value.dtype != dtype
            or (shape is not None and tuple(value.shape) != shape)):
        raise ValueError(f"{label} must be a dense {dtype} tensor"
                         + (f" with shape {list(shape)}" if shape is not None else ""))
    if not torch.isfinite(value).all():
        raise ValueError(f"{label} has nonfinite values")
    return value


def _torch_load(data: bytes, name: str) -> object:
    try:
        return torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
    except Exception as exc:  # torch/pickle raise many types; report all as a bundle error.
        raise ValueError(f"Cannot load {name}: {exc}") from exc


def _load_head(data: bytes, name: str, width: int) -> tuple[MeanPoolPhoneRatingHead, np.ndarray, np.ndarray]:
    payload = _torch_load(data, name)
    if not isinstance(payload, dict) or set(payload) != _HEAD_KEYS:
        raise ValueError(f"{name} must be a dict with keys {sorted(_HEAD_KEYS)}")
    epochs = payload["epochs"]
    if type(epochs) is not int or not 1 <= epochs <= 100:
        raise ValueError(f"{name} epochs must be an int in 1..100")
    mean = _check_tensor(payload["mean"], f"{name} mean", torch.float32, (width,))
    std = _check_tensor(payload["std"], f"{name} std", torch.float32, (width,))
    if not (std > 0).all():
        raise ValueError(f"{name} std must be positive")
    state = payload["model"]
    if not isinstance(state, dict):
        raise ValueError(f"{name} model must be a state dict")
    for key, value in state.items():
        _check_tensor(value, f"{name} model[{key!r}]", torch.float32)
    with torch.random.fork_rng(devices=[]):  # initialization must not advance the caller's RNG
        model = MeanPoolPhoneRatingHead(width, num_phones=24, hidden_dim=128, dropout=0.1)
    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError as exc:
        raise ValueError(f"{name} model state does not match the head: {exc}") from exc
    model.eval().requires_grad_(False)
    return model, mean.numpy().copy(), std.numpy().copy()


def _load_projection(data: bytes) -> tuple[torch.Tensor, torch.Tensor]:
    payload = _torch_load(data, "projection.pt")
    if not isinstance(payload, dict) or set(payload) != {"center", "basis"}:
        raise ValueError("projection.pt must be a dict with keys ['basis', 'center']")
    center = _check_tensor(payload["center"], "projection.pt center", torch.float64, (TARGET_WIDTH,))
    basis = _check_tensor(payload["basis"], "projection.pt basis", torch.float64, (TARGET_WIDTH, PCA_WIDTH))
    if not torch.allclose(basis.T @ basis, torch.eye(PCA_WIDTH, dtype=torch.float64), rtol=0, atol=1e-8):
        raise ValueError("projection.pt basis columns are not orthonormal")
    return center.clone(), basis.clone()


def _check_age(age_years: object) -> None:
    if (isinstance(age_years, (bool, np.bool_)) or not isinstance(age_years, numbers.Real)
            or not math.isfinite(age_years) or not 6 <= age_years < 13):
        raise ValueError("age_years must be a finite number in [6, 13) (completed years 6-12)")


def _check_inputs(features: object, target_ids: object) -> None:
    if (not isinstance(features, np.ndarray) or features.dtype != np.float32 or features.ndim != 2
            or features.shape[0] < 1 or features.shape[1] != FEATURE_WIDTH):
        raise ValueError(f"features must be a nonempty float32 numpy array [N, {FEATURE_WIDTH}]")
    if not np.isfinite(features).all():
        raise ValueError("features must be finite")
    if (not isinstance(target_ids, np.ndarray) or not np.issubdtype(target_ids.dtype, np.integer)
            or target_ids.shape != (features.shape[0],)):
        raise ValueError("target_ids must be an integer (not bool) numpy array [N]")
    if ((target_ids < 0) | (target_ids >= len(PHONES))).any():
        raise ValueError(f"target_ids must be in 0..{len(PHONES) - 1}")


def _normalize(values: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (values - mean) / std  # float32 throughout


def _head_log_probs(model: MeanPoolPhoneRatingHead, inputs: np.ndarray, ids: torch.Tensor) -> np.ndarray:
    logits = []
    with torch.no_grad():
        for start in range(0, len(inputs), BATCH_SIZE):
            batch = torch.from_numpy(inputs[start:start + BATCH_SIZE]).unsqueeze(1)
            mask = torch.ones(batch.shape[:2], dtype=torch.bool)
            logits.append(model(batch, mask, ids[start:start + BATCH_SIZE].unsqueeze(1), mask)[:, 0, :])
        return torch.log_softmax(torch.cat(logits).to(torch.float64), dim=-1).numpy()


class ResearchMixture:
    """Equal-weight mixture of a scalar head and a PCA16+scalar head."""

    def __init__(self, scalar: tuple[MeanPoolPhoneRatingHead, np.ndarray, np.ndarray],
                 compact: tuple[MeanPoolPhoneRatingHead, np.ndarray, np.ndarray],
                 center: torch.Tensor, basis: torch.Tensor):
        self._scalar, self._scalar_mean, self._scalar_std = scalar
        self._compact, self._compact_mean, self._compact_std = compact
        self._center, self._basis = center, basis

    def _head_inputs(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        # Project in torch float64 to match the fitting recipe; numpy float64
        # matmul is not bitwise identical.
        targets = torch.from_numpy(features[:, :TARGET_WIDTH].astype(np.float64))
        projected = ((targets - self._center) @ self._basis).numpy().astype(np.float32)
        scalars = features[:, TARGET_WIDTH:]
        compact = np.concatenate((projected, scalars), axis=1)
        return (_normalize(scalars, self._scalar_mean, self._scalar_std),
                _normalize(compact, self._compact_mean, self._compact_std))

    def predict(self, features: np.ndarray, target_ids: np.ndarray, *, age_years: float) -> dict[str, object]:
        """Return one three-class mixture distribution per row, in input order."""
        _check_age(age_years)
        _check_inputs(features, target_ids)
        ids = torch.from_numpy(target_ids.astype(np.int64))
        previous_threads = torch.get_num_threads()
        torch.set_num_threads(THREADS)
        try:
            scalar_inputs, compact_inputs = self._head_inputs(features)
            log_scalar = _head_log_probs(self._scalar, scalar_inputs, ids)
            log_compact = _head_log_probs(self._compact, compact_inputs, ids)
        finally:
            torch.set_num_threads(previous_threads)
        log_probs = np.logaddexp(log_scalar, log_compact) - math.log(2.0)
        return {"probabilities": np.exp(log_probs), "logProbabilities": log_probs,
                "ageRangeYears": [6, 12], **{flag: False for flag in _FLAGS}}


def load_bundle(directory: str | os.PathLike[str], expected_manifest_sha256: str) -> ResearchMixture:
    """Verify all bundle bytes against the caller's manifest hash, then load on CPU."""
    if not isinstance(expected_manifest_sha256, str) or not _HEX.fullmatch(expected_manifest_sha256):
        raise ValueError("expected_manifest_sha256 must be 64 lowercase hex characters")
    root = Path(directory)
    try:
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"Bundle {root} must be a real directory, not a symlink")
        names = sorted(os.listdir(root))
        if names != sorted((MANIFEST, *FILE_NAMES)):
            raise ValueError(f"Bundle must contain exactly {MANIFEST} and {list(FILE_NAMES)}, found {names}")
        blobs = {}
        for name in names:
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Bundle file {name} must be a regular file, not a symlink")
            blobs[name] = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read bundle {root}: {exc}") from exc
    if hashlib.sha256(blobs[MANIFEST]).hexdigest() != expected_manifest_sha256:
        raise ValueError("manifest.json does not match expected_manifest_sha256")
    files = _parse_manifest(blobs[MANIFEST])["files"]
    for name in FILE_NAMES:
        if hashlib.sha256(blobs[name]).hexdigest() != files[name]:
            raise ValueError(f"{name} does not match its manifest hash")
    scalar = _load_head(blobs["scalar.pt"], "scalar.pt", SCALAR_WIDTH)
    compact = _load_head(blobs["compact.pt"], "compact.pt", PCA_WIDTH + SCALAR_WIDTH)
    center, basis = _load_projection(blobs["projection.pt"])
    return ResearchMixture(scalar, compact, center, basis)
