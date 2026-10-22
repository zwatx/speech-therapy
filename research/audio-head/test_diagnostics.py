import itertools
import unittest

from diagnostics import align_tokens, sequence_diagnostics
from pipeline import edit_distance


class DiagnosticTests(unittest.TestCase):
    def test_edit_alignment_matches_distance_and_reconstructs_sequences(self):
        # Exhaust repeated phones, empty predictions, insertions, and tie cases.
        sequences = [list(value) for length in range(4)
                     for value in itertools.product(("a", "b"), repeat=length)]
        for reference in sequences:
            for prediction in sequences:
                alignment = align_tokens(reference, prediction)
                self.assertEqual([actual for _, actual, _ in alignment if actual is not None], reference)
                self.assertEqual([guess for _, _, guess in alignment if guess is not None], prediction)
                self.assertEqual(sum(kind != "match" for kind, _, _ in alignment),
                                 edit_distance(reference, prediction))

    def test_substitutions_deletions_insertions_and_blank_occupancy(self):
        result = sequence_diagnostics([["b", "ae", "t"], ["s"], ["a"]],
                                      [["p", "ae", "t"], [], ["a", "m"]],
                                      [[0, 1, 0, 2], [0, 0], [1, 0, 2]])
        self.assertEqual((result["substitutions"], result["deletions"], result["insertions"]), (1, 1, 1))
        self.assertEqual(result["tokenEdits"], 3)
        self.assertEqual(result["tokenErrorRate"], 3 / 5)
        self.assertEqual(result["emptyPredictions"], 1)
        self.assertEqual(result["substitutionPairs"], [{"reference": "b", "prediction": "p", "count": 1}])
        self.assertEqual(result["insertedTokens"], [{"token": "m", "count": 1}])
        self.assertEqual(result["greedyFrames"], {"count": 9, "blankCount": 5, "blankFraction": 5 / 9})
        by_phone = {row["token"]: row for row in result["perReferenceToken"]}
        self.assertEqual(by_phone["s"]["deletions"], 1)
        self.assertEqual(by_phone["b"]["agreementRecall"], 0)
        self.assertEqual(by_phone["ae"]["agreementRecall"], 1)

    def test_collapse_and_insertions_are_not_clamped(self):
        collapsed = sequence_diagnostics([["b", "a"]], [[]], [[0, 0]])
        self.assertEqual(collapsed["deletions"], 2)
        self.assertEqual(collapsed["greedyFrames"]["blankFraction"], 1)
        expanded = sequence_diagnostics([["b"]], [["a", "a", "a"]])
        self.assertEqual(expanded["tokenErrorRate"], 3)
        self.assertEqual(expanded["predictedToReferenceRatio"], 3)
        self.assertNotIn("greedyFrames", expanded)

    def test_empty_references_have_no_undefined_rates(self):
        result = sequence_diagnostics([[]], [["b"]])
        self.assertIsNone(result["tokenErrorRate"])
        self.assertIsNone(result["predictedToReferenceRatio"])
        self.assertEqual(result["insertions"], 1)

    def test_malformed_batches_fail(self):
        for arguments in [([], []), ([["b"]], []), ([[""]], [["b"]]),
                          ([["b"]], [["b"]], []), ([["b"]], [["b"]], [[]]),
                          ([["b"]], [["b"]], [[True]]), ([["b"]], [["b"]], [[-1]])]:
            with self.assertRaises(ValueError):
                sequence_diagnostics(*arguments)


if __name__ == "__main__":
    unittest.main()
