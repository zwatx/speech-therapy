"""Repeat-position masking regressions through the existing short filter."""
import copy
import json
import unittest
from test_multiphone_short_vad_filter import ShortFilterTests
from position_filter import study as s


class RepeatedFilterTests(ShortFilterTests):
    def setUp(self):
        super().setUp()
        self.original['schemaVersion']=2
        self.original['targets']=[dict(t,subjectiveCorpusRatingProbabilities=p) for t,p in zip(
            s.PROMPT['targets'],([.1,.2,.7],[.6,.1,.3],[.3,.2,.5]),strict=True)]
        self.source.write_text(json.dumps(self.original));self.sha=s.a.digest(self.source)

    def test_all_repeated_occurrences_withheld_and_order_preserved(self):
        result=self.exercise(phone=False)
        self.assertEqual([t['id'] for t in result['targets']],['last-b','first-b','middle-b'])
        self.assertTrue(all(t['subjectiveCorpusRatingProbabilities'] is None for t in result['targets']))
        s.check_targets(self.original['targets'],result['targets'],False)
        leaked=copy.deepcopy(result['targets']);leaked[1]['subjectiveCorpusRatingProbabilities']=[.6,.1,.3]
        with self.assertRaisesRegex(ValueError,'probability differs'):s.check_targets(self.original['targets'],leaked,False)

    def test_accepted_occurrences_cannot_be_reordered_or_collapsed(self):
        result=self.exercise();s.check_targets(self.original['targets'],result['targets'],True)
        with self.assertRaisesRegex(ValueError,'count'):s.check_targets(self.original['targets'],result['targets'][:1],True)
        with self.assertRaisesRegex(ValueError,'identity/order'):s.check_targets(self.original['targets'],result['targets'][::-1],True)

    def test_conjunction_never_invents_prompt_or_local_speech_validation(self):
        phone=dict(ratingAvailable=False,reasons=['no-recognized-phone-evidence'])
        decision=s.expected_decision(phone,[{'start':0,'end':8000}],'fixed')
        self.assertFalse(decision['ratingAvailable']);self.assertFalse(decision['speechPresenceValidated'])
        self.assertFalse(decision['promptMatchValidated']);self.assertFalse(decision['pronunciationCorrectnessValidated'])
        self.assertEqual(decision['reasons'],phone['reasons'])


if __name__=='__main__':unittest.main()
