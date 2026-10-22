import unittest

import numpy as np

from multiphone_evidence_gate import assess, gated_targets


class EvidenceGateTests(unittest.TestCase):
    def posterior(self, token=0, frames=4):
        p = np.full((frames, 392), .001/391, dtype=np.float64)
        p[:, token] = .999
        return np.log(p).astype('<f4')

    def speech(self):
        return (np.arange(1600) % 11 - 5).astype(np.float32)/32768

    def test_constant_and_dc_inputs_withhold_even_if_recognizer_emits_phone(self):
        for value in (0., .1, -.5):
            decision = assess(np.full(1600, value), self.posterior(26))
            self.assertEqual(decision['status'], 'abstain')
            self.assertEqual(decision['reasons'], ['constant-waveform'])

    def test_blank_and_special_tokens_are_not_phone_evidence(self):
        for token in range(4):
            decision = assess(self.speech(), self.posterior(token))
            self.assertFalse(decision['ratingAvailable'])
            self.assertEqual(decision['recognizedPhoneTokens'], 0)

    def test_quiet_and_alternative_phone_evidence_not_rejected_as_wrong_speech(self):
        decision = assess(self.speech(), self.posterior(391))
        self.assertTrue(decision['ratingAvailable'])
        self.assertFalse(decision['promptMatchValidated'])
        self.assertFalse(decision['speechPresenceValidated'])

    def test_collapse_repeats_but_preserve_blank_separated_tokens(self):
        logp = self.posterior(26)
        logp[2] = self.posterior(0)[0]
        self.assertEqual(assess(self.speech(), logp)['recognizedPhoneTokens'], 2)

    def test_corrupt_data_is_error_not_semantic_abstention(self):
        for logp in (self.posterior(frames=3), self.posterior().astype(np.float64),
                     np.zeros((4, 392), dtype=np.float32), np.full((4, 392), np.nan, dtype=np.float32)):
            with self.assertRaises(ValueError): assess(np.zeros(1600), logp)
        with self.assertRaises(ValueError): assess(np.full(1600, np.nan), self.posterior())

    def test_no_scores_in_abstained_targets_and_input_unchanged(self):
        targets = [{'id': 'x', 'targetPhone': 'B', 'wordIndex': 0, 'phoneIndex': 0,
                    'subjectiveCorpusRatingProbabilities': [.01, .02, .97]}]
        rejected = gated_targets(targets, {'ratingAvailable': False})
        self.assertIsNone(rejected[0]['subjectiveCorpusRatingProbabilities'])
        self.assertEqual(targets[0]['subjectiveCorpusRatingProbabilities'], [.01, .02, .97])
        accepted = gated_targets(targets, {'ratingAvailable': True})
        self.assertEqual(accepted[0]['subjectiveCorpusRatingProbabilities'], [.01, .02, .97])


if __name__ == '__main__': unittest.main()
