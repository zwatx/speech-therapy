"""Synthetic analytic/transform/bootstrap checks; no study outcomes accessed."""
import hashlib
import json
import unittest

import numpy as np

from nisqa_quality import regression as r


class RegressionTests(unittest.TestCase):
    def test_hand_ridge_penalty_and_unpenalized_intercept(self):
        x = np.array([[-1.], [1.]])
        y = np.tile([2., 4.], (5, 1)).T
        model = r.fit_ridge(x, y, .1)
        np.testing.assert_allclose(model['coefficients'], np.full((1, 5), 2 / 3), rtol=1e-15)
        np.testing.assert_array_equal(model['intercept'], np.full(5, 3.))
        self.assertEqual(model['penalty'], 1.)
        shifted = r.fit_ridge(x + 100, y, .1)
        np.testing.assert_allclose(r.predict(x + 100, shifted), r.predict(x, model), atol=1e-14)
        predicted = r.predict(np.array([[100.]]), model)
        self.assertTrue(np.all(predicted > 5))
        residual = y - r.predict(x, model)
        expected_objective = (residual ** 2).sum() / 10 + .1 * (model['coefficients'] ** 2).sum()
        self.assertAlmostEqual(model['objective'], expected_objective, places=15)

    def test_independent_augmented_least_squares_solution(self):
        rng = np.random.default_rng(7)
        x = rng.normal(size=(21, 6)); y = rng.uniform(1, 5, size=(21, 5))
        xc, yc = x - x.mean(axis=0), y - y.mean(axis=0)
        for value in r.GRID:
            model = r.fit_ridge(x, y, value)
            augmented_x = np.vstack((xc, np.sqrt(5 * len(x) * value) * np.eye(6)))
            augmented_y = np.vstack((yc, np.zeros((6, 5))))
            expected, _, _, _ = np.linalg.lstsq(augmented_x, augmented_y, rcond=None)
            np.testing.assert_allclose(model['coefficients'], expected, rtol=1e-12, atol=1e-14)
            np.testing.assert_allclose(model['intercept'], y.mean(axis=0) - x.mean(axis=0) @ expected)

    def test_standardization_population_constant_all_partitions_and_counts(self):
        x = np.column_stack((np.arange(4.), np.full(4, 3.14)))
        state = r.fit_standardization(x)
        self.assertEqual(state['scale'][1], 1.)
        self.assertTrue(state['constant'][1])
        fitted, diagnostics = r.standardize(x, state, return_diagnostics=True)
        np.testing.assert_allclose(fitted[:, 0], (x[:, 0] - 1.5) / np.sqrt(1.25))
        np.testing.assert_array_equal(fitted[:, 1], np.zeros(4))
        self.assertEqual(diagnostics['totalClampCount'], 0)
        heldout, diagnostics = r.standardize(np.array([[-100., 7.], [100., -3.]]), state, return_diagnostics=True)
        np.testing.assert_array_equal(heldout[:, 1], np.zeros(2))
        np.testing.assert_array_equal(heldout[:, 0], [state['fitMin'][0], state['fitMax'][0]])
        self.assertEqual(diagnostics['perRowClampCounts'], [1, 1])
        self.assertEqual(diagnostics['perColumnClampCounts'], [2, 0])
        self.assertEqual(diagnostics['constantInputDifferenceCount'], 2)
        json.dumps(diagnostics, allow_nan=False)

    def test_pca_rank_sign_and_fit_only_bounds_at_both_candidate_stages(self):
        rng = np.random.default_rng(12)
        ssl = np.zeros((32, 1536)); ssl[:, :20] = rng.normal(size=(32, 20)); ssl[:, 20] = 3.14
        scalars = rng.normal(size=(32, 6)); scalars[:, 5] = 6.
        fit_x, state = r.fit_transform(ssl, scalars)
        self.assertEqual(fit_x.shape, (32, 22))
        pca = state['sslPca']
        self.assertEqual(pca['numericalRank'], 20)
        self.assertEqual(pca['rankThreshold'], max(ssl.shape) * np.finfo(float).eps * pca['singularValues'][0])
        for component in pca['components']:
            self.assertGreaterEqual(component[np.argmax(np.abs(component))], 0)
        original_mean = pca['scaler']['mean'].copy()
        heldout, diag = r.transform_features(ssl[:2] * 1e6, scalars[:2] * 1e6, state, return_diagnostics=True)
        self.assertGreater(diag['sslBeforePca']['totalClampCount'], 0)
        self.assertGreater(diag['finalStandardization']['totalClampCount'], 0)
        np.testing.assert_array_equal(pca['scaler']['mean'], original_mean)
        self.assertTrue(np.all(heldout >= state['joinedScaler']['fitMin']))
        self.assertTrue(np.all(heldout <= state['joinedScaler']['fitMax']))
        np.testing.assert_array_equal(heldout[:, -1], np.zeros(2))
        low_rank = np.zeros((32, 1536)); low_rank[:, :15] = rng.normal(size=(32, 15))
        with self.assertRaisesRegex(ValueError, 'rank'):
            r.fit_pca(low_rank)
        with self.assertRaisesRegex(ValueError, 'rank'):
            r.fit_pca(np.zeros((17, 1536)))

    def test_sparse_scalar_outlier_clamps_features_not_original_or_predictions(self):
        raw = np.zeros((20, 6)); raw[-1, 0] = 1.
        fit_x, state = r.fit_transform(None, raw, kind='acoustic')
        outlier = np.zeros((1, 6)); outlier[0, 0] = 1e12; outlier[0, 1] = 10.
        transformed, diag = r.transform_features(None, outlier, state, return_diagnostics=True)
        self.assertEqual(transformed[0, 0], fit_x[-1, 0])
        self.assertEqual(transformed[0, 1], 0)
        self.assertEqual(outlier[0, 0], 1e12)
        self.assertEqual(diag['finalStandardization']['totalClampCount'], 1)
        self.assertIsNone(diag['sslBeforePca'])

    def test_lambda_ties_larger_wins_all_grid_saved_and_condition_control(self):
        scalars = np.zeros((20, 6)); y = np.full((20, 5), 3.)
        selected = r.select_model(None, scalars, y, None, scalars[:4], y[:4], kind='acoustic',
                                  fit_capture_conditions=['phone'] * 10 + ['Skype'] * 10,
                                  selection_capture_conditions=['phone', 'Skype'] * 2)
        self.assertEqual(selected['selectedLambda'], 10.)
        self.assertEqual([grid['lambda'] for grid in selected['grid']], list(r.GRID))
        for grid in selected['grid']:
            np.testing.assert_array_equal(grid['predictions'], y[:4])
        np.testing.assert_array_equal(selected['meanControlPredictions'], y[:4])
        np.testing.assert_array_equal(selected['conditionMeanControlPredictions'], y[:4])
        refit = r.refit_model(None, scalars, y, selected['selectedLambda'], kind='acoustic')
        self.assertEqual(refit['model']['fitRows'], 20)

    def test_perfect_scalar_signal_beats_pooled_mean(self):
        x = np.linspace(-1, 1, 40)
        scalars = np.zeros((40, 6)); scalars[:, 0] = x
        y = np.tile(3 + x, (5, 1)).T
        selected = r.select_model(None, scalars, y, None, scalars, y, kind='acoustic',
                                  fit_capture_conditions=['phone', 'Skype'] * 20,
                                  selection_capture_conditions=['phone', 'Skype'] * 20)
        self.assertEqual(selected['selectedLambda'], .01)
        model_mae = selected['grid'][selected['selectedIndex']]['metrics']['macroMAE']
        mean_mae = r.metrics(y, selected['meanControlPredictions'])['macroMAE']
        self.assertLess(model_mae, mean_mae / 10)

    def test_metrics_null_constant_correlations_and_macro_definition(self):
        y = np.full((40, 5), 3.14); p = y + np.arange(5)[None, :]
        result = r.metrics(y, p)
        self.assertEqual(result['pearson'], [None] * 5)
        np.testing.assert_allclose(result['dimensionMAE'], np.arange(5))
        self.assertAlmostEqual(result['macroMAE'], 2., places=14)
        self.assertAlmostEqual(result['macroRMSE'], 2., places=14)
        json.dumps(result, allow_nan=False)

    def test_condition_only_signal_cannot_pass_condition_mean(self):
        captures = ['phone'] * 20 + ['Skype'] * 20
        y = np.vstack((np.full((20, 5), 2.), np.full((20, 5), 4.)))
        condition = r.condition_mean(y, captures)
        p = r.predict_condition_mean(condition, captures)
        np.testing.assert_array_equal(p, y)
        report = r.confirmation_report(y, p, p, r.fitted_mean(y, 40), p,
                                       [str(i) for i in range(40)], captures)
        self.assertFalse(report['passesContinuationScreen'])
        self.assertEqual(report['comparisons']['conditionMean']['macroMAEDifference'], 0.)
        self.assertEqual(report['comparisons']['conditionMean']['interval95'], [0., 0.])

    def test_fixed_bootstrap_common_hash_sign_and_all_guards(self):
        y = np.full((40, 5), 3.)
        captures = ['phone'] * 20 + ['Skype'] * 20
        components = [f'component{i}' for i in range(40)]
        result = r.confirmation_report(y, y, y + .2, y + .3, y + .1, components, captures)
        self.assertTrue(result['passesContinuationScreen'])
        self.assertTrue(all(result['guards'].values()))
        indices = np.random.Generator(np.random.PCG64(27092026)).integers(0, 40, size=(10000, 40), dtype=np.int64)
        self.assertEqual(result['bootstrap']['indicesSha256'], hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest())
        for name, delta in (('acoustic', -.2), ('mean', -.3), ('conditionMean', -.1)):
            np.testing.assert_allclose(result['comparisons'][name]['interval95'], [delta, delta], atol=1e-14)
        json.dumps(result, allow_nan=False)
        # Candidate is worse for phone even though its pooled difference is
        # favorable; capture and dimension guards remain separate conditions.
        candidate = y.copy(); candidate[:20] += .3
        guarded = r.confirmation_report(y, candidate, y + .8, y + .8, y + .1, components, captures)
        self.assertFalse(guarded['guards']['bothCapturesNonpositiveVsConditionMean'])
        self.assertFalse(guarded['passesContinuationScreen'])
        first_dimension = y.copy(); first_dimension[:, 0] += .2
        dimension_guard = r.confirmation_report(y, first_dimension, y + .8, y, y + .1, components, captures)
        self.assertFalse(dimension_guard['guards']['noDimensionMoreThan010WorseThanMean'])

    def test_nonconstant_bootstrap_matches_independent_paired_draws(self):
        y = np.full((40, 5), 3.)
        candidate = y + np.linspace(0, .4, 40)[:, None]
        acoustic = y + .3; mean = y + .2; condition = y + .1
        result = r.confirmation_report(y, candidate, acoustic, mean, condition,
                                       [str(i) for i in range(40)], ['phone', 'Skype'] * 20)
        rng = np.random.Generator(np.random.PCG64(27092026))
        indices = rng.integers(0, 40, (10000, 40), dtype=np.int64)
        for name, control in (('acoustic', acoustic), ('mean', mean), ('conditionMean', condition)):
            row_delta = np.abs(candidate - y).mean(axis=1) - np.abs(control - y).mean(axis=1)
            independent = np.array([np.mean(row_delta[draw]) for draw in indices])
            np.testing.assert_array_equal(result['comparisons'][name]['pairedRowDifferences'], row_delta)
            np.testing.assert_allclose(result['comparisons'][name]['interval95'], np.quantile(independent, [.025, .975], method='linear'), rtol=0, atol=1e-16)

    def test_invalid_labels_shapes_finite_lambda_conditions_components(self):
        x = np.zeros((4, 6)); y = np.full((4, 5), 3.)
        for invalid in (np.ones((4, 4)), np.full((4, 5), .99), np.full((4, 5), 5.01),
                        np.full((4, 5), np.nan), np.full((3, 5), 3.), np.full((4, 5), '3')):
            with self.assertRaises(ValueError):
                r.fit_ridge(x, invalid, .1)
        for value in (0, .001, -1, True):
            with self.assertRaises(ValueError):
                r.fit_ridge(x, y, value)
        for invalid in (np.zeros((0, 6)), np.full((4, 6), np.inf), np.zeros(6), np.ones((4, 6), dtype=complex)):
            with self.assertRaises(ValueError):
                r.fit_standardization(invalid)
        with self.assertRaises(ValueError):
            r.condition_mean(y, ['Phone', 'Skype'] * 2)
        with self.assertRaises(ValueError):
            r.condition_mean(y, ['phone'] * 4)
        forty = np.full((40, 5), 3.)
        with self.assertRaises(ValueError):
            r.confirmation_report(forty, forty, forty, forty, forty, ['same'] * 40, ['phone', 'Skype'] * 20)
        with self.assertRaises(ValueError):
            r.confirmation_report(forty, forty, forty, forty, forty, [str(i) for i in range(40)], ['phone'] * 40)


if __name__ == '__main__':
    unittest.main()
