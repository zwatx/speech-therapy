import copy
import unittest

from speechocean_r_mispronunciation_audit import r_note, summarize


def utterance(phones, r_rating=2.0, note=None):
    ratings = [r_rating if phone == "R" else 2.0 for phone in phones]
    word = {"accuracy": 8, "stress": 10, "total": 8, "text": "WORD",
            "phones": phones, "phones-accuracy": ratings}
    if note is not None:
        word["mispronunciations"] = note
    aggregate = {"accuracy": 8, "completeness": 10, "fluency": 8, "prosodic": 8,
                 "total": 8, "text": "WORD", "words": [word]}
    annotation = []
    for phone in phones:
        if phone == "R" and r_rating == 0:
            annotation.append("(R)")
        elif phone == "R" and r_rating == 0.4:
            annotation.append("R")
        else:
            annotation.append(phone)
    if r_rating == 0.4:
        detailed_phones = [" ".join("(R)" if phone == "R" else phone for phone in phones)] * 4 + [" ".join(annotation)]
    else:
        detailed_phones = [" ".join(annotation)] * 5
    detailed = {"accuracy": [8] * 5, "completeness": [1] * 5,
                "fluency": [8] * 5, "prosodic": [8] * 5, "total": [8] * 5,
                "text": "WORD", "words": [{"text": "WORD", "ref-phones": " ".join(phones),
                                          "phones": detailed_phones}]}
    return aggregate, detailed


class MispronunciationAuditTests(unittest.TestCase):
    def test_one_r_selection_age_bands_and_threshold_equivalence(self):
        examples = [
            ("u1", "s1", 8, ["B", "R"], 0, [{"canonical-phone": "R", "index": 1, "pronounced-phone": "L"}]),
            ("u2", "s1", 8, ["B", "R"], 2, None),
            ("u3", "s2", 22, ["R", "AE1"], 0.4,
             [{"canonical-phone": "R", "index": 0, "pronounced-phone": "<unk>"}]),
            ("u4", "s2", 22, ["B", "AE1"], 2, None),
            ("u5", "s2", 22, ["R", "R"], 2, None),
        ]
        train, ages, aggregate, detailed = {}, {}, {}, {}
        for uid, speaker, age, phones, rating, note in examples:
            train[uid], ages[speaker] = speaker, str(age)
            aggregate[uid], detailed[uid] = utterance(phones, rating, note)
        result = summarize(train, ages, aggregate, detailed)
        self.assertEqual(result["selected"]["clips"], 3)
        self.assertEqual(result["selected"]["byAgeBand"]["child_15_or_younger"],
                         {"clips": 2, "speakers": 1})
        self.assertEqual(result["rPositionNotes"]["byAgeBand"]["adult_19_or_older"],
                         {"clips": 1, "speakers": 1})
        self.assertEqual(result["rPositionNotes"]["pronouncedPhoneDescriptions"],
                         {"<unk>": 1, "L": 1})
        self.assertEqual(result["noteVsScoreBelowHalf"],
                         {"both": 2, "note_only": 0, "low_score_only": 0, "neither": 1})
        self.assertTrue(result["notePresenceEquivalentToScoreBelowHalf"])
        self.assertNotIn("u1", str(result))

    def test_threshold_mismatch_is_reported_not_hidden(self):
        train, ages = {"u1": "s1", "u2": "s1"}, {"s1": "8"}
        a1, d1 = utterance(["R"], 0, None)
        a2, d2 = utterance(["R"], 2, [{"canonical-phone": "R", "index": 0,
                                      "pronounced-phone": "R*"}])
        result = summarize(train, ages, {"u1": a1, "u2": a2}, {"u1": d1, "u2": d2})
        self.assertEqual(result["noteVsScoreBelowHalf"]["low_score_only"], 1)
        self.assertEqual(result["noteVsScoreBelowHalf"]["note_only"], 1)
        self.assertFalse(result["notePresenceEquivalentToScoreBelowHalf"])

    def test_bad_index_canonical_and_duplicate_r_note_rejected(self):
        word = utterance(["B", "R"], 0)[0]["words"][0]
        valid = {"canonical-phone": "R", "index": 1, "pronounced-phone": "L"}
        for bad, message in (
            ({**valid, "index": 2}, "index"),
            ({**valid, "index": 0}, "canonical phone"),
            ({**valid, "canonical-phone": "L"}, "canonical phone"),
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, message):
                copy_word = copy.deepcopy(word)
                copy_word["mispronunciations"] = [bad]
                r_note(copy_word, 1)
        word["mispronunciations"] = [valid, valid]
        with self.assertRaisesRegex(ValueError, "Duplicate R-position"):
            r_note(word, 1)


if __name__ == "__main__":
    unittest.main()
