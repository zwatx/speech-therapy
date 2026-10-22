"""Metadata and failure gates; never fit a head or run encoder inference."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from temporal_pooling import study


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

    def test_source_or_input_drift_rejected_before_bundle_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'plan.json'
            pin = {'path':'unused', 'sha256':'unused'}
            path.write_text(json.dumps({'inputs':{'featureReport':pin,'extractionReview':pin}, 'sources':{'new':'old'}}))
            with patch.object(study, 'declaration', return_value={'sources':{'new':'changed'}}):
                with self.assertRaisesRegex(ValueError,'declaration changed'):
                    study.load_plan(path, study.files.binding(path)['sha256'])

    def test_incomplete_phase_rejected_before_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); pin = {'path': str(root/'plan.json'), 'sha256': 'plan'}
            value = dict(complete=True, plan=pin, phase='inner', study=study.STUDY, trainingPerformed=True,
                         outerInferencePerformed=False, runs=[], **study.FLAGS)
            path = root/'inner-freeze.json'; path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'Incomplete 75-job'):
                study.check_freeze({'jobs': []}, pin, path, study.files.binding(path)['sha256'], 'inner', {})




class TrainerTests(unittest.TestCase):
    def test_trainer_and_validator_are_only_explicit_routing_changes(self):
        from lexical_seed_replication import core as frozen, validation
        from temporal_pooling import core
        import inspect
        text = Path(core.__file__).read_text()
        trainer = Path(frozen.__file__).read_text().replace('from lexical_compact import core as compact', 'from temporal_pooling import compact')
        self.assertEqual(text[:len(trainer)], trainer)
        expected = inspect.getsource(validation.run).replace('def run(', 'def validate_run(',1).replace('prior.compact.core.TRANSFORM_RECIPE','compact.TRANSFORM_RECIPE').replace('core.fitting_weights(', 'fitting_weights(').replace('core.recipe(', 'recipe(').replace('core.initialize(', 'initialize(')
        self.assertEqual(inspect.getsource(core.validate_run), expected)

    def test_same_seed_initial_tensors_exact(self):
        from lexical_seed_replication import core as frozen
        from temporal_pooling import core
        import torch
        for seed in study.SEEDS:
            actual,_ = core.initialize(29,seed)
            old,_ = frozen.initialize(29,seed)
            self.assertTrue(all(torch.equal(v,old.state_dict()[k]) for k,v in actual.state_dict().items()))

    def test_synthetic_temporal_refit_and_replay(self):
        from temporal_pooling import core
        from lexical_unit_weights.test_core import bundle
        import numpy as np
        import torch
        data = bundle(True)
        data['target'] = np.random.default_rng(31).normal(size=(len(data['target']),3072)).astype(np.float32)
        prepared = core.prepare(data, 'pca16-scalars', list(range(65)), 'unweighted')
        self.assertEqual(prepared['values'].shape[1],29)
        self.assertEqual(prepared['transform']['basis'].shape,(3072,16))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'refit'
            report = core.train(prepared, [], output, {}, seed=17, epochs=1)
            self.assertEqual(report['bestEpoch'],1)
            result = core.replay(output,prepared,list(range(65,71)),seed=17)
            self.assertEqual(result['rowIndices'],list(range(65,71)))
            cfg = json.loads((output/'config.json').read_text())
            self.assertEqual(cfg['transformRecipe'],core.compact.TRANSFORM_RECIPE)
            cfg['transformRecipe']['input'] = 'raw 1024-dimensional target features'
            (output/'config.json').write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'configuration differs'):
                core.replay(output,prepared,list(range(65,71)),seed=17)


if __name__ == '__main__': unittest.main()
