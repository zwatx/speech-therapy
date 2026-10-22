import copy
import unittest

import multiphone_note_likelihood as diagnostic


def fixture(raw='D'):
    word = dict(phones=['L'], **{'phones-accuracy': [.4], 'mispronunciations': [
        {'index': 0, 'canonical-phone': 'L', 'pronounced-phone': raw}]})
    notes = diagnostic.derive_notes({'u': 's'}, {'s': '8'}, {'u': {'words': [word]}})
    row = dict(id='u:L', clipId='u', speakerId='s', age=8, wordIndex=0, phoneIndex=0,
               targetId=15, targetPhone='L', trainingEligible=True)
    recipe = dict(consonants={'L': 'l', 'D': 'd', 'R': 'ɹ'}, vowels={}, stressOverrides={})
    vocab = {'l': 4, 'd': 5, 'ɹ': 6}
    return word, notes, {'rows': [row]}, recipe, vocab


def scored_fixture():
    _, notes, cohort, recipe, vocab = fixture()
    chosen, _ = diagnostic.choose_notes(notes, cohort, recipe, vocab)
    n = chosen[0]
    target = {k: n[k] for k in ('rowIndex', 'rowId', 'targetId', 'targetPhone',
                               'wordIndex', 'phoneIndex', 'canonicalIndex')}
    values = [-20.]*388
    values[0], values[1] = -4., -2.
    artifact = dict(clip=dict(id='u', speakerId='s', canonicalPhones=['L'],
        mappedTokenIds=[4], targetRows=[target], mappingAmbiguities=['canonical-l-does-not-model-dark-or-syllabic-variants']), computed=dict(canonicalLogLikelihood=-4., slots=[
        dict(target=target, likelihoods=dict(position=0, canonicalToken=4,
             candidateTokenIds=list(range(4, 392)), replacementLogLikelihoods=values,
             canonicalLogLikelihood=-4.))]))
    return n, artifact


class NoteLikelihoodTests(unittest.TestCase):
    def test_raw_identity_and_utterance_offset(self):
        word, _, _, _, _ = fixture()
        words = [dict(phones=['AH0', 'N'], **{'phones-accuracy': [2, 2]}), word]
        rows = diagnostic.derive_notes({'u': 's'}, {'s': '8'}, {'u': {'words': words}})
        self.assertEqual((rows[0]['wordIndex'], rows[0]['canonicalIndex'], rows[0]['producedRaw']), (1, 2, 'D'))
        self.assertEqual(len(rows), 1)  # No notes invented for unannotated phones.
        self.assertTrue(rows[0]['belowHalf'])

    def test_duplicate_and_wrong_canonical_rejected(self):
        word, *_ = fixture()
        for change in ('duplicate', 'canonical'):
            bad = copy.deepcopy(word)
            if change == 'duplicate':
                bad['mispronunciations'] *= 2
            else:
                bad['mispronunciations'][0]['canonical-phone'] = 'R'
            with self.assertRaises(ValueError):
                diagnostic.derive_notes({'u': 's'}, {'s': '8'}, {'u': {'words': [bad]}})

    def test_exclusion_categories_and_absent_row(self):
        for raw, reason in [('<unk>', 'unknown-production'), ('R*', 'approximate-production'),
                            ('<DEL>', 'deletion-description'), ('D R', 'multi-phone-description'),
                            ('WHAT', 'unsupported-production-description')]:
            _, notes, cohort, recipe, vocab = fixture(raw)
            selected, excluded = diagnostic.choose_notes(notes, cohort, recipe, vocab)
            self.assertEqual(selected, [])
            self.assertEqual(excluded[0]['exclusion'], reason)
        _, notes, _, recipe, vocab = fixture()
        self.assertEqual(diagnostic.choose_notes(notes, {'rows': []}, recipe, vocab)[1][0]['exclusion'],
                         'absent-from-single-occurrence-export')

    def test_collision_and_misaligned_cohort(self):
        _, notes, cohort, recipe, vocab = fixture('L')
        self.assertEqual(diagnostic.choose_notes(notes, cohort, recipe, vocab)[1][0]['exclusion'], 'same-decoder-token')
        cohort['rows'][0]['age'] = 9
        with self.assertRaises(ValueError):
            diagnostic.choose_notes(notes, cohort, recipe, vocab)

    def test_postvocalic_context_for_both_hypotheses(self):
        _, notes, cohort, recipe, vocab = fixture('R')
        recipe['vowels']['EH'] = 'ɛ'
        vocab['ɛ'] = 7
        notes[0]['precedingCanonicalPhone'] = 'EH0'
        chosen, _ = diagnostic.choose_notes(notes, cohort, recipe, vocab)
        self.assertIn('postvocalic-r-may-compete-with-merged-rhotic-tokens', chosen[0]['mappingLimitations'])
        notes[0].update(canonicalRaw='R', targetPhone='R', producedRaw='D')
        cohort['rows'][0]['targetPhone'] = 'R'
        chosen, _ = diagnostic.choose_notes(notes, cohort, recipe, vocab)
        self.assertIn('postvocalic-r-may-compete-with-merged-rhotic-tokens', chosen[0]['mappingLimitations'])

    def test_exact_likelihood_and_rank_ties(self):
        note, artifact = scored_fixture()
        row = diagnostic.score_note(note, artifact)
        self.assertEqual((row['favored'], row['strictRank'], row['notedMinusCanonical']), ('noted', 1, 2.))
        self.assertTrue(row['uniqueMaximum'])
        artifact['computed']['slots'][0]['likelihoods']['replacementLogLikelihoods'][2] = -2.
        row = diagnostic.score_note(note, artifact)
        self.assertEqual(row['exactTieCount'], 2)
        self.assertFalse(row['uniqueMaximum'])
        artifact['computed']['slots'][0]['likelihoods']['replacementLogLikelihoods'][1] = -4.
        row = diagnostic.score_note(note, artifact)
        self.assertEqual((row['favored'], row['strictRank']), ('tie', 2))

    def test_invalid_likelihood_and_position_rejected(self):
        for mutation in ('nonfinite', 'position', 'canonical', 'candidate'):
            note, artifact = scored_fixture()
            ll = artifact['computed']['slots'][0]['likelihoods']
            if mutation == 'nonfinite': ll['replacementLogLikelihoods'][1] = float('nan')
            elif mutation == 'position': ll['position'] = 1
            elif mutation == 'canonical': ll['canonicalLogLikelihood'] = -3.
            else: ll['candidateTokenIds'][0] = 5
            with self.assertRaises(ValueError):
                diagnostic.score_note(note, artifact)

    def test_summary_zero_support_and_context(self):
        note, artifact = scored_fixture()
        row = diagnostic.score_note(note, artifact)
        summary = diagnostic.summarize([row])
        child = summary['child6to12']['oneNoteInUtterance']
        self.assertEqual(child['total']['events'], 1)
        self.assertEqual(len(child['byPhone']), 23)
        self.assertIsNone(child['byPhone']['B']['medianNotedMinusCanonical'])
        self.assertEqual(summary['olderThan12']['all']['total']['events'], 0)
        self.assertEqual(summary['all']['multipleNotesInUtterance']['total']['events'], 0)


if __name__ == '__main__':
    unittest.main()
