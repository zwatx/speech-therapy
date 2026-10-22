"""Research-only exact-phrase admission layered over the frozen word policy.

A separately versioned research mode with no clinical, correctness or learner
meaning. The frozen single-word policy is called unchanged with the expected
transcript. For a multi-word expectation it can only return single_word_required
after every evidence, capture, speech, recognition and runtime check passed, so
that refusal alone opens the exact full-sequence comparison here; every other
refusal stays rejected. The expected phrase never reaches recognition.
"""
import re
import unicodedata

from common import PHONES, VOWELS, Refused, canonical, require, sha

__all__ = ("BASE_WORD_POLICY_SHA", "PHRASE_POLICY", "PHRASE_POLICY_SHA", "Refused",
           "decide", "normalize_phrase", "validate_phrase_prompt")

BASE_WORD_POLICY_SHA = "33b4a2598c1700d2d88ded58fbe369bed4bca71d63fbff6a1beb191cc6e9cf49"
PHRASE_POLICY = {
    "id": "research-phrase-admission-v1",
    "researchOnly": True,
    "learnerFeedbackEligible": False,
    "baseWordPolicySha256": BASE_WORD_POLICY_SHA,
    "baseRefusalOpeningComparison": "single_word_required",
    "method": "independent-asr-exact-phrase",
    "comparison": "exact-normalized-full-word-sequence",
    "normalization": "whitespace-split-edge-unicode-punctuation-trim-ascii-only-casefold",
    "wordPattern": "[a-z]+(?:['-][a-z]+)*",
    "punctuationOnlyTokens": "reject",
    "aliases": {},
    "synonyms": False,
    "contractionExpansion": False,
    "approximateMatching": False,
    "minimumWords": 2,
    "maximumWords": 8,
    "maximumTextCharacters": 256,
    "maximumWordCharacters": 64,
    "maximumPhones": 512,
    "maximumTargets": 512,
    "maximumTargetIdCharacters": 128,
}
PHRASE_POLICY_SHA = sha(canonical(PHRASE_POLICY))

WORD_FORM = re.compile(PHRASE_POLICY["wordPattern"])
PROMPT_WORD = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
VOWEL_PHONE = re.compile(r"(?:" + "|".join(sorted(VOWELS)) + r")[012]?")
HEX_SHA = re.compile(r"[0-9a-f]{64}")
BASE_DECISION_KEYS = frozenset(("admitted", "reason", "expectedWordSha256", "evidenceSha256", "policySha256",
                                "method", "requestedWordVerified", "recognitionRejectionIsArticulationError"))


def normalize_phrase(value):
    """Return the normalized word tuple, or None. Never raises; never deletes tokens."""
    if type(value) is not str or len(value) > PHRASE_POLICY["maximumTextCharacters"]:
        return None
    words = []
    for token in value.split():
        start, end = 0, len(token)
        while start < end and unicodedata.category(token[start]).startswith("P"):
            start += 1
        while end > start and unicodedata.category(token[end - 1]).startswith("P"):
            end -= 1
        # A punctuation-only token empties here and refuses the whole phrase.
        # Non-ASCII refuses before casefold could fold it into ASCII letters.
        word = token[start:end]
        if not word or not word.isascii():
            return None
        word = word.casefold()
        if len(word) > PHRASE_POLICY["maximumWordCharacters"] or WORD_FORM.fullmatch(word) is None:
            return None
        words.append(word)
    if not PHRASE_POLICY["minimumWords"] <= len(words) <= PHRASE_POLICY["maximumWords"]:
        return None
    return tuple(words)


