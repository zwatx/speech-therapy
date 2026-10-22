import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from lexical_expanded_heads import study as s


def membership_fixture():
    held = 'BAT'
    group = s.inventory.prior.word_group(held)
    fitting = next(w for w in ('CAT', 'DOG', 'FISH', 'A', 'THE') if s.inventory.prior.word_group(w) != group)
    rows = [dict(id=str(i), clipId='fit', speakerId='f', age=8, targetPhone=p, trainingEligible=True,
                 legacyRowIndex=i, targetWord=fitting) for i, p in enumerate(s.scalar.membership.PHONES)]
    rows += [dict(id='v', clipId='validation', speakerId='v', age=8, targetPhone='B', trainingEligible=True,
                  legacyRowIndex=30, targetWord=fitting),
             dict(id='a', clipId='validation', speakerId='v', age=8, targetPhone='B', trainingEligible=True,
                  legacyRowIndex=None, targetWord=fitting),
             dict(id='o', clipId='outer', speakerId='o', age=8, targetPhone='B', trainingEligible=True,
                  legacyRowIndex=31, targetWord=held)]
    job = dict(id=f'child-only-scalars-s0-w{group}', family='scalars', regime='child-only', speakerFold=0,
               wordGroup=group, fitRows=list(range(23)), selectionRows=[23], addedValidationRows=[24],
               refitRows=list(range(25)), outerRows=[25])
    return job, rows, {'fit': [fitting], 'validation': [fitting], 'outer': [held]}, {held: group, fitting: s.inventory.prior.word_group(fitting)}


class RunnerTests(unittest.TestCase):
    def test_added_validation_is_withheld_then_included_in_refit(self):
        job, rows, tokens, groups = membership_fixture()
        s.check_job(job, rows, tokens, groups)
        for key in ('fitRows', 'selectionRows'):
            bad = copy.deepcopy(job); bad[key].append(24)
            with self.assertRaises(ValueError):
                s.check_job(bad, rows, tokens, groups)
        bad = copy.deepcopy(job); bad['refitRows'].remove(24)
        with self.assertRaisesRegex(ValueError, 'refit union'):
            s.check_job(bad, rows, tokens, groups)

    def test_whole_utterance_age_and_added_speaker_guards(self):
        job, rows, tokens, groups = membership_fixture()
        bad = copy.deepcopy(tokens); bad['fit'].append('BAT')
        with self.assertRaisesRegex(ValueError, 'Held-out word'):
            s.check_job(job, rows, bad, groups)
        bad = copy.deepcopy(rows); bad[24]['age'] = 30
        with self.assertRaisesRegex(ValueError, 'age restriction'):
            s.check_job(job, bad, tokens, groups)
        bad = copy.deepcopy(rows); bad[24]['speakerId'] = 'f'
        with self.assertRaisesRegex(ValueError, 'speaker leaks'):
            s.check_job(job, bad, tokens, groups)

    def test_inner_freeze_is_required_before_refit_preparation(self):
        bundle = {'cohort': {'rows': []}}
        with patch.object(s, 'load_plan', return_value=({}, {}, bundle)), patch.object(s, 'check_freeze', side_effect=ValueError('missing freeze')), patch.object(s.scalar.core, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'missing freeze'):
                s.fit(Path('plan'), 'sha', 'outer-refit', Path('freeze'), 'sha')
            prepare.assert_not_called()

    def test_refit_freeze_is_required_before_outer_inference(self):
        with patch.object(s, 'load_plan', return_value=({}, {}, {'cohort': {'rows': []}})), patch.object(s, 'check_freeze', side_effect=ValueError('missing freeze')), patch.object(s.scalar.core, 'replay') as replay:
            with self.assertRaisesRegex(ValueError, 'missing freeze'):
                s.outer(Path('plan'), 'sha', Path('freeze'), 'sha')
            replay.assert_not_called()

    def test_fresh_declaration_without_fitting(self):
        with tempfile.TemporaryDirectory(dir=s.BASE) as tmp:
            dest = Path(tmp)/'fresh'
            with patch.object(s, 'inputs', return_value=({}, [], {})), patch.object(s.scalar.core, 'train', side_effect=AssertionError('training')):
                pin = s.declare(dest)
                self.assertFalse(s.read(pin)['trainingPerformed'])
                with self.assertRaisesRegex(ValueError, 'Fresh ignored'):
                    s.declare(dest)

    def test_both_frozen_trainers_integrate_and_checkpoint_tampering_fails(self):
        # Synthetic 46-row data exercise actual fixed optimization and PCA once.
        rng = np.random.default_rng(109)
        rows = [dict(id=f'r{i}', targetId=i % 23, targetPhone=s.scalar.membership.PHONES[i % 23],
                     raterCounts=[1, 1, 3], age=8) for i in range(46)]
        bundle = dict(cohort={'rows': rows}, scalars=rng.normal(size=(46, 13)).astype(np.float32),
                      target=rng.normal(size=(46, 1024)).astype(np.float32), positions={i: i for i in range(46)})
        with tempfile.TemporaryDirectory() as tmp:
            for family in s.FAMILIES:
                module = s.implementation(family)
                job = dict(id=f'all-age-{family}-s0-w0', family=family, regime='all-age', speakerFold=0,
                           wordGroup=0, fitRows=list(range(46)), selectionRows=[], refitRows=list(range(46)),
                           addedValidationRows=[], outerRows=[])
                data = module.core.prepare(bundle, family, job['refitRows'])
                output = Path(tmp).resolve()/family
                module.core.train(data, [], output, s.config_value(job, {}, 'outer-refit', {'epoch': 1}), epochs=1)
                run = dict(jobId=job['id'], selectedEpoch=1, artifacts=s.scalar.manifest(output))
                s.validate_run(job, run, {}, 'outer-refit', rows)
                prediction = module.core.replay(output, data, [0, 1])
                self.assertEqual(prediction['rowIndices'], [0, 1])
                bad = copy.deepcopy(run); bad['selectedEpoch'] = 2
                with self.assertRaises(ValueError):
                    s.validate_run(job, bad, {}, 'outer-refit', rows)


if __name__ == '__main__':
    unittest.main()
