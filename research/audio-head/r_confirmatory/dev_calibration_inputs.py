"""Pure projection of caller-verified saved DEV summaries into calibration rows.

No files are opened here. The caller must verify each supplied binding's bytes
before invoking the adapter; matching in-memory pins cannot prove authenticity.
"""
import copy
from collections import Counter
import math
import re

PRODUCTION_COUNTS = {"devChildren": 119, "completeTokens": 4534, "excludedTokens": 5,
                     "selectedTokens": 4539, "testChildren": 80}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _child(value):
    return (type(value) is str and bool(value) and value.isascii() and value.isdecimal()
            and value[0] != "0")


def _roster(values, label):
    _require(type(values) is list and all(_child(value) for value in values),
             label + " requires canonical positive child IDs")
    _require(len(set(values)) == len(values), label + " has duplicate child IDs")
    return set(values)


def _unique(rows, label):
    _require(type(rows) is list, label + " requires rows")
    result = {}
    for row in rows:
        _require(type(row) is dict and type(row.get("tokenId")) is str
                 and bool(row["tokenId"].strip()), label + " requires nonblank token IDs")
        _require(row["tokenId"] not in result, "duplicate token ID in " + label)
        result[row["tokenId"]] = row
    return result


def _exclusions(value):
    _require(type(value) is dict and set(value) == {"unmappable", "belowReaderMinimum"},
             "invalid frozen exclusion categories")
    result = set()
    for rows in value.values():
        _require(type(rows) is list and all(type(token) is str and bool(token.strip()) for token in rows)
                 and len(rows) == len(set(rows)), "invalid frozen exclusion IDs")
        result.update(rows)
    return result


def _metadata(row):
    for field in ("study", "phase", "word", "context"):
        _require(type(row.get(field)) is str and bool(row[field].strip()), "invalid metadata: " + field)
    _require(row["context"] in ("intervocalic", "prevocalic", "postvocalic", "other"), "invalid context")
    _require(type(row.get("age")) is int and 6 <= row["age"] <= 12, "invalid age metadata")


