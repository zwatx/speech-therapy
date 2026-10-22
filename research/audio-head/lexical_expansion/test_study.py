import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from lexical_expansion import study as s


def row(name='r', legacy=0):
    return dict(id=name, clipId='c', speakerId='s', age=8, wordIndex=0, phoneIndex=0,
                targetPhone='B', targetWord='BAT', raterCounts=[1, 1, 3], trainingEligible=True,
                legacyRowIndex=legacy, legacyRowId='old' if legacy is not None else None)


class StudyTests(unittest.TestCase):
    def test_projection_keeps_extra_clips_and_nontarget_words(self):
        clip = dict(id='c', text='BAT!', words=[dict(text='BAT', phones=['B']), dict(text='A', phones=['AH0'])],
                    canonicalPhones=['B', 'AH0'], canonicalPhoneCount=2)
        extra = dict(clip, id='extra')
        cohort = dict(authorPartition='train', authorTestObjectsDecoded=False, clips=[clip, extra])
        projected, tokens = s.canonical_projection(cohort)
        self.assertEqual(tokens, {'c': ['BAT', 'A'], 'extra': ['BAT', 'A']})
        self.assertEqual([c['text'] for c in projected['clips']], ['BAT A', 'BAT A'])
        self.assertEqual(cohort['clips'][0]['text'], 'BAT!')
        bad = copy.deepcopy(cohort); bad['clips'][1]['words'][0]['text'] = 'TWO WORDS'
        with self.assertRaisesRegex(ValueError, 'canonical token'):
            s.canonical_projection(bad)

    def test_legacy_mapping_rejects_changed_votes_duplicate_and_missing(self):
        original = [row('old'), dict(row('ineligible'), trainingEligible=False)]
        expanded = [row('added', None), row()]
        self.assertEqual(s.legacy_map(original, expanded), {0: 1})
        for bad in ([expanded[0]], expanded + [row('duplicate')], [dict(row(), raterCounts=[0, 1, 4])]):
            with self.assertRaises(ValueError):
                s.legacy_map(original, bad)
        with self.assertRaisesRegex(ValueError, 'legacy identity'):
            s.legacy_map(original, [dict(expanded[0], legacyRowId='old'), expanded[1]])

    def test_old_membership_uses_mapping_and_checks_excluded_and_base(self):
        old = dict(baseRows=[0, 4], retainedRows=[4], excludedRows=[0])
        new = dict(baseRows=[8, 9, 10], retainedRows=[8, 10], excludedRows=[9])
        s.check_old_partition(old, new, {0: 9, 4: 8})
        for key in ('baseRows', 'retainedRows', 'excludedRows'):
            bad = copy.deepcopy(new); bad[key] = []
            with self.assertRaisesRegex(ValueError, 'membership'):
                s.check_old_partition(old, bad, {0: 9, 4: 8})

    def test_strata_keep_overlapping_speakers_absent_phones_and_vote_support(self):
        out = s.strata([row(), row('added', None)], [0, 1])
        self.assertEqual([out[k]['support']['ages6to12']['positions'] for k in ('original', 'added', 'all')], [1, 1, 2])
        self.assertEqual([out[k]['support']['ages6to12']['speakers'] for k in ('original', 'added', 'all')], [1, 1, 1])
        sup = out['all']['support']['ages6to12']
        self.assertEqual(len(sup['perPhone']), 23)
        self.assertEqual(sup['perPhone']['B']['raterVotes'], [2, 2, 6])
        self.assertIn('G', sup['missingPhones'])
        self.assertIn('G', sup['missingEventVoteClasses']['rating0'])

    def test_full_utterance_purge_differs_from_outer_target_assignment(self):
        rows = [row()]
        group = s.prior.word_group('BAT')
        other = next(w for w in ('A', 'THE', 'CAT', 'DOG', 'FISH') if s.prior.word_group(w) != group)
        blocked_group = s.prior.word_group(other)
        groups = {'BAT': group, other: blocked_group}
        fitting = s.prior.partition(rows, [0], {'c': [other]})
        outer = s.prior.partition(rows, [0], {'c': [other]}, True, groups, group)
        self.assertEqual(fitting['retainedRows'], [])
        self.assertEqual(outer['retainedRows'], [0])

    def test_feature_parity_checks_scalar_values_and_concatenation(self):
        report = dict(rowIds=['r'], inputs={'old/headInput/report': 'report', 'scalars': 'scalars',
            'old/headInput/target': 'oldTarget', 'old/headInput/scalars': 'oldScalars'},
            matrices={'target': 'target', 'combined': 'combined'})
        values = {'target': np.zeros((1, 1024), np.float32), 'scalars': np.ones((1, 13), np.float32)}
        values.update(oldTarget=values['target'].copy(), oldScalars=values['scalars'].copy(),
                      combined=np.concatenate((values['target'], values['scalars']), axis=1))
        with patch.object(s, 'read', return_value={'rows': [{'rowIndex': 0}]}), patch.object(s.features, 'checked_array', side_effect=lambda p, shape: values[p]):
            self.assertTrue(s.feature_parity(report, [row()], {0: 0})['exact'])
            values['oldScalars'][0, 2] = 9
            with self.assertRaisesRegex(ValueError, 'scalars differ'):
                s.feature_parity(report, [row()], {0: 0})
            values['oldScalars'][0, 2] = 1
            values['combined'][0, 0] = 2
            with self.assertRaisesRegex(ValueError, 'concatenation'):
                s.feature_parity(report, [row()], {0: 0})

    def test_declaration_is_fresh_and_does_not_derive_support(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            dest = Path(tmp)/'fresh'
            with patch.object(s, 'plan_value', return_value=dict(s.FLAGS)), patch.object(s, 'calculate', side_effect=AssertionError('premature support')):
                pin = s.declare(dest)
                self.assertFalse(s.read(pin)['trainingPerformed'])
                with self.assertRaisesRegex(ValueError, 'Fresh ignored'):
                    s.declare(dest)

    def test_changed_plan_prevents_calculation(self):
        with patch.object(s.files, 'binding', return_value={}), patch.object(s, 'read', return_value={'changed': True}), patch.object(s, 'plan_value', return_value={}), patch.object(s, 'calculate') as calculate:
            with self.assertRaisesRegex(ValueError, 'declaration changed'):
                s.run(Path('plan'), 'sha')
            calculate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
