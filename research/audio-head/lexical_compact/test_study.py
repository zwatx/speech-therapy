"""Candidate transform lineage and frozen reference comparison guards."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import torch

from lexical_compact import study as s


class StudyTests(unittest.TestCase):
    def test_reference_outcomes_stay_closed_until_refit_validation(self):
        pin = dict(path='outer-freeze', sha256='outer')
        plan = dict(jobs=[])
        frozen = dict(complete=True, plan={}, outerInferencePerformed=True, predictions=[],
                      refitFreeze=dict(path='refit-freeze', sha256='refit'))
        with patch.object(s.files, 'binding', return_value=pin), \
             patch.object(s, 'read', return_value=frozen) as read, \
             patch.object(s, 'checked_refits', side_effect=ValueError('incomplete refits')):
            with self.assertRaisesRegex(ValueError, 'incomplete refits'):
                s.calculate(plan, {}, Path('outer-freeze'), 'outer')
            read.assert_called_once_with(pin)

    def test_refit_and_outer_require_complete_freezes(self):
        with patch.object(s, 'load_plan', return_value=({}, {}, {})), \
             patch.object(s, 'check_freeze', side_effect=ValueError('incomplete freeze')), \
             patch.object(s.core, 'train') as train, patch.object(s.core, 'replay') as replay:
            for action in (s.refit, s.outer):
                with self.assertRaisesRegex(ValueError, 'incomplete freeze'):
                    action(Path('plan'), 'p', Path('freeze'), 'f')
            train.assert_not_called()
            replay.assert_not_called()

    def test_reference_identity_requires_exact_rows_folds_groups_and_cells(self):
        candidate = dict(rowIndices=[0, 1], rowFolds=[0, 1], rowWordGroups=[2, 3],
                         cells=[dict(speakerFold=0, wordGroup=2, rowIndices=[0]),
                                dict(speakerFold=1, wordGroup=3, rowIndices=[1])],
                         speakerFolds=[dict(speakerFold=0, rowIndices=[0]), dict(speakerFold=1, rowIndices=[1])])
        s.check_reference_identity(candidate, copy.deepcopy(candidate))
        for key in ('rowIndices', 'rowFolds', 'rowWordGroups', 'cells', 'speakerFolds'):
            changed = copy.deepcopy(candidate)
            changed[key] = list(reversed(changed[key]))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Reference'):
                s.check_reference_identity(candidate, changed)

    def test_transform_and_all_checkpoint_lineage_must_match(self):
        artifacts = {name: dict(path=name, sha256=name) for name in
                     ('config.json', 'transform.pt', 'initial.pt', 'best.pt', 'last.pt')}
        cfg = dict(transform=artifacts['transform.pt'], transformRecipe=s.core.TRANSFORM_RECIPE,
                   featureWidth=29, family=s.FAMILY)
        transform = dict(fitRows=[0, 1], rank=16, center=torch.zeros(1024),
                         basis=torch.zeros(1024, 16), eigenvalues=torch.zeros(1024))
        states = {name: dict(transformSha256='transform.pt', configSha256='config.json', epoch=epoch)
                  for name, epoch in [('initial.pt', 0), ('best.pt', 2), ('last.pt', 17)]}
        values = {'transform.pt': transform, **states}
        report = dict(bestEpoch=2, epochsRun=17)
        job = dict(fitRows=[0, 1], refitRows=[0, 1, 2])
        def check(payload, configuration):
            with patch.object(s.baseline, 'validate_history', return_value=report), \
                 patch.object(s, 'read', return_value=configuration), \
                 patch.object(s.torch, 'load', side_effect=lambda path, **kwargs: payload[path]):
                return s.validate_history(job, dict(artifacts=artifacts), {}, 'inner', [])
        self.assertEqual(check(values, cfg), report)
        for name in states:
            wrong = copy.deepcopy(values)
            wrong[name]['transformSha256'] = 'wrong'
            with self.subTest(checkpoint=name), self.assertRaisesRegex(ValueError, 'Checkpoint transform'):
                check(wrong, cfg)
        wrong = copy.deepcopy(values)
        wrong['transform.pt']['fitRows'] = [0, 2]
        with self.assertRaisesRegex(ValueError, 'Transform fitting identity'):
            check(wrong, cfg)
        with self.assertRaisesRegex(ValueError, 'Transform configuration'):
            check(values, dict(cfg, transform=dict(path='other', sha256='other')))


if __name__ == '__main__':
    unittest.main()
