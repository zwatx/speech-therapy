"""Metadata and failure gates; never fit a head or run encoder inference."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from middle_layer_replication import study


class MembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = study.read(study.files.binding(*study.PINS['historicalPlan']))
        cls.candidate = study.read(study.files.binding(*study.PINS['candidatePlan']))
        cls.rows = study.read(cls.old['inputs']['cohort'])['rows']

    def test_all_75_jobs_and_150_controls_preserve_list_orders(self):
        jobs = study.make_jobs(self.old, self.candidate, self.rows)
        self.assertEqual(len(jobs), 75)
        self.assertEqual(len({r for j in jobs for r in j['references'].values()}), 150)
        lookup = {j['id']: j for j in self.old['jobs']}
        for seed in study.SEEDS:
            selected = [j for j in jobs if j['seed'] == seed]
            ids = [i for j in selected for i in j['outerRows']]
            self.assertEqual(len(ids), 5654)
            self.assertEqual(len(set(ids)), 5654)
            for job in selected:
                self.assertEqual(job['objective'], 'unweighted')
                for ref in job['references'].values():
                    for role in study.ROLES:
                        self.assertEqual(job[role], lookup[ref][role])

    def test_mismatched_seed_and_objective_rejected(self):
        for field, value in [('seed', 7), ('objective', 'unit-weighted')]:
            old = dict(self.old, jobs=[dict(j) for j in self.old['jobs']])
            j = next(j for j in old['jobs'] if j['id'] == 'seed17-unweighted-child-only-scalars-s0-w0')
            j[field] = value
            with self.assertRaises(ValueError): study.make_jobs(old, self.candidate, self.rows)

    def test_reordered_fit_membership_rejected(self):
        candidate = copy.deepcopy(self.candidate)
        job = next(j for j in candidate['jobs'] if j['representation'] == 'middle')
        job['fitRows'] = list(reversed(job['fitRows']))
        with self.assertRaises(ValueError): study.make_jobs(self.old, candidate, self.rows)


class GateTests(unittest.TestCase):
    def test_partial_phase_never_restarted(self):
        for suffix in ('', '-started.json', '-freeze.json', '-failure.json'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root/('inner'+suffix)).touch()
                with self.assertRaises(ValueError): study.fresh_phase(root, 'inner')

    def test_review_requires_matching_independent_clear_receipt(self):
        valid = dict(planSha256='abc', verdict='clear', blockingFindings=[], independent=True, reviewer='independent')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'review.json'
            for changes in ({'planSha256': 'wrong'}, {'verdict': 'blocked'}, {'independent': False}, {'blockingFindings': ['blocker']}):
                path.write_text(json.dumps(valid | changes))
                with self.assertRaises(ValueError): study.review_binding(path, 'abc')
            path.write_text(json.dumps(valid))
            self.assertEqual(study.review_binding(path, 'abc')['path'], str(path))

    def test_inner_requires_controls_before_train(self):
        with patch.object(study, 'load_plan', return_value=({}, {'path': '/tmp/plan.json'}, {})), \
             patch.object(study, 'review_binding'), patch.object(study, 'checked_control_freeze', side_effect=ValueError('missing controls')), \
             patch.object(study.core, 'train') as train:
            with self.assertRaisesRegex(ValueError, 'missing controls'):
                study.fit('/tmp/plan.json', 'abc', 'inner', '/tmp/review.json')
            train.assert_not_called()

    def test_incomplete_phase_rejected_before_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); pin = {'path': str(root/'plan.json'), 'sha256': 'plan'}
            value = dict(complete=True, plan=pin, phase='inner', study=study.STUDY, trainingPerformed=True,
                         outerInferencePerformed=False, runs=[], **study.FLAGS)
            path = root/'inner-freeze.json'; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'Incomplete 75-job'):
                study.check_freeze({'jobs': []}, pin, path, study.files.binding(path)['sha256'], 'inner', {})


if __name__ == '__main__': unittest.main()
