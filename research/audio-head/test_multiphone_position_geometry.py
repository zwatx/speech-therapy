import copy
import unittest
import numpy as np

from multiphone_position_geometry import clip_geometry, legacy_parity


def fixture(adjacent=False):
    # Artificial one-frame-per-sample geometry for a synthetic CTC-path test.
    phones = ['S', 'S'] if adjacent else ['S', 'T', 'S']
    vocab = {'s': 4, 't': 5}
    recipe = dict(consonants={'S': 's', 'T': 't'}, vowels={}, stressOverrides={},
                  convKernel=[1], convStride=[1], minimumTargetFramesDiagnostic=2, poolingContextFrames=2)
    clip = dict(id='u', sampleCount=7, canonicalPhones=phones, words=[{'phones': phones}])
    rows = [dict(id=f'u:0:{i}', clipId='u', wordIndex=0, phoneIndex=i,
                 canonicalIndex=i, targetId=10, targetPhone='S', legacyRowIndex=None)
            for i, p in enumerate(phones) if p == 'S']
    prob = np.full((7, 392), .00001)
    path = [0, 4, 0, 0 if adjacent else 5, 0, 4, 0]
    for i, token in enumerate(path): prob[i, token] += .99
    prob /= prob.sum(1, keepdims=True)
    return clip, rows, np.log(prob).astype(np.float32), recipe, vocab


class PositionGeometryTests(unittest.TestCase):
    def test_repeated_sound_has_distinct_state_and_window(self):
        result = clip_geometry(*fixture())
        a, b = result['rows']
        self.assertNotEqual(a['id'], b['id'])
        self.assertLessEqual(a['intervalFrames'][1], b['intervalFrames'][0])
        self.assertNotEqual(a['estimatedPoolingWindowFrames'], b['estimatedPoolingWindowFrames'])
        self.assertEqual((result['repeatedTargetGroups'], result['repeatedPositions']), (1, 2))

    def test_adjacent_equal_tokens_have_blank_between_states(self):
        a, b = clip_geometry(*fixture(adjacent=True))['rows']
        self.assertLess(a['intervalFrames'][1], b['intervalFrames'][0])

    def test_invalid_position_identity_and_duplicate_rejected(self):
        for kind in ('duplicate', 'wrong-word', 'wrong-flat-index', 'wrong-id'):
            clip, rows, logp, recipe, vocab = fixture()
            if kind == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            elif kind == 'wrong-word': rows[0]['wordIndex'] = 2
            elif kind == 'wrong-flat-index': rows[1]['canonicalIndex'] = 1
            else: rows[1]['id'] = 'u:S'
            with self.assertRaises(ValueError): clip_geometry(clip, rows, logp, recipe, vocab)

    def test_legacy_exact_parity_and_changed_value_rejected(self):
        args = fixture()
        args[1][0]['legacyRowIndex'] = 7
        result = clip_geometry(*args)
        legacy = dict(result['rows'][0], rowIndex=7)
        diagnostic = dict(result['diagnostics'], clipId='u')
        self.assertEqual(legacy_parity(result, [legacy], diagnostic), 1)
        changed = copy.deepcopy(legacy)
        changed['scalarFeatures'][0] += .001
        with self.assertRaises(ValueError): legacy_parity(result, [changed], diagnostic)
        with self.assertRaises(ValueError): legacy_parity(result, [], diagnostic)

    def test_no_rating_or_note_fields_are_used_or_exported(self):
        args = fixture()
        args[1][0].update(raterCounts=[5, 0, 0], sparseNotes={'unknown': 'value'})
        result = clip_geometry(*args)
        self.assertNotIn('raterCounts', result['rows'][0])
        self.assertNotIn('sparseNotes', result['rows'][0])
        self.assertEqual(legacy_parity(result, [], None), 0)

    def test_corrupt_array_and_geometry_rejected(self):
        for kind in ('nonfinite', 'frame-count', 'flattened'):
            clip, rows, logp, recipe, vocab = fixture()
            if kind == 'nonfinite': logp[0, 0] = np.nan
            elif kind == 'frame-count': clip['sampleCount'] += 1
            else: clip['words'] = [{'phones': ['T']}]
            with self.assertRaises(ValueError): clip_geometry(clip, rows, logp, recipe, vocab)


if __name__ == '__main__': unittest.main()
