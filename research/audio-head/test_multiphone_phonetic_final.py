"""Synthetic final-selection/export checks; no corpus inference or fitting."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_phonetic_final as final
from test_multiphone_controls import synthetic_study


def trials():
    return [{'variant': variant, 'fold': fold, 'lr': rate, 'loss': .3 + fold * .01,
             'bestEpoch': [5, 1, 3, 2, 4][fold], 'output': f'inner/{variant}/{fold}/{rate}'}
            for variant in final.VARIANTS for fold in range(5) for rate in (.001, .0003)]


def synthetic_bound():
    cohort, splits = synthetic_study()
    for row in cohort['rows']:
        row['raterCounts'] = [1, 1, 3]
    rng = np.random.default_rng(11)
    n = len(cohort['rows'])
    return {'cohort': cohort, 'splits': splits, 'positions': {i: n - i - 1 for i in range(n)},
            'arrays': {'target': rng.normal(size=(n, 1024)).astype(np.float32)},
            'scalars': rng.normal(size=(n, 13)).astype(np.float32), 'bindings': {}}


class FinalPhoneticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'outputs').mkdir()
        self.binding = self.root / 'binding.json'
        final.atomic_json(self.binding, {'synthetic': True})
        self.sentinel = self.root / 'input.txt'
        self.sentinel.write_text('immutable')
        self.bound = synthetic_bound()
        self.plan_path = self.root / 'outputs' / 'plan.json'
        inner = trials()
        for trial in inner:
            trial['bestEpoch'] = 2
        self.plan = {'complete': True, 'sourceSha256': {'synthetic': 'stable'}, 'recipeSha256': final.digest(final.RECIPE),
                     'variants': list(final.VARIANTS), 'trials': inner, 'selections': final.selection(inner),
                     'binding': str(self.binding), 'inputFiles': {},
                     'artifactsSha256': {str(self.sentinel): final.digest(self.sentinel)}}
        final.atomic_json(self.plan_path, self.plan)
        self.plan_sha = final.digest(self.plan_path)
        self.enterContext(patch.object(final, 'HERE', self.root))
        self.enterContext(patch.object(final, 'source_hashes', return_value={'synthetic': 'stable'}))
        self.enterContext(patch.object(final.head, 'load_bound', return_value=self.bound))

    def args(self, variant):
        return SimpleNamespace(plan=self.plan_path, plan_sha256=self.plan_sha, variant=variant,
                               output=self.root / 'outputs' / variant)

    def test_selection_mean_over_five_folds_lower_lr_tie_and_integer_median(self):
        rows = trials()
        chosen = final.selection(rows)
        self.assertTrue(all(value['lr'] == .0003 and value['fixedEpochs'] == 3 for value in chosen.values()))
        for row in rows:
            if row['variant'] == final.VARIANTS[0] and row['lr'] == .001:
                row['loss'] = 0. if row['fold'] == 0 else 1.
        self.assertEqual(final.selection(rows)[final.VARIANTS[0]]['lr'], .0003)
        rows[0] = deepcopy(rows[1])
        with self.assertRaisesRegex(ValueError, 'Missing or duplicate'):
            final.selection(rows)
        with self.assertRaisesRegex(ValueError, 'forty'):
            final.selection(rows[:-1])

    def test_full_child_fit_uses_every_child_but_no_adult_moments_labels_or_priors(self):
        data = final.full_fit_data(self.bound, 'child-only', 'weighted')
        expected = [i for i, row in enumerate(self.bound['cohort']['rows']) if 6 <= row['age'] <= 12]
        self.assertEqual(data['fit'], expected)
        changed = deepcopy(self.bound)
        for i, row in enumerate(changed['cohort']['rows']):
            if i not in expected:
                row['raterCounts'] = [0, 0, 5]
                changed['arrays']['target'][changed['positions'][i]] = 1e9
        second = final.full_fit_data(changed, 'child-only', 'weighted')
        self.assertTrue(torch.equal(data['mean'], second['mean']))
        self.assertTrue(torch.equal(data['std'], second['std']))
        self.assertEqual(data['classWeightState'], second['classWeightState'])
        self.assertEqual(data['priors'], second['priors'])
        observed = np.asarray([self.bound['cohort']['rows'][i]['raterCounts'] for i in expected]).sum(0)
        self.assertEqual(data['classWeightState']['observedRaterCounts'], observed.tolist())
        self.assertAlmostEqual(np.dot(observed / observed.sum(), data['classWeightState']['weights']), 1.)

    def test_four_fresh_exports_exact_replay_and_research_feature_contract(self):
        for variant in final.VARIANTS:
            args = self.args(variant)
            manifest = final.fit(args)
            self.assertEqual(manifest['epochsRun'], 2)
            self.assertFalse(manifest['generalizationMeasured'])
            self.assertFalse(manifest['targets'][23]['supported'])
            self.assertNotIn('evaluation', manifest)
            self.assertTrue(final.read_json(args.output / 'status.json')['complete'])
            self.assertEqual(manifest['filesSha256']['status.json'], final.digest(args.output / 'status.json'))
            sha = final.digest(args.output / 'manifest.json')
            self.assertTrue(final.replay(args.output, sha)['exact'])
            model, saved, config, _ = final.load_export(args.output, sha)
            self.assertEqual(config['hyperparameters']['seed'], 7)
            inputs = np.zeros((2, 1037), dtype=np.float32)
            p = final.predict_features(model, saved['mean'], saved['std'], saved['classWeights'], inputs, np.array([0, 1]))
            np.testing.assert_allclose(p.sum(1), 1., atol=1e-6)
            for values, ids in ((inputs[:, :-1], np.array([0, 1])), (inputs, np.array([0, 23])),
                                (inputs, np.array([0, 24])), (inputs, np.array([0, -1])),
                                (inputs, np.array([0., 1.])), (inputs * np.nan, np.array([0, 1])),
                                (inputs, np.array([0, 2]))):
                with self.assertRaisesRegex(ValueError, 'feature-input contract'):
                    final.predict_features(model, saved['mean'], saved['std'], saved['classWeights'], values, ids)
            with self.assertRaisesRegex(ValueError, 'fresh'):
                final.fit(args)

    def test_rehashed_wrong_verification_is_rejected_by_actual_checkpoint_replay(self):
        args = self.args('weighted-child-only')
        final.fit(args)
        path = args.output / 'verification.json'
        value = final.read_json(path)
        value['probabilities'] = [[.1, .2, .7]] * len(value['rowIndices'])
        final.atomic_json(path, value)
        manifest = final.read_json(args.output / 'manifest.json')
        manifest['filesSha256']['verification.json'] = final.digest(path)
        final.atomic_json(args.output / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'checkpoint replay differs'):
            final.replay(args.output, final.digest(args.output / 'manifest.json'))

    def test_source_or_upstream_change_is_rejected_and_final_is_not_published(self):
        args = self.args('unweighted-all-age')
        real_predict = final.predict_features
        def mutate(*values, **keywords):
            result = real_predict(*values, **keywords)
            self.sentinel.write_text('changed')
            return result
        with patch.object(final, 'predict_features', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'Pinned inner artifact'):
                final.fit(args)
        self.assertFalse(args.output.exists())
        self.assertTrue(args.output.with_name(args.output.name + '.partial').exists())
        with patch.object(final, 'source_hashes', return_value={'synthetic': 'changed'}):
            with self.assertRaisesRegex(ValueError, 'source or recipe'):
                final.guard(self.plan, self.plan_path, self.plan_sha)

    def test_missing_classes_rejected_only_for_weighted_and_author_test_rejected(self):
        data = deepcopy(self.bound)
        for row in data['cohort']['rows']:
            row['raterCounts'] = [0, 0, 5]
        self.assertEqual(final.full_fit_data(data, 'all-age', 'unweighted')['classWeights'].tolist(), [1., 1., 1.])
        with self.assertRaisesRegex(ValueError, 'every class'):
            final.full_fit_data(data, 'all-age', 'weighted')
        data['cohort']['authorPartition'] = 'test'
        with self.assertRaisesRegex(ValueError, 'research population'):
            final.full_fit_data(data, 'all-age', 'unweighted')

    def test_exact_replay_record_must_be_completed_and_artifact_bound(self):
        directory = self.root / 'inner'
        directory.mkdir()
        report = {'checkpointSha256': 'checkpoint', 'evaluation': {'metric': .2}}
        for name in final.ARTIFACTS:
            final.atomic_json(directory / name, {})
        final.atomic_json(directory / 'predictions.json', {'rowIndices': [0, 1]})
        final.atomic_json(directory / 'replay.json', {'exact': True, 'checkpointSha256': 'checkpoint',
                                                    'evaluation': report['evaluation'], 'rows': 2})
        job = {'output': str(directory), 'state': 'complete', 'exitCode': 0, 'replay': {'state': 'complete',
            'exitCode': 0, 'verifiedExact': True, 'sha256': final.digest(directory / 'replay.json')}}
        self.assertEqual(len(final.checked_replay(job, report)), 7)
        for field, value in (('state', 'running'), ('exitCode', None), ('verifiedExact', False)):
            bad = deepcopy(job)
            bad['replay'][field] = value
            with self.assertRaisesRegex(ValueError, 'exact checkpoint replay'):
                final.checked_replay(bad, report)
        (directory / 'replay.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'exact checkpoint replay'):
            final.checked_replay(job, report)

    def test_partial_ledger_fails_before_loading_any_features(self):
        unweighted, weighted = self.root / 'unweighted.json', self.root / 'weighted.json'
        final.atomic_json(unweighted, {'complete': True})
        final.atomic_json(weighted, {'complete': False})
        recipe = final.read_json(final.RECIPE)
        recipe['featureBindingSha256'] = final.digest(self.binding)
        temporary_recipe = self.root / 'recipe.json'
        final.atomic_json(temporary_recipe, recipe)
        with patch.object(final, 'RECIPE', temporary_recipe), patch.object(final.head, 'load_bound') as loader:
            with self.assertRaisesRegex(ValueError, 'matrices must be complete'):
                final.check_ledgers(unweighted, final.digest(unweighted), weighted, final.digest(weighted), self.binding)
            loader.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'ledger digest'):
            final.check_ledgers(unweighted, 'wrong', weighted, final.digest(weighted), self.binding)

    def test_recipe_mutation_during_declaration_is_rejected(self):
        recipe_path = self.root / 'recipe-mutation.json'
        recipe_path.write_text(final.RECIPE.read_text())
        args = SimpleNamespace(output=self.root / 'outputs' / 'new-plan.json', unweighted_ledger=Path('unused'),
            unweighted_sha256='unused', weighted_ledger=Path('unused'), weighted_sha256='unused', binding=self.binding)
        def mutate(*_):
            recipe_path.write_text(recipe_path.read_text() + ' ')
            return trials(), {}, self.bound
        with patch.object(final, 'RECIPE', recipe_path), patch.object(final, 'check_ledgers', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'recipe or inner artifact changed'):
                final.declare(args)
        self.assertFalse(args.output.exists())

    def test_masked_target_never_enters_fit_and_positions_must_cover_exactly(self):
        data = deepcopy(self.bound)
        row = deepcopy(data['cohort']['rows'][0])
        row.update(targetId=23, targetPhone='ZH', trainingEligible=False)
        data['cohort']['rows'].append(row)
        result = final.full_fit_data(data, 'all-age', 'unweighted')
        self.assertEqual(len(result['fit']), 20)
        data['positions'][0] = 100
        with self.assertRaisesRegex(ValueError, 'feature coverage'):
            final.full_fit_data(data, 'all-age', 'unweighted')


if __name__ == '__main__':
    unittest.main()
