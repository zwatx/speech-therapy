"""Generated-double tests for the research phrase admission mode.

Evidence here is invented and sealed locally. It drives the REAL frozen word
policy's integrity checks but is not accuracy evidence: no audio, media, model
files or inference are read or run.
"""
import copy
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for entry in (str(HERE.parents[1] / "assessment-admission"), str(HERE)):
    while entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)

from admission import policy as base_policy
from admission.models import MODEL_MANIFEST_SHA
from common import Refused, canonical, sha, validate_prompt
from phrase_admission import (BASE_WORD_POLICY_SHA, PHRASE_POLICY, PHRASE_POLICY_SHA, decide,
                              normalize_phrase, validate_phrase_prompt)

EXPECTED_BASE_SHA = "33b4a2598c1700d2d88ded58fbe369bed4bca71d63fbff6a1beb191cc6e9cf49"
AUDIO_SHA = sha(b"invented-audio-double")
SAMPLES = 16000
PHRASE = "purple giraffe"
DECISION_KEYS = {"admitted", "reason", "phrasePolicySHA256", "baseWordPolicySHA256", "evidenceSHA256", "method",
                 "requestedPhraseVerified", "recognitionRejectionIsArticulationError", "researchOnly",
                 "learnerFeedbackEligible", "baseWordDecision", "decisionSHA256"}
LEAK_KEYS = {"transcript", "tokenId", "selectedTokenPosteriors", "recognition"}


def make_prompt(words, targets):
    return {"schemaVersion": 2, "language": "en", "transcript": " ".join(text for text, _ in words),
            "words": [{"text": text, "phones": list(phones)} for text, phones in words],
            "targets": [{"id": identifier, "wordIndex": word, "phoneIndex": phone, "targetPhone": target}
                        for identifier, word, phone, target in targets]}


def giraffe():
    return make_prompt([("purple", ("P", "ER1", "P", "AH0", "L")), ("giraffe", ("JH", "ER0", "AE1", "F"))],
                       [("p-first", 0, 0, "P"), ("p-second", 0, 2, "P"), ("l", 0, 4, "L"),
                        ("jh", 1, 0, "JH"), ("f", 1, 3, "F")])


def dont_stop():
    return make_prompt([("don't", ("D", "OW1", "N", "T")), ("stop", ("S", "T", "AA1", "P"))],
                       [("d", 0, 0, "D"), ("s", 1, 0, "S")])


def red_yoyo():
    return make_prompt([("red", ("R", "EH1", "D")), ("yo-yo", ("Y", "OW1", "Y", "OW2"))],
                       [("r", 0, 0, "R"), ("y", 1, 2, "Y")])


def big_red_ball():
    return make_prompt([("big", ("B", "IH1", "G")), ("red", ("R", "EH1", "D")), ("ball", ("B", "AO1", "L"))],
                       [("b-big", 0, 0, "B"), ("b-ball", 2, 0, "B"), ("l", 2, 2, "L")])


def lazy_lion():
    return make_prompt([("lazy", ("L", "EY1", "Z", "IY0")), ("lion", ("L", "AY1", "AH0", "N"))],
                       [("lion-l", 1, 0, "L"), ("lazy-l", 0, 0, "L"), ("lazy-z", 0, 2, "Z"), ("lion-n", 1, 3, "N")])


