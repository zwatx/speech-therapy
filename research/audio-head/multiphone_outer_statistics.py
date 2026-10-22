"""Paired speaker-stratified uncertainty for frozen development predictions.

Pure arrays and metadata: no files, fitting, model selection or data loading.
Intervals are descriptive conditional on selected pipelines, not independent
clinical validation or selection-adjusted generalization guarantees.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

SLICES = ("allAges", "ages6to12", "ages13to15", "ages16plus")
PROPER = ("macroTargetLogLoss", "perRaterLogLoss", "perRaterBrier", "meanRatingMAE")
EVENTS = ("rating0", "ratingBelow2")
RANKING = tuple(f"macroTarget.{event}.{metric}" for event in EVENTS for metric in ("auroc", "averagePrecision"))
METRICS = PROPER + RANKING


def require(condition, message):
    if not condition:
        raise ValueError(message)


def age_slice(age):
    require(type(age) is int and age >= 6, "Expected an integer corpus age of at least six")
    return "ages6to12" if age <= 12 else "ages13to15" if age <= 15 else "ages16plus"


def validate_inputs(model_probabilities, rows, row_folds, reference_pairs):
    require(bool(rows) and bool(model_probabilities), "Rows and at least one model are required")
    counts = np.asarray([row["raterCounts"] for row in rows], dtype=np.float64)
    require(counts.shape == (len(rows), 3) and np.isfinite(counts).all()
            and (counts >= 0).all() and (counts == np.floor(counts)).all() and (counts.sum(1) == 5).all(),
            "Every row must retain exactly five nonnegative integer ratings")
    require(len({row["id"] for row in rows}) == len(rows), "Duplicate target row identity")
    require(len(row_folds) == len(rows) and all(type(f) is int and f in range(5) for f in row_folds),
            "One declared outer fold is required per row")
    speakers, clips = {}, {}
    for row, fold in zip(rows, row_folds, strict=True):
        require(isinstance(row["speakerId"], str) and isinstance(row["targetPhone"], str)
                and bool(row["speakerId"]) and bool(row["targetPhone"]), "Speaker and target identities must be named")
        stratum = (fold, age_slice(row["age"]))
        require(row["speakerId"] not in speakers or speakers[row["speakerId"]] == (row["age"], stratum),
                "A speaker spans outer folds or ages")
        speakers[row["speakerId"]] = (row["age"], stratum)
        require(row["clipId"] not in clips or clips[row["clipId"]] == row["speakerId"],
                "A waveform spans speakers")
        clips[row["clipId"]] = row["speakerId"]
    require(len(speakers) >= 2, "Speaker uncertainty requires at least two speakers")
    probabilities = {}
    for name, values in model_probabilities.items():
        p = np.asarray(values, dtype=np.float64)
        require(isinstance(name, str) and name and p.shape == counts.shape
                and np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all()
                and np.allclose(p.sum(1), 1., rtol=0, atol=1e-6),
                "Invalid aligned model probabilities")
        probabilities[name] = p
    require(set(reference_pairs).issubset(probabilities), "Unknown model in reference pairs")
    for model, references in reference_pairs.items():
        require(isinstance(references, (list, tuple)) and len(set(references)) == len(references)
                and set(references).issubset(probabilities), f"Unknown or duplicate reference for {model}")
    return probabilities, counts, speakers


def speaker_bootstrap(speaker_metadata, replicates=2000, seed=20260926):
    """One multiplicity matrix shared by every model, reference and age slice."""
    require(type(replicates) is int and replicates > 0 and type(seed) is int and seed >= 0,
            "Use a positive replicate count and nonnegative integer seed")
    speakers = sorted(speaker_metadata)
    strata = {}
    for index, speaker in enumerate(speakers):
        strata.setdefault(speaker_metadata[speaker][1], []).append(index)
    rng = np.random.default_rng(seed)
    multiplicities = np.zeros((replicates, len(speakers)), dtype=np.int64)
    description = []
    for (fold, age), indices in sorted(strata.items()):
        n = len(indices)
        multiplicities[:, indices] = rng.multinomial(n, np.full(n, 1 / n), size=replicates)
        description.append({"outerFold": fold, "ageSlice": age, "speakers": n})
    return speakers, multiplicities, description


class RankGroups:
    """Sort once; evaluate tied-threshold ranking with batched cluster weights."""
    def __init__(self, scores, positive, negative, speaker_indices):
        scores, positive, negative = [np.asarray(x, dtype=np.float64) for x in (scores, positive, negative)]
        indices = np.asarray(speaker_indices)
        require(scores.ndim == 1 and len(scores) and scores.shape == positive.shape == negative.shape == indices.shape
                and all(np.isfinite(x).all() for x in (scores, positive, negative))
                and (positive >= 0).all() and (negative >= 0).all()
                and np.issubdtype(indices.dtype, np.integer) and (indices >= 0).all(), "Invalid rank groups")
        order = np.argsort(scores, kind="stable")
        self.starts = np.r_[0, np.flatnonzero(np.diff(scores[order])) + 1]
        self.positive, self.negative, self.speakers = positive[order], negative[order], indices[order]

    def evaluate(self, multiplicities, batch_size=64):
        weights = np.asarray(multiplicities, dtype=np.float64)
        require(weights.ndim == 2 and weights.shape[1] > self.speakers.max()
                and np.isfinite(weights).all() and (weights >= 0).all()
                and type(batch_size) is int and batch_size > 0, "Invalid cluster multiplicities")
        auc, ap = np.full(len(weights), np.nan), np.full(len(weights), np.nan)
        for start in range(0, len(weights), batch_size):
            stop = min(start + batch_size, len(weights))
            selected = weights[start:stop, self.speakers]
            pos = np.add.reduceat(selected * self.positive, self.starts, axis=1)
            neg = np.add.reduceat(selected * self.negative, self.starts, axis=1)
            tp, tn = pos.sum(1), neg.sum(1)
            numerator = (pos * (np.cumsum(neg, axis=1) - neg / 2)).sum(1)
            auc[start:stop] = np.divide(numerator, tp * tn, out=np.full(len(tp), np.nan), where=(tp > 0) & (tn > 0))
            descending_pos, descending_neg = pos[:, ::-1], neg[:, ::-1]
            cumulative_pos = np.cumsum(descending_pos, axis=1)
            cumulative_all = cumulative_pos + np.cumsum(descending_neg, axis=1)
            precision = np.divide(cumulative_pos, cumulative_all, out=np.zeros_like(cumulative_pos), where=cumulative_all > 0)
            # AP is algebraically defined for all-positive samples, but the
            # protocol requires both classes for any separation assessment.
            ap[start:stop] = np.divide((descending_pos * precision).sum(1), tp,
                                      out=np.full(len(tp), np.nan), where=(tp > 0) & (tn > 0))
        return auc, ap


def finite_or_none(value):
    return float(value) if np.isfinite(value) else None


def interval(point, values, minimum_valid_fraction=.95):
    values = np.asarray(values, dtype=np.float64)
    valid = values[np.isfinite(values)]
    minimum = math.ceil(minimum_valid_fraction * len(values))
    usable = np.isfinite(point) and len(valid) >= minimum
    return {"pointEstimate": finite_or_none(point), "validReplicates": int(len(valid)),
            "requestedReplicates": len(values), "minimumValidReplicates": minimum,
            "percentile95": np.quantile(valid, [.025, .975]).tolist() if usable else None,
            "intervalWithheld": not bool(usable)}


def support_for(rows, counts):
    return {"positions": len(rows), "speakers": len({r["speakerId"] for r in rows}),
            "clips": len({r["clipId"] for r in rows}), "observedRaterCounts": counts.sum(0).astype(int).tolist(),
            "mixedRaterPositions": int((np.count_nonzero(counts, axis=1) > 1).sum())}


def score_model(p, counts, phone_indices, speaker_indices, phones, weights, fixed_ranking, batch_size):
    """Return point+bootstrap vectors, and point metrics for every phone."""
    speaker_count, phone_count = weights.shape[1], len(phones)
    bins = phone_indices * speaker_count + speaker_indices
    cell_counts = np.bincount(bins, minlength=phone_count * speaker_count).reshape(phone_count, speaker_count)
    denominators = weights @ cell_counts.T
    full_support = (denominators > 0).all(1)
    totals = denominators.sum(1)
    truth = counts / 5
    row_metrics = np.column_stack((-(truth * np.log(p.clip(1e-12, 1))).sum(1),
                                   (p * p - 2 * p * truth).sum(1) + 1,
                                   np.abs((p - truth) @ np.array([0., 1., 2.]))))
    sums = [np.bincount(bins, weights=row_metrics[:, column], minlength=phone_count * speaker_count)
            .reshape(phone_count, speaker_count) for column in range(3)]
    weighted_sums = [weights @ matrix.T for matrix in sums]
    phone_nll = np.divide(weighted_sums[0], denominators, out=np.full_like(denominators, np.nan), where=denominators > 0)
    macro = np.full(len(weights), np.nan)
    macro[full_support] = phone_nll[full_support].mean(1)
    result = {"macroTargetLogLoss": macro,
              **{name: np.divide(value.sum(1), totals, out=np.full(len(weights), np.nan), where=totals > 0)
                 for name, value in zip(PROPER[1:], weighted_sums, strict=True)}}
    per_phone = {}
    for i, phone in enumerate(phones):
        per_phone[phone] = {"perRaterLogLoss": float(phone_nll[0, i]),
                            "perRaterBrier": float(weighted_sums[1][0, i] / denominators[0, i]),
                            "meanRatingMAE": float(weighted_sums[2][0, i] / denominators[0, i])}
    for event in EVENTS:
        macro_auc = np.zeros(len(weights))
        macro_ap = np.zeros(len(weights))
        valid = np.ones(len(weights), dtype=bool)
        eligible = fixed_ranking[event]
        for i, phone in enumerate(phones):
            selected = phone_indices == i
            q, c = p[selected], counts[selected]
            positive, negative = (c[:, 0], c[:, 1] + c[:, 2]) if event == "rating0" else (c[:, 0] + c[:, 1], c[:, 2])
            scores = q[:, 0] if event == "rating0" else q[:, 0] + q[:, 1]
            grouped = RankGroups(scores, positive, negative, speaker_indices[selected])
            auc, ap = grouped.evaluate(weights if phone in eligible else weights[:1], batch_size)
            per_phone[phone][event] = {"auroc": finite_or_none(auc[0]), "averagePrecision": finite_or_none(ap[0]),
                                      "positiveRaterWeight": float(positive.sum()), "negativeRaterWeight": float(negative.sum()),
                                      "prevalence": float(positive.sum() / (positive.sum() + negative.sum()))}
            if phone in eligible:
                valid &= np.isfinite(auc) & np.isfinite(ap)
                macro_auc += np.nan_to_num(auc)
                macro_ap += np.nan_to_num(ap)
        for metric, values in (("auroc", macro_auc), ("averagePrecision", macro_ap)):
            if eligible:
                values /= len(eligible)
                values[~valid] = np.nan
            else:
                values[:] = np.nan
            result[f"macroTarget.{event}.{metric}"] = values
    return result, per_phone


def compute_statistics(model_probabilities, rows, row_folds, reference_pairs=None, *, replicates=2000,
                       seed=20260926, batch_size=64):
    """Score aligned name→N×3 probabilities with caller-declared paired references.

    `rows` are original cohort dictionaries (id, speakerId, clipId, age,
    targetPhone, raterCounts); `row_folds` maps each corresponding row to its
    prediction's outer fold. The caller owns artifact/row-order verification.
    References may include all-age prior, full13, and the matched child prior;
    this function neither chooses references nor ranks candidate models.
    """
    reference_pairs = reference_pairs or {}
    probabilities, counts, metadata = validate_inputs(model_probabilities, rows, row_folds, reference_pairs)
    require(type(batch_size) is int and batch_size > 0, "Use a positive rank batch size")
    speakers, multiplicities, strata = speaker_bootstrap(metadata, replicates, seed)
    speaker_map = {name: i for i, name in enumerate(speakers)}
    speaker_indices = np.asarray([speaker_map[r["speakerId"]] for r in rows])
    # The first row obtains point estimates with exactly the same arithmetic.
    weights = np.vstack((np.ones(len(speakers)), multiplicities)).astype(np.float64)
    report = {"schemaVersion": 1, "rows": len(rows), "modelNames": list(probabilities), "referencePairs": reference_pairs,
              "bootstrap": {"replicates": replicates, "seed": seed, "unit": "speaker",
                            "stratification": "outer fold × ages6–12/13–15/16+", "strata": strata,
                            "pairedAcrossAllModels": True, "multiplicitiesSha256": hashlib.sha256(multiplicities.astype('<i8').tobytes()).hexdigest(),
                            "minimumValidFraction": .95, "fixedPhoneSets": True, "refittingPerformed": False},
              "slices": {}, "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "interpretation": "Descriptive development cross-fit; not independent nested validation or selection-adjusted intervals",
              "limitations": ["Architecture discovery used overlapping inner folds; training sets also overlap.",
                              "Intervals condition on these frozen models and corpus; they exclude model-selection and seed uncertainty.",
                              "Five-rater subjective canonical-position ratings are not produced-phone or clinical correctness labels.",
                              "Ages2–5 and a verified child speech-sound-disorder cohort are absent."]}
    for age in SLICES:
        keep = np.asarray([age == "allAges" or age_slice(row["age"]) == age for row in rows])
        selected_rows, c = [row for row, included in zip(rows, keep, strict=True) if included], counts[keep]
        phones = sorted({row["targetPhone"] for row in selected_rows})
        phone_map = {name: i for i, name in enumerate(phones)}
        phone_indices = np.asarray([phone_map[row["targetPhone"]] for row in selected_rows], dtype=int)
        per_phone_support = {phone: support_for([r for r in selected_rows if r["targetPhone"] == phone], c[phone_indices == i])
                             for i, phone in enumerate(phones)}
        fixed = {event: [phone for phone, support in per_phone_support.items()
                        if (support["observedRaterCounts"][0] > 0 and sum(support["observedRaterCounts"][1:]) > 0
                            if event == "rating0" else sum(support["observedRaterCounts"][:2]) > 0 and support["observedRaterCounts"][2] > 0)]
                 for event in EVENTS}
        section = {"support": support_for(selected_rows, c), "perPhoneSupport": per_phone_support,
                   "fixedProperPhones": phones, "fixedRankingPhones": fixed,
                   "excludedRankingPhones": {event: sorted(set(phones) - set(fixed[event])) for event in EVENTS},
                   "models": {}, "pairedDeltas": {}}
        draws = {}
        for model, p in probabilities.items():
            if selected_rows:
                values, per_phone = score_model(p[keep], c, phone_indices, speaker_indices[keep], phones, weights, fixed, batch_size)
            else:
                values, per_phone = {metric: np.full(replicates + 1, np.nan) for metric in METRICS}, {}
            draws[model] = values
            section["models"][model] = {"point": {metric: finite_or_none(value[0]) for metric, value in values.items()},
                                         "intervals": {metric: interval(value[0], value[1:]) for metric, value in values.items()},
                                         "perPhone": per_phone}
        for model, references in reference_pairs.items():
            section["pairedDeltas"][model] = {}
            for reference in references:
                section["pairedDeltas"][model][reference] = {
                    metric: interval(draws[model][metric][0] - draws[reference][metric][0],
                                     draws[model][metric][1:] - draws[reference][metric][1:]) for metric in METRICS}
        report["slices"][age] = section
    return report
