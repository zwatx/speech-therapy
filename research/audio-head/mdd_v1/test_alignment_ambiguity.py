"""Independent complete-path oracle; synthetic tokens only, no model imports."""
from dataclasses import FrozenInstanceError
import itertools
import unittest

from .alignment_ambiguity import MAX_DP_CELLS, analyze_alignment


def all_paths(reference, hypothesis):
    """Enumerate every legal edit path, including deliberately nonoptimal ones."""
    def walk(i, j, cost, correspondences):
        if i == len(reference) and j == len(hypothesis):
            yield cost, correspondences
            return
        if i < len(reference):
            yield from walk(i + 1, j, cost + 1, correspondences + (None,))
        if j < len(hypothesis):
            yield from walk(i, j + 1, cost + 1, correspondences)
        if i < len(reference) and j < len(hypothesis):
            yield from walk(i + 1, j + 1, cost + int(reference[i] != hypothesis[j]),
                            correspondences + (j,))
    return list(walk(0, 0, 0, ()))


class AlignmentAmbiguityTests(unittest.TestCase):
    def test_exhaustive_all_paths_binary_sequences_through_length_three(self):
        sequences = [tokens for length in range(4)
                     for tokens in itertools.product(('A', 'B'), repeat=length)]
        for reference in sequences:
            for hypothesis in sequences:
                paths = all_paths(reference, hypothesis)
                optimum = min(cost for cost, _ in paths)
                best = [indices for cost, indices in paths if cost == optimum]
                with self.subTest(reference=reference, hypothesis=hypothesis):
                    result = analyze_alignment(reference, hypothesis)
                    self.assertEqual(result.distance, optimum)
                    self.assertEqual(len(result.positions), len(reference))
                    for i, choices in enumerate(result.positions):
                        indices = {path[i] for path in best}
                        identities = {hypothesis[j] if j is not None else None for j in indices}
                        agreement_values = {value == reference[i] for value in identities}
                        agreement = ('ambiguous' if len(agreement_values) == 2 else
                                     'match' if True in agreement_values else 'mismatch')
                        self.assertEqual(choices.reference_index, i)
                        self.assertEqual(choices.reference_phone, reference[i])
                        self.assertEqual(set(choices.hypothesis_indices), indices)
                        self.assertEqual(set(choices.hypothesis_phones), identities)
                        self.assertEqual(choices.hypothesis_indices,
                                         tuple(sorted(j for j in indices if j is not None))
                                         + ((None,) if None in indices else ()))
                        self.assertEqual(choices.hypothesis_phones,
                                         tuple(sorted(value for value in identities if value is not None))
                                         + ((None,) if None in identities else ()))
                        self.assertEqual(choices.correspondence_ambiguous, len(indices) > 1)
                        self.assertEqual(choices.identity_ambiguous, len(identities) > 1)
                        self.assertEqual(choices.agreement, agreement)

    def test_repeated_deletion_has_ambiguous_identity_and_match_status(self):
        result = analyze_alignment(['A', 'A'], ['A'])
        self.assertEqual(result.distance, 1)
        for choices in result.positions:
            self.assertEqual(choices.hypothesis_indices, (0, None))
            self.assertEqual(choices.hypothesis_phones, ('A', None))
            self.assertTrue(choices.identity_ambiguous)
            self.assertEqual(choices.agreement, 'ambiguous')
        # Both positions marginally allow index 0, but cannot both consume it.
        self.assertNotIn((0, 0), [path for cost, path in all_paths(['A', 'A'], ['A']) if cost == 1])

    def test_repeated_insertion_has_index_ambiguity_but_stable_identity(self):
        choices = analyze_alignment(['A'], ['A', 'A']).positions[0]
        self.assertEqual(choices.hypothesis_indices, (0, 1))
        self.assertEqual(choices.hypothesis_phones, ('A',))
        self.assertTrue(choices.correspondence_ambiguous)
        self.assertFalse(choices.identity_ambiguous)
        self.assertEqual(choices.agreement, 'match')

    def test_substitution_deletion_insertion_alternatives(self):
        result = analyze_alignment(['A', 'B'], ['B', 'A'])
        self.assertEqual(result.distance, 2)
        for choices in result.positions:
            self.assertEqual(choices.hypothesis_indices, (0, 1, None))
            self.assertEqual(choices.hypothesis_phones, ('A', 'B', None))
            self.assertEqual(choices.agreement, 'ambiguous')

    def test_identity_ambiguity_does_not_imply_ambiguous_match_status(self):
        choices = analyze_alignment(['X'], ['A', 'B']).positions[0]
        self.assertEqual(choices.hypothesis_phones, ('A', 'B'))
        self.assertTrue(choices.identity_ambiguous)
        self.assertEqual(choices.agreement, 'mismatch')
        choices = analyze_alignment(['X'], ['A', 'A']).positions[0]
        self.assertTrue(choices.correspondence_ambiguous)
        self.assertFalse(choices.identity_ambiguous)
        self.assertEqual(choices.agreement, 'mismatch')

    def test_unique_alignment_and_opaque_phone_strings(self):
        result = analyze_alignment(['tʃ', 'aɪ', 'N'], ['tʃ', 'ə', 'N'])
        self.assertEqual(result.distance, 1)
        self.assertEqual([p.hypothesis_indices for p in result.positions], [(0,), (1,), (2,)])
        self.assertEqual([p.agreement for p in result.positions], ['match', 'mismatch', 'match'])
        self.assertTrue(all(not p.correspondence_ambiguous for p in result.positions))
        self.assertEqual(analyze_alignment(['None'], []).positions[0].hypothesis_phones, (None,))

    def test_empty_sequences(self):
        self.assertEqual(analyze_alignment([], []).distance, 0)
        self.assertEqual(analyze_alignment([], ['A', 'A']).positions, ())
        self.assertEqual(analyze_alignment([], ['A', 'A']).distance, 2)
        deleted = analyze_alignment(['A', 'B'], [])
        self.assertEqual(deleted.distance, 2)
        for choices in deleted.positions:
            self.assertEqual(choices.hypothesis_indices, (None,))
            self.assertEqual(choices.hypothesis_phones, (None,))
            self.assertEqual(choices.agreement, 'mismatch')
            self.assertFalse(choices.correspondence_ambiguous)

    def test_invalid_sequences_and_tokens(self):
        for invalid in (None, 'ABC', b'ABC', bytearray(b'A'), {'A'}, {'A': 'B'},
                        [None], [''], [' \t\n'], [1], [True], [['A']]):
            for side in ('reference', 'hypothesis'):
                values = dict(reference=['A'], hypothesis=['A'])
                values[side] = invalid
                with self.subTest(side=side, invalid=invalid), self.assertRaises(ValueError):
                    analyze_alignment(**values)

    def test_quadratic_resource_guard(self):
        with self.assertRaisesRegex(ValueError, 'MAX_DP_CELLS'):
            analyze_alignment(['A'] * 500, ['A'] * 500)
        with self.assertRaisesRegex(ValueError, 'MAX_DP_CELLS'):
            analyze_alignment(['A'] * MAX_DP_CELLS, [])

    def test_results_are_immutable_and_do_not_alias_inputs(self):
        reference, hypothesis = ['A'], ['B']
        result = analyze_alignment(reference, hypothesis)
        reference[0] = 'B'
        hypothesis[0] = 'A'
        self.assertEqual(result.positions[0].reference_phone, 'A')
        self.assertEqual(result.positions[0].hypothesis_phones, ('B',))
        with self.assertRaises(FrozenInstanceError):
            result.distance = 0
        with self.assertRaises(FrozenInstanceError):
            result.positions[0].agreement = 'match'


if __name__ == '__main__':
    unittest.main()