def evidence_body(transcript, *, log_probabilities=(-0.1, -0.25, -0.15, -0.05, -0.3), speech=0.9, no_speech=0.02):
    """Invented, internally consistent evidence; a double, not a recording."""
    window, threshold = base_policy.POLICY["vadWindowSamples"], base_policy.POLICY["vadThreshold"]
    probabilities = [speech] * ((SAMPLES + window - 1) // window)
    positive = consecutive = longest = 0
    for index, probability in enumerate(probabilities):
        count = min(window, SAMPLES - index * window)
        if probability >= threshold:
            positive += count
            consecutive += count
            longest = max(longest, consecutive)
        else:
            consecutive = 0
    passed = (positive >= base_policy.POLICY["minimumPositiveSamples"]
              and longest >= base_policy.POLICY["minimumConsecutivePositiveSamples"])
    posteriors = [{"tokenId": 1000 + 17 * index, "selectedLogProbability": value}
                  for index, value in enumerate(log_probabilities)]
    mean = sum(token["selectedLogProbability"] for token in posteriors) / len(posteriors)
    return {
        "schemaVersion": 1, "status": "recognized", "reason": None,
        "capture": {"audioSha256": AUDIO_SHA, "valid": True,
                    "metrics": {"sampleCount": SAMPLES, "durationMilliseconds": SAMPLES / 16,
                                "rms": 0.08, "peak": 0.5, "railSamples": 0}},
        "speechEvidence": {"method": "silero-vad", "passed": passed, "positiveSamples": positive,
                           "maximumConsecutivePositiveSamples": longest, "windowCount": len(probabilities),
                           "probabilities": probabilities, "speechPresenceVerified": False},
        "recognition": {"method": "whisper-base.en", "transcript": transcript, "meanTokenLogProbability": mean,
                        "noSpeechProbability": no_speech, "complete": True, "endTokenId": 50256,
                        "generatedTokenCount": len(posteriors) + 1, "selectedTokenPosteriors": posteriors,
                        "requestedWordVerified": False},
        "binding": {"audioSha256": AUDIO_SHA, "modelManifestSha256": MODEL_MANIFEST_SHA,
                    "policySha256": base_policy.POLICY_SHA},
        "runtime": {"elapsedSeconds": 1.25, "peakRssKiB": 250000, "workerExitCode": 0, "timedOut": False,
                    "acousticCalls": 1},
        "claimLimits": dict(base_policy.CLAIMS),
    }


def seal(body):
    return {**body, "evidenceSha256": base_policy.digest(body)}


def make_evidence(transcript, change=None, **options):
    body = evidence_body(transcript, **options)
    if change is not None:
        change(body)
    return seal(body)


def setting(section, **values):
    def change(body):
        (body if section is None else body[section]).update(values)
    return change


def shifted_mean(body):
    body["recognition"]["meanTokenLogProbability"] += 0.01


def altered_after_seal():
    evidence = make_evidence("orange giraffe")
    evidence["recognition"]["transcript"] = PHRASE
    return evidence


def refusal_cases():
    return [
        ("low_confidence", make_evidence(PHRASE, log_probabilities=(-1.2, -1.5, -0.9)), "recognition_uncertain"),
        ("no_speech_probability", make_evidence(PHRASE, no_speech=0.9), "recognition_uncertain"),
        ("missing_eos", make_evidence(PHRASE, setting("recognition", complete=False)), "recognition_incomplete"),
        ("wrong_end_token", make_evidence(PHRASE, setting("recognition", endTokenId=50255)), "recognition_incomplete"),
        ("vad_not_passed", make_evidence(PHRASE, speech=0.1), "speech_not_detected"),
        ("silence", make_evidence(PHRASE, setting(None, status="rejected", reason="silence")), "silence"),
        ("clipping", make_evidence(PHRASE, setting(None, status="rejected", reason="clipping")), "clipping"),
        ("worker_timeout", make_evidence(PHRASE, setting(None, status="failed", reason="worker_timeout")),
         "worker_timeout"),
        ("model_unavailable", make_evidence(PHRASE, setting(None, status="failed", reason="model_unavailable")),
         "model_unavailable"),
        ("runtime_timed_out", make_evidence(PHRASE, setting("runtime", timedOut=True)), "invalid_evidence"),
        ("worker_exit_code", make_evidence(PHRASE, setting("runtime", workerExitCode=1)), "invalid_evidence"),
        ("second_acoustic_call", make_evidence(PHRASE, setting("runtime", acousticCalls=2)), "invalid_evidence"),
        ("capture_invalid", make_evidence(PHRASE, setting("capture", valid=False)), "invalid_evidence"),
        ("rail_samples", make_evidence(PHRASE, lambda body: body["capture"]["metrics"].update(railSamples=1)),
         "invalid_evidence"),
        ("wrong_model_sha", make_evidence(PHRASE, setting("binding", modelManifestSha256="0" * 64)),
         "invalid_evidence"),
        ("wrong_bound_policy_sha", make_evidence(PHRASE, setting("binding", policySha256="1" * 64)),
         "invalid_evidence"),
        ("audio_binding_mismatch", make_evidence(PHRASE, setting("binding", audioSha256=sha(b"other"))),
         "invalid_evidence"),
        ("claim_limits_widened", make_evidence(PHRASE, setting("claimLimits", learnerFeedbackEligible=True)),
         "invalid_evidence"),
        ("token_posterior_average", make_evidence(PHRASE, shifted_mean), "invalid_evidence"),
        ("recognized_with_reason", make_evidence(PHRASE, setting(None, reason="silence")), "invalid_evidence"),
        ("altered_after_seal", altered_after_seal(), "invalid_evidence"),
        ("unsealed", evidence_body(PHRASE), "invalid_evidence"),
        ("not_a_mapping", None, "invalid_evidence"),
    ]


def walk(value):
    yield value
    if type(value) is dict:
        for key, item in value.items():
            yield key
            yield from walk(item)
    elif type(value) is list:
        for item in value:
            yield from walk(item)


class RefusalAssertions(unittest.TestCase):
    def assertRefused(self, tag, function, *arguments):
        with self.assertRaises(Refused) as caught:
            function(*arguments)
        self.assertEqual(str(caught.exception), tag)


class NormalizationTests(unittest.TestCase):
    def test_normalizes_case_whitespace_and_edge_punctuation(self):
        self.assertEqual(normalize_phrase("Purple Giraffe"), ("purple", "giraffe"))
        self.assertEqual(normalize_phrase("  PURPLE\tgiraffe!\n"), ("purple", "giraffe"))
        self.assertEqual(normalize_phrase("\u201cPurple, giraffe\u2026\u201d"), ("purple", "giraffe"))
        self.assertEqual(normalize_phrase("\u00abpurple giraffe?\u00bb"), ("purple", "giraffe"))
        self.assertEqual(normalize_phrase("'Quoted' words"), ("quoted", "words"))

    def test_preserves_contractions_and_hyphens_without_expansion_or_aliases(self):
        self.assertEqual(normalize_phrase("Don't stop"), ("don't", "stop"))
        self.assertEqual(normalize_phrase("do not stop"), ("do", "not", "stop"))
        self.assertEqual(normalize_phrase("Red yo-yo."), ("red", "yo-yo"))
        self.assertEqual(normalize_phrase("rock'n'roll music"), ("rock'n'roll", "music"))
        self.assertNotEqual(normalize_phrase("red yoyo"), normalize_phrase("red yo-yo"))

    def test_refuses_without_deleting_tokens_or_folding_non_ascii(self):
        for value in ("purple , giraffe", "purple - giraffe", "... purple giraffe", "purple giraff\u00e9",
                      "purple gira\ufb00e", "don\u2019t stop", "purple gira--ffe", "purple_giraffe now",
                      "purple 2 giraffes", "purple $giraffe", None, 7, b"purple giraffe", ["purple", "giraffe"]):
            with self.subTest(value=value):
                self.assertIsNone(normalize_phrase(value))

    def test_word_count_and_length_bounds(self):
        self.assertIsNone(normalize_phrase("purple"))
        self.assertIsNone(normalize_phrase("   "))
        self.assertEqual(len(normalize_phrase(" ".join(["tap"] * 8))), 8)
        self.assertIsNone(normalize_phrase(" ".join(["tap"] * 9)))
        self.assertEqual(normalize_phrase(PHRASE + " " * 242), ("purple", "giraffe"))
        self.assertIsNone(normalize_phrase(PHRASE + " " * 243))
        self.assertIsNone(normalize_phrase("g" * 65 + " giraffe"))


class PromptTests(RefusalAssertions):
    def test_accepts_repeated_targets_across_words_in_caller_order(self):
        prompt = lazy_lion()
        snapshot = copy.deepcopy(prompt)
        self.assertIs(validate_phrase_prompt(prompt), prompt)
        self.assertEqual(prompt, snapshot)
        self.assertEqual([target["id"] for target in prompt["targets"]], ["lion-l", "lazy-l", "lazy-z", "lion-n"])
        for factory in (giraffe, dont_stop, red_yoyo, big_red_ball):
            with self.subTest(prompt=factory.__name__):
                prompt = factory()
                self.assertIs(validate_phrase_prompt(prompt), prompt)

    def test_bounds(self):
        eight = make_prompt([("tap", ("T", "AE1", "P"))] * 8, [("t", 7, 0, "T")])
        self.assertIs(validate_phrase_prompt(eight), eight)
        nine = make_prompt([("tap", ("T", "AE1", "P"))] * 9, [("t", 8, 0, "T")])
        self.assertRefused("invalid_phrase_word_count", validate_phrase_prompt, nine)
        full = make_prompt([("bat", ("B",) * 256), ("cat", ("K",) * 256)],
                           [(f"t{word}-{phone}", word, phone, "BK"[word]) for word in range(2) for phone in range(256)])
        self.assertIs(validate_phrase_prompt(full), full)
        over_targets = copy.deepcopy(full)
        over_targets["targets"].append(dict(over_targets["targets"][0], id="extra"))
        self.assertRefused("invalid_targets", validate_phrase_prompt, over_targets)
        over_phones = make_prompt([("bat", ("B",) * 256), ("cat", ("K",) * 257)], [("b", 0, 0, "B")])
        self.assertRefused("invalid_canonical_phones", validate_phrase_prompt, over_phones)
        long_text = make_prompt([("g" * 64, ("G",))] * 4 + [("go", ("G",))], [("g", 0, 0, "G")])
        self.assertRefused("invalid_phrase_text", validate_phrase_prompt, long_text)

    def test_canonical_zh_and_vowels_are_not_targets(self):
        prompt = make_prompt([("measure", ("M", "EH1", "ZH", "ER0")), ("it", ("IH", "T"))],
                             [("m", 0, 0, "M"), ("t", 1, 1, "T")])
        self.assertIs(validate_phrase_prompt(prompt), prompt)
        for position, phone in ((2, "ZH"), (1, "EH1"), (3, "ER0")):
            with self.subTest(phone=phone):
                broken = copy.deepcopy(prompt)
                broken["targets"][0].update(phoneIndex=position, targetPhone=phone)
                self.assertRefused("unsupported_target", validate_phrase_prompt, broken)
        unstressed = make_prompt([("the", ("DH", "AH")), ("dog", ("D", "AO", "G"))], [("dh", 0, 0, "DH")])
        self.assertIs(validate_phrase_prompt(unstressed), unstressed)

    def test_malformed_prompts_refuse_with_safe_tags(self):
        cases = (
            ("invalid_prompt_schema", lambda p: p.update(extra=1)),
            ("invalid_prompt_schema", lambda p: p.update(schemaVersion=True)),
            ("invalid_prompt_schema", lambda p: p.update(schemaVersion=1)),
            ("invalid_prompt_schema", lambda p: p.update(language="EN")),
            ("invalid_prompt_schema", lambda p: p.pop("targets")),
            ("invalid_phrase_word_count", lambda p: p.update(words=p["words"][:1], transcript="purple")),
            ("invalid_phrase_word_count", lambda p: p.update(words=[])),
            ("invalid_phrase_word_count", lambda p: p.update(words=tuple(p["words"]))),
            ("invalid_expected_word", lambda p: p["words"][1].update(text="giraffe!")),
            ("invalid_expected_word", lambda p: p["words"][1].update(text="giraff\u00e9")),
            ("invalid_expected_word", lambda p: p["words"][1].update(text="'giraffe")),
            ("invalid_expected_word", lambda p: p["words"][1].update(text="gira--ffe")),
            ("invalid_expected_word", lambda p: p["words"][1].update(text="g" * 65)),
            ("invalid_expected_word", lambda p: p["words"][1].update(extra=[])),
            ("invalid_canonical_phones", lambda p: p["words"][1].update(phones=[])),
            ("invalid_canonical_phones", lambda p: p["words"][1].update(phones=("JH",))),
            ("invalid_canonical_phone", lambda p: p["words"][1].update(phones=["JH", "AH3"])),
            ("invalid_canonical_phone", lambda p: p["words"][1].update(phones=["jh"])),
            ("invalid_canonical_phone", lambda p: p["words"][1].update(phones=["JH", 1])),
            ("transcript_word_list_mismatch", lambda p: p.update(transcript="purple  giraffe")),
            ("transcript_word_list_mismatch", lambda p: p.update(transcript="Purple giraffe")),
            ("transcript_word_list_mismatch", lambda p: p.update(transcript="giraffe purple")),
            ("transcript_word_list_mismatch", lambda p: p.update(transcript=["purple", "giraffe"])),
            ("invalid_targets", lambda p: p.update(targets=[])),
            ("invalid_target", lambda p: p["targets"][0].update(note="x")),
            ("duplicate_or_invalid_target_id", lambda p: p["targets"][1].update(id="p-first")),
            ("duplicate_or_invalid_target_id", lambda p: p["targets"][0].update(id="")),
            ("duplicate_or_invalid_target_id", lambda p: p["targets"][0].update(id="bad\nid")),
            ("duplicate_or_invalid_target_id", lambda p: p["targets"][0].update(id="i" * 129)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][1].update(phoneIndex=0)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][3].update(wordIndex=True)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][0].update(phoneIndex=False)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][0].update(wordIndex=0.0)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][3].update(wordIndex=2)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][4].update(phoneIndex=4)),
            ("duplicate_or_invalid_target_position", lambda p: p["targets"][0].update(phoneIndex=-1)),
            ("unsupported_target", lambda p: p["targets"][0].update(phoneIndex=1, targetPhone="ER1")),
            ("unsupported_target", lambda p: p["targets"][0].update(targetPhone="ZH")),
            ("target_position_mismatch", lambda p: p["targets"][0].update(targetPhone="L")),
        )
        for index, (tag, change) in enumerate(cases):
            with self.subTest(case=index, tag=tag):
                prompt = giraffe()
                change(prompt)
                self.assertRefused(tag, validate_phrase_prompt, prompt)