def _probability(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def _retained_probability(prediction, record):
    values = prediction.get("probabilities")
    _require(type(values) is list and len(values) == 3 and all(_probability(value) for value in values),
             "invalid retained three-class probabilities")
    _require(abs(sum(values) - 1) <= 1e-6, "retained probabilities do not sum to one")
    retained = values[0] + values[1]
    _require(_probability(retained), "invalid retained p0+p1")
    for row in (prediction, record):
        score = row.get("scoreBelow2")
        _require(_probability(score) and abs(score - retained) <= 1e-12, "saved retained score differs")
    return retained


def _validate_lineage(artifacts, bindings):
    required = {"tokens", "extract", "predictions", "selection", "split", "closedDeclaration",
                "clips", "retention"}
    _require(type(bindings) is dict and set(bindings) == required, "unexpected input binding set")
    for binding in bindings.values():
        _require(type(binding) is dict and set(binding) == {"path", "sha256"}
                 and type(binding["path"]) is str and binding["path"].startswith("/")
                 and type(binding["sha256"]) is str
                 and re.fullmatch("[0-9a-f]{64}", binding["sha256"]) is not None,
                 "bindings require absolute paths and lowercase SHA256")
    for name in ("tokens", "extract", "predictions"):
        _require(artifacts[name].get("declaration") == bindings["closedDeclaration"],
                 "closed declaration binding differs: " + name)
    for name, keys in (("tokens", ("extract", "predictions", "retention")),
                       ("extract", ("clips",)), ("predictions", ("extract", "clips"))):
        _require(artifacts[name].get("upstream") == {key: bindings[key] for key in keys},
                 "upstream bindings differ: " + name)
    inputs = artifacts["closedDeclaration"].get("inputs")
    _require(type(inputs) is dict and all(inputs.get(key) == bindings[key] for key in ("selection", "split")),
             "closed input bindings differ")
    for flag in ("testPartitionTouched", "thresholdSelected", "trainingPerformed",
                 "clinicalUseEligible", "learnerFeedbackEligible"):
        _require(artifacts["tokens"].get(flag) is False, "closed evaluation flag differs: " + flag)
    _require(artifacts["predictions"].get("ratingsRead") is False, "prediction ratingsRead must be false")


def prepare_dev_calibration_inputs(artifacts, bindings, expected=None):
    """Return a calibration ``payload`` and private provenance ``receipt``.

    ``artifacts`` contains parsed tokens/extract/predictions/selection/split/
    closedDeclaration summaries, optionally clips. ``bindings`` contains exactly
    those six pins plus clips and retention; its bytes must already be verified
    by the caller. No retention contents, raw reports, features or audio are used.
    ``expected`` contains exactly the five PRODUCTION_COUNTS keys; omission uses
    production denominators, while explicit counts support synthetic tests.
    Children sort lexicographically, selectedTokens/rows by tokenId. Inputs are
    never changed. Malformed summaries raise ValueError without excluding rows.
    The private receipt records supplied pins, not a declaration or hash audit.
    """
    required = {"tokens", "extract", "predictions", "selection", "split", "closedDeclaration"}
    _require(type(artifacts) is dict and required <= set(artifacts) <= required | {"clips"}
             and all(type(value) is dict for value in artifacts.values()), "invalid artifact summary set")
    expected = PRODUCTION_COUNTS if expected is None else expected
    _validate_lineage(artifacts, bindings)
    _require(type(expected) is dict and set(expected) == set(PRODUCTION_COUNTS),
             "expected requires exactly the five denominator counts")
    _require(all(type(value) is int and value >= (0 if key == "excludedTokens" else 1)
                 for key, value in expected.items()), "invalid expected denominator counts")
    dev = _roster(artifacts["split"].get("dev"), "DEV")
    test = _roster(artifacts["split"].get("test"), "TEST")
    _require(not dev & test, "DEV and TEST children overlap")
    tokens = _unique(artifacts["tokens"].get("records"), "saved token report")
    selected = _unique(artifacts["selection"].get("part1"), "Part1 selection")
    extracts = _unique(artifacts["extract"].get("outcomes"), "extraction outcomes")
    predictions = _unique(artifacts["predictions"].get("rows"), "saved predictions")
    _require(all(row.get("state") in ("complete", "excluded") for row in extracts.values()),
             "all selected extraction outcomes must be complete or excluded")
    complete = {token for token, row in extracts.items() if row["state"] == "complete"}
    excluded = {token for token, row in extracts.items() if row["state"] == "excluded"}
    frozen_exclusions = artifacts["selection"].get("part1Excluded")
    _require(excluded == _exclusions(frozen_exclusions), "exclusions differ from frozen Part1 exclusions")
    for name in ("tokens", "closedDeclaration"):
        _require(artifacts[name].get("part1Excluded") == frozen_exclusions, "frozen exclusions differ: " + name)
    _require(complete == set(tokens) == set(predictions) and set(selected) == complete | excluded,
             "selection, extraction, saved token report and prediction coverage differs")
    if "clips" in artifacts:
        clips = artifacts["clips"]
        _require(clips.get("declaration") == bindings["closedDeclaration"], "clip declaration differs")
        clip_rows = _unique(clips.get("records"), "clip summary")
        _require(complete <= set(clip_rows)
                 and all(clip_rows[token].get("state") == "complete" for token in complete),
                 "complete DEV tokens lack complete saved clips")
    declared = artifacts["closedDeclaration"].get("part1")
    _require(type(declared) is list and all(type(token) is str for token in declared)
             and len(declared) == len(set(declared)) and set(declared) == set(selected),
             "closed declaration Part1 coverage differs")
    for row in selected.values():
        _metadata(row)
        _require(_child(row.get("speakerId")) and row["speakerId"] in dev,
                 "selection child must be in DEV")
    for token, row in tokens.items():
        _metadata(row)
        _require(all(row[field] == selected[token][field] for field in ("study", "phase", "word", "context", "age")),
                 "selection metadata differs")
        _require(_child(row.get("speakerId")) and row["speakerId"] == selected[token]["speakerId"],
                 "saved token child identity differs")
        _require(type(row.get("k")) is int and type(row.get("n")) is int
                 and row["n"] > 0 and 0 <= row["k"] <= row["n"], "invalid listener counts")
    _require({row["speakerId"] for row in tokens.values()} == dev, "complete rows must cover every DEV child")
    records = [tokens[token] for token in sorted(tokens)]
    children = sorted(artifacts["split"]["dev"])
    rows = [{"childId": row["speakerId"], "tokenId": row["tokenId"],
             "retainedProbability": _retained_probability(predictions[row["tokenId"]], row),
             "positiveVotes": row["n"] - row["k"],
             "negativeVotes": row["k"]} for row in records]
    excluded = sorted(excluded)
    observed = {"devChildren": len(children), "completeTokens": len(rows),
                "excludedTokens": len(excluded),
                "selectedTokens": len(artifacts["selection"]["part1"]), "testChildren": len(test)}
    _require(observed == expected, "full DEV denominator counts differ")
    return {"payload": {"children": [{"childId": child} for child in children],
                        "selectedTokens": [{"childId": row["childId"], "tokenId": row["tokenId"]}
                                           for row in rows], "rows": rows},
            "receipt": {"inputBindings": copy.deepcopy(bindings), "expectedCounts": dict(expected),
                        "schemaVersion": 1, "status": "prepared_from_caller_verified_saved_dev_summaries",
                        "observedCounts": observed,
                        "children": children, "completeTokenIds": sorted(complete),
                        "selectedTokenIds": sorted(selected),
                        "excludedTokenIds": excluded,
                        "frozenExclusions": copy.deepcopy(frozen_exclusions),
                        "childTokenCounts": dict(sorted(Counter(row["childId"] for row in rows).items())),
                        "clipSummarySupplied": "clips" in artifacts,
                        "researchOnly": True, "testPartitionTouched": False,
                        "calibrationFitPerformed": False, "clinicalUseEligible": False,
                        "learnerFeedbackEligible": False, "productionUseEligible": False,
                        "byteHashesVerifiedByAdapter": False,
                        "positiveVotes": sum(row["positiveVotes"] for row in rows),
                        "negativeVotes": sum(row["negativeVotes"] for row in rows)}}
