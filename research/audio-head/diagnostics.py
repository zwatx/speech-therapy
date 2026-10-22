"""Descriptive alignment agreement, never pronunciation correctness or calibration.

Edit attribution is one deterministic minimum-edit alignment. Repeated phones
can admit multiple equally good alignments; prefer a diagonal, then deletion,
then insertion. Aggregate edit distance is unaffected by that tie policy.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence


def align_tokens(reference: Sequence[str], prediction: Sequence[str]) -> list[tuple[str, str | None, str | None]]:
    """Return (match/substitution/deletion/insertion, reference, prediction)."""
    costs = [list(range(len(prediction) + 1))]
    for i, actual in enumerate(reference, 1):
        row = [i]
        for j, guess in enumerate(prediction, 1):
            row.append(min(costs[i - 1][j - 1] + (actual != guess),
                           costs[i - 1][j] + 1, row[j - 1] + 1))
        costs.append(row)
    alignment = []
    i, j = len(reference), len(prediction)
    while i or j:
        if i and j and costs[i][j] == costs[i - 1][j - 1] + (reference[i - 1] != prediction[j - 1]):
            kind = "match" if reference[i - 1] == prediction[j - 1] else "substitution"
            alignment.append((kind, reference[i - 1], prediction[j - 1]))
            i, j = i - 1, j - 1
        elif i and costs[i][j] == costs[i - 1][j] + 1:
            alignment.append(("deletion", reference[i - 1], None))
            i -= 1
        else:
            alignment.append(("insertion", None, prediction[j - 1]))
            j -= 1
    return list(reversed(alignment))


def sequence_diagnostics(
    references: Sequence[Sequence[str]],
    predictions: Sequence[Sequence[str]],
    frame_indices: Sequence[Sequence[int]] | None = None,
    blank_id: int = 0,
) -> dict:
    """Summarize token agreement and raw greedy CTC blank occupancy by split.

    References may be automatic alignments. These values cannot be interpreted
    as independently annotated produced-phone accuracy or clinical error rates.
    """
    if len(references) != len(predictions) or not references:
        raise ValueError("Diagnostics require matching, nonempty sequence batches")
    for sequence in (*references, *predictions):
        if any(not isinstance(token, str) or not token for token in sequence):
            raise ValueError("Tokens must be nonempty strings")
    if isinstance(blank_id, bool) or not isinstance(blank_id, int) or blank_id < 0:
        raise ValueError("Blank ID must be a nonnegative integer")
    if frame_indices is not None:
        if len(frame_indices) != len(references) or any(not frames for frames in frame_indices):
            raise ValueError("Each sequence must have a nonempty frame path")
        if any(isinstance(token, bool) or not isinstance(token, int) or token < 0
               for frames in frame_indices for token in frames):
            raise ValueError("Frame paths must contain nonnegative integer token IDs")

    operations: Counter = Counter()
    support: Counter = Counter()
    phone_operations: dict[str, Counter] = {}
    confusions: Counter = Counter()
    inserted: Counter = Counter()
    for reference, prediction in zip(references, predictions):
        support.update(reference)
        for kind, actual, guess in align_tokens(reference, prediction):
            operations[kind] += 1
            if actual is not None:
                phone_operations.setdefault(actual, Counter())[kind] += 1
            if kind == "substitution":
                confusions[(actual, guess)] += 1
            elif kind == "insertion":
                inserted[guess] += 1
    reference_count = sum(map(len, references))
    prediction_count = sum(map(len, predictions))
    edits = sum(operations[kind] for kind in ("substitution", "deletion", "insertion"))
    result = {
        "referenceTokenCount": reference_count,
        "predictedTokenCount": prediction_count,
        "predictedToReferenceRatio": prediction_count / reference_count if reference_count else None,
        "matches": operations["match"],
        "substitutions": operations["substitution"],
        "deletions": operations["deletion"],
        "insertions": operations["insertion"],
        "tokenEdits": edits,
        "tokenErrorRate": edits / reference_count if reference_count else None,
        "emptyPredictions": sum(not prediction for prediction in predictions),
        "perReferenceToken": [
            {"token": token, "support": count, "matches": phone_operations[token]["match"],
             "substitutions": phone_operations[token]["substitution"],
             "deletions": phone_operations[token]["deletion"],
             "agreementRecall": phone_operations[token]["match"] / count}
            for token, count in sorted(support.items())
        ],
        "substitutionPairs": [
            {"reference": actual, "prediction": guess, "count": count}
            for (actual, guess), count in sorted(confusions.items(), key=lambda item: (-item[1], item[0]))
        ],
        "insertedTokens": [{"token": token, "count": count}
                           for token, count in sorted(inserted.items(), key=lambda item: (-item[1], item[0]))],
        "alignmentTiePolicy": "diagonal-then-deletion-then-insertion",
    }
    if frame_indices is not None:
        frame_count = sum(map(len, frame_indices))
        blank_count = sum(token == blank_id for frames in frame_indices for token in frames)
        result["greedyFrames"] = {"count": frame_count, "blankCount": blank_count,
                                  "blankFraction": blank_count / frame_count}
    return result