def validate_phrase_prompt(prompt):
    """Validate an existing schema-2 prompt of 2-8 words; return it unchanged."""
    require(type(prompt) is dict and set(prompt) == {"schemaVersion", "language", "transcript", "words", "targets"}
            and type(prompt["schemaVersion"]) is int and prompt["schemaVersion"] == 2
            and type(prompt["language"]) is str and prompt["language"] == "en", "invalid_prompt_schema")
    words = prompt["words"]
    require(type(words) is list and PHRASE_POLICY["minimumWords"] <= len(words) <= PHRASE_POLICY["maximumWords"],
            "invalid_phrase_word_count")
    total = 0
    for word in words:
        require(type(word) is dict and set(word) == {"text", "phones"} and type(word["text"]) is str
                and len(word["text"]) <= PHRASE_POLICY["maximumWordCharacters"]
                and PROMPT_WORD.fullmatch(word["text"]) is not None, "invalid_expected_word")
        phones = word["phones"]
        require(type(phones) is list and 1 <= len(phones)
                and total + len(phones) <= PHRASE_POLICY["maximumPhones"], "invalid_canonical_phones")
        total += len(phones)
        for phone in phones:
            require(type(phone) is str and (phone in PHONES or phone == "ZH"
                    or VOWEL_PHONE.fullmatch(phone) is not None), "invalid_canonical_phone")
    transcript = prompt["transcript"]
    require(type(transcript) is str and transcript == " ".join(word["text"] for word in words),
            "transcript_word_list_mismatch")
    require(normalize_phrase(transcript) is not None, "invalid_phrase_text")
    targets = prompt["targets"]
    require(type(targets) is list and 1 <= len(targets) <= PHRASE_POLICY["maximumTargets"], "invalid_targets")
    ids, positions = set(), set()
    for target in targets:
        require(type(target) is dict and set(target) == {"id", "wordIndex", "phoneIndex", "targetPhone"},
                "invalid_target")
        identifier, word_index, phone_index = target["id"], target["wordIndex"], target["phoneIndex"]
        require(type(identifier) is str and 1 <= len(identifier) <= PHRASE_POLICY["maximumTargetIdCharacters"]
                and identifier.isprintable() and identifier not in ids, "duplicate_or_invalid_target_id")
        # type() is int refuses booleans as indices.
        require(type(word_index) is int and 0 <= word_index < len(words)
                and type(phone_index) is int and 0 <= phone_index < len(words[word_index]["phones"])
                and (word_index, phone_index) not in positions, "duplicate_or_invalid_target_position")
        require(type(target["targetPhone"]) is str and target["targetPhone"] in PHONES, "unsupported_target")
        require(words[word_index]["phones"][phone_index] == target["targetPhone"], "target_position_mismatch")
        ids.add(identifier)
        positions.add((word_index, phone_index))
    return prompt


def _pinned(policy):
    # Verify the live frozen POLICY bytes too, not only the module's own claim.
    try:
        return (type(getattr(policy, "POLICY_SHA", None)) is str and policy.POLICY_SHA == BASE_WORD_POLICY_SHA
                and sha(canonical(policy.POLICY)) == BASE_WORD_POLICY_SHA and callable(policy.decide))
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError):
        return False


def _checked(base):
    require(type(base) is dict and set(base) == BASE_DECISION_KEYS
            and base["policySha256"] == BASE_WORD_POLICY_SHA and base["method"] == "independent-asr-single-word"
            and base["requestedWordVerified"] is False and base["recognitionRejectionIsArticulationError"] is False
            and type(base["admitted"]) is bool
            and (base["reason"] is None if base["admitted"] else type(base["reason"]) is str)
            and all(base[key] is None or (type(base[key]) is str and HEX_SHA.fullmatch(base[key]) is not None)
                    for key in ("expectedWordSha256", "evidenceSha256")), "base_policy_contract_violated")
    return dict(base)


def _sealed_transcript(evidence, evidence_sha):
    """Read the transcript only from evidence still matching the verified seal."""
    try:
        if type(evidence) is not dict or type(evidence_sha) is not str or evidence.get("evidenceSha256") != evidence_sha:
            return False, None
        body = {key: value for key, value in evidence.items() if key != "evidenceSha256"}
        recognition = body.get("recognition")
        if (sha(canonical(body)) != evidence_sha or body.get("status") != "recognized"
                or type(recognition) is not dict or "transcript" not in recognition):
            return False, None
        return True, recognition["transcript"]
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return False, None


def _decision(base, admitted, reason):
    decision = {"admitted": admitted, "reason": reason,
                "phrasePolicySHA256": PHRASE_POLICY_SHA, "baseWordPolicySHA256": BASE_WORD_POLICY_SHA,
                "evidenceSHA256": base["evidenceSha256"], "method": PHRASE_POLICY["method"],
                "requestedPhraseVerified": False, "recognitionRejectionIsArticulationError": False,
                "researchOnly": True, "learnerFeedbackEligible": False, "baseWordDecision": base}
    decision["decisionSHA256"] = sha(canonical(decision))
    return decision


def decide(evidence, prompt, policy):
    """Return a separately hashed research phrase decision; never a learner verdict.

    Prompt or policy faults raise Refused with a fixed tag. Evidence faults are
    the frozen policy's own refusals, preserved under baseWordDecision.
    """
    validate_phrase_prompt(prompt)
    require(_pinned(policy), "base_policy_mismatch")
    base = _checked(policy.decide(evidence, prompt["transcript"]))
    if base["admitted"]:
        return _decision(base, False, "unexpected_base_admission")
    if base["reason"] != PHRASE_POLICY["baseRefusalOpeningComparison"]:
        return _decision(base, False, base["reason"])
    sealed, transcript = _sealed_transcript(evidence, base["evidenceSha256"])
    if not sealed:
        return _decision(base, False, "invalid_evidence")
    actual, expected = normalize_phrase(transcript), normalize_phrase(prompt["transcript"])
    if actual is None or expected is None:
        return _decision(base, False, "phrase_normalization_failed")
    if actual != expected:
        return _decision(base, False, "requested_phrase_not_matched")
    return _decision(base, True, None)
