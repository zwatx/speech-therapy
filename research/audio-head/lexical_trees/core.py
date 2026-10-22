"""Fixed CatBoost learner kernels for the child scalar boosted-tree comparison.

The root orchestrator owns cell membership, stage evaluation, selection freezing
and refits. This module only builds features, vote copies, fits, predicts and
scores, with every recipe detail fixed by the declared protocol.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import catboost
import numpy as np
from catboost import CatBoostClassifier, Pool

PHONES = ["B", "P", "M", "T", "D", "N", "K", "G", "F", "V", "S", "Z",
          "SH", "CH", "JH", "L", "R", "W", "Y", "HH", "TH", "DH", "NG"]
STAGES = (25, 50, 100, 200, 400)
RECIPE = {
    "loss_function": "MultiClass",
    "classes_count": 3,
    "random_seed": 7,
    "learning_rate": 0.05,
    "l2_leaf_reg": 3.0,
    "bootstrap_type": "No",
    "boosting_type": "Plain",
    "grow_policy": "SymmetricTree",
    "random_strength": 0.0,
    "leaf_estimation_method": "Newton",
    "leaf_estimation_iterations": 1,
    "thread_count": 2,
    "use_best_model": False,
    "task_type": "CPU",
    "allow_writing_files": False,
    "verbose": False,
}
# Applied when learning borders from unexpanded rows; copies reuse the saved file.
QUANTIZATION = {"border_count": 64, "feature_border_type": "Median",
                "nan_mode": "Forbidden", "task_type": "CPU"}
CATBOOST_VERSION = "1.2.10"
CLASSES = [0, 1, 2]
N_SCALARS = 13
N_FEATURES = N_SCALARS + len(PHONES)
TOLERANCE = 1e-7


def _is_int(value):
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _check_x(x):
    if (not isinstance(x, np.ndarray) or x.dtype != np.float32 or x.ndim != 2
            or x.shape[1] != N_FEATURES or len(x) == 0):
        raise ValueError(f"x must be a nonempty float32[N, {N_FEATURES}] array")
    if not np.isfinite(x).all():
        raise ValueError("x must be finite")


def _check_classes(model):
    if not isinstance(model, CatBoostClassifier) or list(model.classes_) != CLASSES:
        raise ValueError(f"model classes must be exactly {CLASSES}")


def features(scalars, phone_ids):
    if (not isinstance(scalars, np.ndarray) or scalars.dtype != np.float32 or scalars.ndim != 2
            or scalars.shape[1] != N_SCALARS or len(scalars) == 0):
        raise ValueError(f"scalars must be a nonempty float32[N, {N_SCALARS}] array")
    if not np.isfinite(scalars).all():
        raise ValueError("scalars must be finite")
    if (not isinstance(phone_ids, np.ndarray) or phone_ids.dtype.kind not in "iu"
            or phone_ids.shape != (len(scalars),)):
        raise ValueError("phone_ids must be an integer array of shape [N]")
    if phone_ids.min() < 0 or phone_ids.max() >= len(PHONES):
        raise ValueError(f"phone_ids must be in 0..{len(PHONES) - 1}")
    onehot = np.eye(len(PHONES), dtype=np.float32)[phone_ids]
    return np.ascontiguousarray(np.concatenate([scalars, onehot], axis=1), dtype=np.float32)


def validate_counts(counts, n):
    if not _is_int(n) or n < 1:
        raise ValueError("n must be a positive integer")
    if not isinstance(counts, np.ndarray) or counts.dtype.kind not in "iu" or counts.shape != (n, 3):
        raise ValueError(f"counts must be an integer array of shape [{n}, 3]")
    counts = counts.astype(np.int64)
    if (counts < 0).any() or (counts.sum(axis=1) != 5).any():
        raise ValueError("counts must be nonnegative and sum to 5 per row")
    return counts


def expand_votes(x, counts):
    """One copy per positive vote count, class c, weight count[c]/5, row-major."""
    _check_x(x)
    counts = validate_counts(counts, len(x))
    rows, classes = np.nonzero(counts)
    weights = counts[rows, classes] / 5.0
    per_position = np.bincount(rows, weights=weights, minlength=len(x))
    if np.abs(per_position - 1.0).max() > 1e-15:
        raise AssertionError("per-position copy weights must sum to one")
    return x[rows], classes.astype(np.int64), weights.astype(np.float64), rows.astype(np.int64)


def fit_model(x, counts, output, *, depth, iterations):
    if not _is_int(depth) or depth not in (4, 6):
        raise ValueError("depth must be 4 or 6")
    if not _is_int(iterations) or not 1 <= iterations <= STAGES[-1]:
        raise ValueError(f"iterations must be an integer in 1..{STAGES[-1]}")
    _check_x(x)
    counts = validate_counts(counts, len(x))
    if not (counts.sum(axis=0) > 0).all():
        raise ValueError("every class needs at least one positive vote to fit")
    if catboost.__version__ != CATBOOST_VERSION:
        raise RuntimeError(f"expected CatBoost {CATBOOST_VERSION}, found {catboost.__version__}")
    output = Path(output)
    if output.exists():
        raise ValueError(f"output must be a fresh directory: {output}")
    output.mkdir(parents=True)

    # Borders come from unexpanded positions and are saved before copies exist.
    borders_path = output / "borders.tsv"
    border_pool = Pool(x)
    border_pool.quantize(**QUANTIZATION)
    border_pool.save_quantization_borders(str(borders_path))

    copies, labels, weights, _ = expand_votes(x, counts)
    pool = Pool(copies, label=labels, weight=weights)
    pool.quantize(input_borders=str(borders_path), nan_mode="Forbidden", task_type="CPU")
    model = CatBoostClassifier(iterations=iterations, depth=depth, **RECIPE)
    model.fit(pool)
    _check_classes(model)
    if model.tree_count_ != iterations:
        raise RuntimeError(f"expected {iterations} trees, got {model.tree_count_}")

    model_path = output / "model.cbm"
    model.save_model(str(model_path), format="cbm")
    (output / "parameters.json").write_text(
        json.dumps(model.get_all_params(), indent=2, sort_keys=True, default=str) + "\n")
    receipt = {
        "original_positions": len(x),
        "weighted_copies": len(labels),
        "total_weight": float(weights.sum()),
        "weight_by_class": np.bincount(labels, weights=weights, minlength=3).tolist(),
        "votes_by_class": counts.sum(axis=0).tolist(),
        "positions_by_class": (counts > 0).sum(axis=0).tolist(),
        "max_float32_weight_cast_error": float(
            np.abs(weights.astype(np.float32).astype(np.float64) - weights).max()),
        "class_order": list(CLASSES),
        "depth": depth,
        "iterations": iterations,
        "tree_count": int(model.tree_count_),
        "quantization": QUANTIZATION,
        "model_sha256": _sha256(model_path.read_bytes()),
        "borders_sha256": _sha256(borders_path.read_bytes()),
        "x_shape": list(x.shape),
        "x_sha256": _sha256(np.ascontiguousarray(x).tobytes()),
        "counts_sha256": _sha256(np.ascontiguousarray(counts).tobytes()),
        "versions": {"catboost": catboost.__version__, "numpy": np.__version__,
                     "python": sys.version.split()[0]},
    }
    (output / "fit.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return model, receipt


def log_probabilities(model, x, *, trees=None):
    _check_classes(model)
    _check_x(x)
    if trees is not None and (not _is_int(trees) or not 1 <= trees <= model.tree_count_):
        raise ValueError(f"trees must be None or an integer in 1..{model.tree_count_}")
    raw = model.predict(x, prediction_type="RawFormulaVal",
                        ntree_end=int(trees or 0), thread_count=2)
    raw = np.asarray(raw, dtype=np.float64)
    if raw.shape != (len(x), 3) or not np.isfinite(raw).all():
        raise RuntimeError(f"expected finite raw logits of shape {(len(x), 3)}, got {raw.shape}")
    shifted = raw - raw.max(axis=1, keepdims=True)
    return shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))


def nll(logp, counts):
    """Mean per-position five-vote soft-target NLL."""
    if (not isinstance(logp, np.ndarray) or logp.dtype != np.float64 or logp.ndim != 2
            or logp.shape[1] != 3 or len(logp) == 0):
        raise ValueError("logp must be a nonempty float64[N, 3] array")
    if not np.isfinite(logp).all():
        raise ValueError("logp must be finite")
    peak = logp.max(axis=1)
    if np.abs(peak + np.log(np.exp(logp - peak[:, None]).sum(axis=1))).max() > 1e-9:
        raise ValueError("logp rows must be normalized log-probabilities")
    counts = validate_counts(counts, len(logp))
    return float(np.mean(-(counts * logp).sum(axis=1) / 5.0))


def choose_stage(stage_losses):
    """Earliest stage unless a later one beats the incumbent by more than 1e-7."""
    if not isinstance(stage_losses, list) or len(stage_losses) != len(STAGES):
        raise ValueError(f"stage_losses must be a list of (stage, loss) for {STAGES}")
    best_stage = best_loss = None
    for entry, expected in zip(stage_losses, STAGES):
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError("each entry must be a (stage, loss) tuple")
        stage, loss = entry
        if not _is_int(stage) or stage != expected:
            raise ValueError(f"stages must be exactly {STAGES} in ascending order")
        if (isinstance(loss, (bool, np.bool_)) or not isinstance(loss, (int, float, np.integer, np.floating))
                or not math.isfinite(loss)):
            raise ValueError(f"loss for stage {stage} must be a finite number")
        if best_loss is None or loss < best_loss - TOLERANCE:
            best_stage, best_loss = int(stage), float(loss)
    return best_stage


def load_model(path):
    model = CatBoostClassifier()
    model.load_model(str(path), format="cbm")
    _check_classes(model)
    return model