class DecisionTests(RefusalAssertions):
    def test_policies_are_pinned_and_separately_hashed(self):
        self.assertEqual(BASE_WORD_POLICY_SHA, EXPECTED_BASE_SHA)
        self.assertEqual(base_policy.POLICY_SHA, EXPECTED_BASE_SHA)
        self.assertEqual(sha(canonical(base_policy.POLICY)), EXPECTED_BASE_SHA)
        self.assertEqual(PHRASE_POLICY_SHA, sha(canonical(PHRASE_POLICY)))
        self.assertNotEqual(PHRASE_POLICY_SHA, EXPECTED_BASE_SHA)
        self.assertEqual(PHRASE_POLICY["baseWordPolicySha256"], EXPECTED_BASE_SHA)
        self.assertEqual(PHRASE_POLICY["aliases"], {})

    def test_exact_phrase_matching(self):
        cases = (
            (giraffe, "Purple giraffe.", None),
            (giraffe, "  PURPLE   Giraffe!  ", None),
            (giraffe, "\u201cPurple giraffe\u2026\u201d", None),
            (giraffe, "\u00a1Purple, giraffe!", None),
            (giraffe, "giraffe purple", "requested_phrase_not_matched"),
            (giraffe, "purple giraffe giraffe", "requested_phrase_not_matched"),
            (giraffe, "the purple giraffe", "requested_phrase_not_matched"),
            (giraffe, "purple giraffes", "requested_phrase_not_matched"),
            (giraffe, "Purple.", "phrase_normalization_failed"),
            (giraffe, "", "phrase_normalization_failed"),
            (giraffe, None, "phrase_normalization_failed"),
            (giraffe, "purple , giraffe", "phrase_normalization_failed"),
            (giraffe, "purple gira\ufb00e", "phrase_normalization_failed"),
            (giraffe, " ".join(["purple"] * 9), "phrase_normalization_failed"),
            (big_red_ball, "Big red ball!", None),
            (big_red_ball, "big ball", "requested_phrase_not_matched"),
            (big_red_ball, "big red red ball", "requested_phrase_not_matched"),
            (big_red_ball, "ball red big", "requested_phrase_not_matched"),
            (dont_stop, "Don't stop!", None),
            (dont_stop, "do not stop", "requested_phrase_not_matched"),
            (dont_stop, "dont stop", "requested_phrase_not_matched"),
            (dont_stop, "don\u2019t stop", "phrase_normalization_failed"),
            (red_yoyo, "Red yo-yo.", None),
            (red_yoyo, "red yoyo", "requested_phrase_not_matched"),
            (red_yoyo, "red yo yo", "requested_phrase_not_matched"),
            (lazy_lion, "Lazy lion.", None),
        )
        for factory, recognized, reason in cases:
            with self.subTest(prompt=factory.__name__, recognized=recognized):
                prompt = factory()
                evidence = make_evidence(recognized)
                result = decide(evidence, prompt, base_policy)
                self.assertEqual(result["baseWordDecision"], base_policy.decide(evidence, prompt["transcript"]))
                self.assertIs(result["baseWordDecision"]["admitted"], False)
                self.assertEqual(result["baseWordDecision"]["reason"], "single_word_required")
                self.assertIs(result["admitted"], reason is None)
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["evidenceSHA256"], evidence["evidenceSha256"])
                self.assertIs(result["requestedPhraseVerified"], False)

    def test_every_frozen_refusal_stays_rejected(self):
        for label, evidence, reason in refusal_cases():
            with self.subTest(case=label):
                result = decide(evidence, giraffe(), base_policy)
                self.assertEqual(result["baseWordDecision"], base_policy.decide(evidence, PHRASE))
                self.assertEqual(result["baseWordDecision"]["reason"], reason)
                self.assertNotEqual(reason, "single_word_required")
                self.assertIs(result["admitted"], False)
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["evidenceSHA256"], result["baseWordDecision"]["evidenceSha256"])

    def test_decision_shape_hash_and_no_recognized_text(self):
        evidence = make_evidence("Purple giraffe!")
        result = decide(evidence, giraffe(), base_policy)
        self.assertEqual(set(result), DECISION_KEYS)
        body = {key: value for key, value in result.items() if key != "decisionSHA256"}
        self.assertEqual(result["decisionSHA256"], sha(canonical(body)))
        self.assertEqual(result["phrasePolicySHA256"], PHRASE_POLICY_SHA)
        self.assertEqual(result["baseWordPolicySHA256"], EXPECTED_BASE_SHA)
        self.assertEqual(result["method"], "independent-asr-exact-phrase")
        self.assertIs(result["admitted"], True)
        self.assertIs(result["requestedPhraseVerified"], False)
        self.assertIs(result["recognitionRejectionIsArticulationError"], False)
        self.assertIs(result["researchOnly"], True)
        self.assertIs(result["learnerFeedbackEligible"], False)
        items = list(walk(result))
        self.assertFalse(LEAK_KEYS & {item for item in items if type(item) is str})
        self.assertFalse(any(type(item) is int for item in items))
        text = canonical(result).decode()
        for fragment in ("purple", "Purple", "giraffe"):
            self.assertNotIn(fragment, text)

    def test_frozen_policy_called_unchanged_with_expected_transcript_only(self):
        calls = []

        def recording(evidence, expected):
            calls.append((evidence, expected))
            return base_policy.decide(evidence, expected)

        double = types.SimpleNamespace(POLICY=base_policy.POLICY, POLICY_SHA=base_policy.POLICY_SHA, decide=recording)
        evidence, prompt = make_evidence(PHRASE), giraffe()
        result = decide(evidence, prompt, double)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], evidence)
        self.assertIs(calls[0][1], prompt["transcript"])
        self.assertIs(result["admitted"], True)

    def test_wrong_or_altered_base_policy_refuses(self):
        never = lambda *_: self.fail("frozen policy called")
        doubles = (
            types.SimpleNamespace(POLICY=base_policy.POLICY, POLICY_SHA="0" * 64, decide=never),
            types.SimpleNamespace(POLICY=dict(base_policy.POLICY, minimumMeanTokenLogProbability=-5.0),
                                  POLICY_SHA=base_policy.POLICY_SHA, decide=never),
            types.SimpleNamespace(POLICY=base_policy.POLICY, POLICY_SHA=base_policy.POLICY_SHA),
            types.SimpleNamespace(),
            None,
        )
        for index, double in enumerate(doubles):
            with self.subTest(policy=index):
                self.assertRefused("base_policy_mismatch", decide, make_evidence(PHRASE), giraffe(), double)
        broken = giraffe()
        broken["transcript"] = "giraffe purple"
        self.assertRefused("transcript_word_list_mismatch", decide, make_evidence(PHRASE), broken,
                           types.SimpleNamespace(POLICY=base_policy.POLICY, POLICY_SHA=base_policy.POLICY_SHA,
                                                 decide=never))

    def test_base_contract_violations(self):
        def double(function):
            return types.SimpleNamespace(POLICY=base_policy.POLICY, POLICY_SHA=base_policy.POLICY_SHA, decide=function)

        evidence = make_evidence(PHRASE)
        genuine = base_policy.decide(evidence, PHRASE)
        for index, bogus in enumerate((None, {"admitted": True}, dict(genuine, policySha256="0" * 64),
                                       dict(genuine, admitted=0), dict(genuine, transcript=PHRASE))):
            with self.subTest(case=index):
                self.assertRefused("base_policy_contract_violated", decide, evidence, giraffe(),
                                   double(lambda *_: bogus))
        admitted = dict(genuine, admitted=True, reason=None)
        result = decide(evidence, giraffe(), double(lambda *_: admitted))
        self.assertEqual((result["admitted"], result["reason"]), (False, "unexpected_base_admission"))
        opened = base_policy.decide(make_evidence("orange giraffe"), PHRASE)
        self.assertEqual(opened["reason"], "single_word_required")
        result = decide(altered_after_seal(), giraffe(), double(lambda *_: opened))
        self.assertEqual((result["admitted"], result["reason"]), (False, "invalid_evidence"))

    def test_inputs_not_mutated(self):
        evidence, prompt = make_evidence("Purple giraffe."), giraffe()
        before = copy.deepcopy((evidence, prompt))
        decide(evidence, prompt, base_policy)
        self.assertEqual((evidence, prompt), before)


class FrozenWordModeTests(RefusalAssertions):
    def test_single_word_validator_and_policy_unchanged(self):
        single = make_prompt([("red", ("R", "EH1", "D"))], [("r", 0, 0, "R")])
        self.assertIs(validate_prompt(single), single)
        decision = base_policy.decide(make_evidence("Red."), single["transcript"])
        self.assertEqual((decision["admitted"], decision["reason"]), (True, None))
        self.assertEqual(base_policy.decide(make_evidence("blue"), "red")["reason"], "requested_word_not_matched")
        self.assertRefused("single_word_required", validate_prompt, giraffe())
        refused = base_policy.decide(make_evidence(PHRASE), PHRASE)
        self.assertEqual((refused["admitted"], refused["reason"]), (False, "single_word_required"))
        self.assertRefused("invalid_phrase_word_count", validate_phrase_prompt, single)


if __name__ == "__main__":
    unittest.main()
