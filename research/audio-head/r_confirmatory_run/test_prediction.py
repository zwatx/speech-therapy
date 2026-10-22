"""Synthetic feature/state-only tests; no corpus, real weights, audio or fitting."""
import hashlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from r_confirmatory_run.prediction import predict_candidate, load_fixed_predictor, FixedPredictor


def candidate_state():
    return {
        'embed_mean': np.zeros(1024, dtype=np.float64),
        'components': np.eye(16, 1024, dtype=np.float64),
        'column_mean': np.zeros(30, dtype=np.float64),
        'column_std': np.ones(30, dtype=np.float64),
        'eigenvalues': np.ones(1024, dtype=np.float64),
        'indices': np.array([0], dtype=np.int64),
        'coef': np.zeros(31, dtype=np.float64),
        'lambda': np.array(.01, dtype=np.float64),
    }


class CandidatePredictionTests(unittest.TestCase):
    def test_zero_fixed_coefficients_produce_literal_half_for_each_feature_row(self):
        features = np.zeros((3, 1037), dtype=np.float32)
        actual = predict_candidate(features, np.array([0.0, .5, 1.0]), candidate_state())
        np.testing.assert_array_equal(actual, np.array([.5, .5, .5]))
        self.assertEqual(actual.dtype, np.float64)

    def test_candidate_rejects_invalid_feature_probability_and_fixed_state_inputs(self):
        valid_features = np.zeros((1, 1037), dtype=np.float32)
        valid_probabilities = np.array([.5], dtype=np.float64)
        inputs = [
            (np.zeros((1, 1036), dtype=np.float32), valid_probabilities, candidate_state(), 'invalid_features'),
            (np.zeros((1, 1037), dtype=np.float64), valid_probabilities, candidate_state(), 'invalid_features'),
            (np.full((1, 1037), np.nan, dtype=np.float32), valid_probabilities, candidate_state(), 'invalid_features'),
            (valid_features, np.array([1.1]), candidate_state(), 'invalid_retained_probabilities'),
            (valid_features, np.array([np.nan]), candidate_state(), 'invalid_retained_probabilities'),
            (valid_features, np.array([.5, .5]), candidate_state(), 'invalid_retained_probabilities'),
        ]
        for key, value in [
            ('column_std', np.zeros(30)), ('coef', np.zeros(30)),
            ('lambda', np.array(.1)), ('eigenvalues', -np.ones(1024)),
            ('components', np.zeros((16, 1024))),
            ('indices', np.array([0, 0], dtype=np.int64)),
            ('embed_mean', np.full(1024, np.inf)),
            ('coef', np.zeros(31, dtype=np.float32)),
        ]:
            state = candidate_state()
            state[key] = value
            inputs.append((valid_features, valid_probabilities, state, 'invalid_candidate_state'))
        state = candidate_state()
        state['unexpected'] = np.array(1.)
        inputs.append((valid_features, valid_probabilities, state, 'invalid_candidate_state'))
        for index, (features, probabilities, state, code) in enumerate(inputs):
            with self.subTest(index=index):
                with self.assertRaises(ValueError) as caught:
                    predict_candidate(features, probabilities, state)
                self.assertEqual(getattr(caught.exception, 'code', None), code)
                self.assertEqual(str(caught.exception), code)

    def test_closed_transform_order_clip_and_numeric_failure_are_explicit(self):
        import math
        state = candidate_state()
        state['embed_mean'][0] = 1
        state['column_mean'][0], state['column_std'][0] = 1, 2
        state['column_mean'][16], state['column_std'][16] = 1, 3
        state['coef'][1], state['coef'][17], state['coef'][30] = 2, -1, 1
        features = np.zeros((1, 1037), dtype=np.float32)
        features[0, 0], features[0, 1024] = 5, 7
        actual = predict_candidate(features, np.array([.75]), state)
        self.assertAlmostEqual(actual[0], 3 * math.e / (1 + 3 * math.e), places=15)
        identity = candidate_state()
        identity['coef'][30] = 1
        actual = predict_candidate(np.zeros((4, 1037), dtype=np.float32), np.array([0., .2, .8, 1.]), identity)
        np.testing.assert_allclose(actual, [1e-6, .2, .8, 1 - 1e-6], rtol=0, atol=2e-16)
        overflow = candidate_state()
        overflow['coef'][1] = 1e308
        features[0, 0] = np.finfo(np.float32).max
        with self.assertRaises(ValueError) as caught:
            predict_candidate(features, np.array([.5]), overflow)
        self.assertEqual(getattr(caught.exception, 'code', None), 'candidate_numerical_failure')

    def test_saved_eigenvalues_use_frozen_leading_rank_condition(self):
        features = np.zeros((1, 1037), dtype=np.float32)
        state = candidate_state()
        state['eigenvalues'][-1] = -1e-15
        np.testing.assert_array_equal(predict_candidate(features, np.array([.5]), state), [.5])
        state['eigenvalues'][15:] = 1e-12
        with self.assertRaises(ValueError) as caught:
            predict_candidate(features, np.array([.5]), state)
        self.assertEqual(caught.exception.code, 'invalid_candidate_state')
        state['eigenvalues'][:] = 1
        state['eigenvalues'][0] = 1e13
        with self.assertRaises(ValueError) as caught:
            predict_candidate(features, np.array([.5]), state)
        self.assertEqual(caught.exception.code, 'invalid_candidate_state')


def _digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _pin(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')
    return _pin(path)


def fixed_fixture(root, state=None):
    """Construct invented checkpoints and independently replayable audit proof."""
    import copy
    import torch
    import multiphone_models
    from r_confirmatory import calibrate, calibration_audit
    from r_confirmatory_run import prediction
    bundle = root / 'bundle'
    bundle.mkdir()
    for name, width in [('scalar.pt', 13), ('compact.pt', 29)]:
        with torch.random.fork_rng(devices=[]):
            model = multiphone_models.MeanPoolPhoneRatingHead(width, num_phones=24, hidden_dim=128, dropout=.1)
        for parameter in model.parameters():
            parameter.data.zero_()
        torch.save({'model': model.state_dict(), 'mean': torch.zeros(width),
                    'std': torch.ones(width), 'epochs': 1}, bundle / name)
    torch.save({'center': torch.zeros(1024, dtype=torch.float64),
                'basis': torch.eye(1024, 16, dtype=torch.float64)}, bundle / 'projection.pt')
    _write_json(bundle / 'provenance.json', {'inventedFixture': True})
    phones = ['B','P','M','T','D','N','K','G','F','V','S','Z','SH','CH','JH','L','R','W','Y','HH','TH','DH','NG']
    flags = {'researchOnly': True, 'learnerFeedbackEligible': False, 'clinicalUseEligible': False, 'productionUseEligible': False}
    manifest = {'schemaVersion': 1, 'kind': 'cadence-expanded-child-mixture', 'ageRangeYears': [6,12],
                'featureWidth': 1037, 'targetPhones': phones, 'mixtureWeights': [.5,.5],
                'modelSourceSha256': hashlib.sha256(Path(multiphone_models.__file__).read_bytes()).hexdigest(),
                'files': {name: _pin(bundle / name)['sha256'] for name in ['scalar.pt','compact.pt','projection.pt','provenance.json']},
                **{key: False for key in ['learnerFeedbackEligible','clinicalUseEligible','promotionEligible']}}
    manifest_pin = _write_json(bundle / 'manifest.json', manifest)
    np.savez(root / 'candidate.npz', **(candidate_state() if state is None else state))
    candidate_pin = _pin(root / 'candidate.npz')
    canonical = {'children': [{'childId': 'C1'}, {'childId': 'C2'}],
                 'selectedTokens': [{'childId': 'C1', 'tokenId': 'T1'}, {'childId': 'C2', 'tokenId': 'T2'}],
                 'rows': [{'childId': c, 'tokenId': t, 'retainedProbability': 2/3, 'positiveVotes': 1, 'negativeVotes': 1} for c,t in [('C1','T1'),('C2','T2')]]}
    control = {'schemaVersion': 1, 'status': 'supplied_input_fit_preparation_not_study_declaration', **flags,
        'fullChildDenominator': 2, 'selectedTokenDenominator': 2, 'canonicalInput': canonical,
        'inputDigest': _digest_json(canonical), 'membershipDigest': _digest_json({key: canonical[key] for key in ['children','selectedTokens']}),
        'digestFormat': 'sha256_utf8_json_sort_keys_compact_ensure_ascii_false',
        'source': {'module': 'r_confirmatory.calibrate', 'sha256': _pin(Path(calibrate.__file__))['sha256']},
        'dependencies': {'python': '3.13.14', 'numpy': np.__version__, 'scipy': '1.17.1', 'dtype': 'float64'},
        'recipe': copy.deepcopy(calibrate._RECIPE),
        'initialization': {'weightedTargetMean': .5, 'clippedWeightedTargetMean': .5, 'intercept': 0., 'slope': 0.},
        'coefficients': {'intercept': 0., 'slope': 0.},
        'transform': {'logitMean': math.log(2/3)-math.log1p(-2/3), 'logitPopulationStd': 0., 'logitScale': 1., 'inputClip': 1e-6},
        'weights': [{'childId': c, 'tokenId': t, 'weight': .5} for c,t in [('C1','T1'),('C2','T2')]],
        'unconstrained': {'coefficients': {'intercept': 0., 'slope': 0.}, 'diagnostics': {'objective': math.log(2), 'gradient': [0.,0.], 'gradientInfinityNorm': 0., 'newtonSteps': 0, 'steps': []}},
        'boundaryApplied': False,
        'projected': {'objective': math.log(2), 'gradient': [0.,0.], 'projectedGradient': [0.,0.], 'projectedGradientInfinityNorm': 0.},
        'fittedPredictions': [{'childId': c, 'tokenId': t, 'probability': .5} for c,t in [('C1','T1'),('C2','T2')]]}
    control_pin = _write_json(root / 'calibration/fit/control.json', control)
    declaration = {'schemaVersion': 1, 'artifactType': 'saved_dev_calibration_declaration', 'root': str(root / 'calibration'),
                   **flags, 'expectedCounts': {'devChildren': 2, 'completeTokens': 2},
                   'payload': {'path': str(root / 'calibration/payload.json'), 'sha256': 'a'*64},
                   'environment': {'python': '3.13.14'}, 'inputBindings': {}, 'sourceBindings': {'fit': _pin(Path(calibrate.__file__))}}
    declaration_pin = _write_json(root / 'calibration/declaration.json', declaration)
    fit = {'schemaVersion': 1, 'stage': 'fit', 'status': 'completed', **flags, 'calibrationFitPerformed': True,
           'declaration': declaration_pin, 'started': {'path': str(root / 'calibration/fit/started.json'), 'sha256': 'b'*64},
           'control': control_pin, 'payload': declaration['payload'], 'environment': declaration['environment']}
    fit_pin = _write_json(root / 'calibration/fit/completion.json', fit)
    report = calibration_audit.audit_calibration(canonical, control)
    audit_pin = _write_json(root / 'calibration/audit/audit.json', report)
    audit_completion = {'schemaVersion': 1, 'stage': 'audit', 'status': 'completed', **flags, 'calibrationFitPerformed': True,
                        'declaration': declaration_pin, 'fitCompletion': fit_pin, 'control': control_pin, 'audit': audit_pin}
    audit_completion_pin = _write_json(root / 'calibration/audit/completion.json', audit_completion)
    project = Path(prediction.__file__).resolve().parents[3]
    source_paths = {'prediction': Path(prediction.__file__), 'retainedLoader': project/'research/audio-head/ages_6_12_bundle/inference.py',
        'retainedPackageInit': project/'research/audio-head/ages_6_12_bundle/__init__.py', 'retainedModelSource': Path(multiphone_models.__file__),
        'calibrationPredict': Path(calibrate.__file__), 'calibrationPackageInit': project/'research/audio-head/r_confirmatory/__init__.py'}
    sources = {name: _pin(path) for name,path in source_paths.items()}
    pins = [candidate_pin, manifest_pin, control_pin, declaration_pin, fit_pin, audit_pin, audit_completion_pin, _pin(Path(calibration_audit.__file__))] + list(sources.values())
    protocol = {'schemaVersion': 1, 'candidateCheckpointSha256': candidate_pin['sha256'], 'retainedManifestSha256': manifest_pin['sha256'],
                'bindings': {pin['path']: {'sha256': pin['sha256']} for pin in pins},
                'runtimeVersions': {'python': '3.13.14', 'dependencies': {'numpy': '2.2.6', 'scipy': '1.17.1', 'torch': '2.8.0'}},
                'fixedCalibration': {'fullDEVChildren': 2, 'fitTokens': 2, 'auditOutcome': 'verified',
                                     'calibration': {key: control[key] for key in ['coefficients','transform','recipe']}}}
    protocol_pin = _write_json(root / 'protocol.json', protocol)
    return {'candidate_binding': candidate_pin, 'retained_manifest_binding': manifest_pin,
            'calibration_binding': control_pin, 'source_bindings': sources, 'protocol_binding': protocol_pin}


class FixedPredictorTests(unittest.TestCase):
    def test_synthetic_fixed_loader_produces_three_literal_probabilities_without_fitting(self):
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-fixture-') as directory:
            fixture = fixed_fixture(Path(directory).resolve())
            predictor = load_fixed_predictor(**fixture, synthetic=True)
            result = predictor.predict(np.zeros(1037, dtype=np.float32), 9)
            np.testing.assert_allclose(result['retained']['probabilities'], [1/3,1/3,1/3], rtol=0, atol=2e-16)
            self.assertAlmostEqual(result['retained']['pError'], 2/3, places=15)
            self.assertEqual(result['candidate'], {'pError': .5})
            self.assertEqual(result['calibration'], {'pError': .5})
            self.assertFalse(predictor.production_bound)

    def test_factory_is_required_and_candidate_numeric_failure_preserves_other_arms(self):
        with self.assertRaises(ValueError) as caught:
            FixedPredictor()
        self.assertEqual(getattr(caught.exception, 'code', None), 'factory_required')
        state = candidate_state()
        state['coef'][1] = 1e308
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-overflow-') as directory:
            fixture = fixed_fixture(Path(directory).resolve(), state=state)
            predictor = load_fixed_predictor(**fixture, synthetic=True)
            features = np.zeros(1037, dtype=np.float32)
            features[0] = np.finfo(np.float32).max
            result = predictor.predict(features, 9)
            self.assertAlmostEqual(result['retained']['pError'], 2/3, places=15)
            self.assertEqual(result['candidate'], {'failureCode': 'candidate_prediction_failure'})
            self.assertEqual(result['calibration'], {'pError': .5})

    def test_protocol_schema_type_and_production_binding_cannot_be_relaxed(self):
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-mode-') as directory:
            fixture = fixed_fixture(Path(directory).resolve())
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**fixture)
            self.assertEqual(caught.exception.code, 'production_binding_mismatch')
            protocol_path = Path(fixture['protocol_binding']['path'])
            protocol = json.loads(protocol_path.read_text())
            protocol['schemaVersion'] = True
            fixture['protocol_binding'] = _write_json(protocol_path, protocol)
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**fixture, synthetic=True)
            self.assertEqual(caught.exception.code, 'invalid_protocol')

    def test_saved_audit_semantic_digest_is_distinct_from_control_file_hash(self):
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-audit-') as directory:
            root = Path(directory).resolve()
            fixture = fixed_fixture(root)
            audit_path = root / 'calibration/audit/audit.json'
            report = json.loads(audit_path.read_text())
            self.assertNotEqual(report['controlSha256'], fixture['calibration_binding']['sha256'])
            report['controlSha256'] = fixture['calibration_binding']['sha256']
            audit_pin = _write_json(audit_path, report)
            completion_path = root / 'calibration/audit/completion.json'
            completion = json.loads(completion_path.read_text())
            completion['audit'] = audit_pin
            completion_pin = _write_json(completion_path, completion)
            protocol_path = Path(fixture['protocol_binding']['path'])
            protocol = json.loads(protocol_path.read_text())
            for pin in [audit_pin, completion_pin]:
                protocol['bindings'][pin['path']]['sha256'] = pin['sha256']
            fixture['protocol_binding'] = _write_json(protocol_path, protocol)
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**fixture, synthetic=True)
            self.assertEqual(caught.exception.code, 'invalid_calibration_provenance')

    def test_source_path_hash_and_pickle_state_mismatch_fail_before_prediction(self):
        import copy
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-source-') as directory:
            fixture = fixed_fixture(Path(directory).resolve())
            changed = copy.deepcopy(fixture)
            changed['source_bindings']['prediction']['sha256'] = '0' * 64
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**changed, synthetic=True)
            self.assertEqual(caught.exception.code, 'binding_hash_mismatch')
            changed = copy.deepcopy(fixture)
            changed['source_bindings']['retainedLoader'] = changed['source_bindings']['retainedModelSource']
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**changed, synthetic=True)
            self.assertEqual(caught.exception.code, 'source_path_mismatch')
        state = candidate_state()
        state['coef'] = np.array(['PRIVATE_SENTINEL'] * 31, dtype=object)
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-pickle-') as directory:
            fixture = fixed_fixture(Path(directory).resolve(), state=state)
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**fixture, synthetic=True)
            self.assertEqual(caught.exception.code, 'invalid_candidate_checkpoint')
            self.assertEqual(str(caught.exception), 'invalid_candidate_checkpoint')

    def test_frozen_runtime_and_completed_age_are_enforced(self):
        with tempfile.TemporaryDirectory(prefix='fixed-predictor-runtime-') as directory:
            fixture = fixed_fixture(Path(directory).resolve())
            predictor = load_fixed_predictor(**fixture, synthetic=True)
            for age in (5, 13, 9.0, True):
                with self.subTest(age=age):
                    with self.assertRaises(ValueError) as caught:
                        predictor.predict(np.zeros(1037, dtype=np.float32), age)
                    self.assertEqual(caught.exception.code, 'invalid_completed_age')
            for features in (np.zeros(1036, dtype=np.float32), np.zeros(1037, dtype=np.float64), np.full(1037, np.nan, dtype=np.float32)):
                with self.assertRaises(ValueError) as caught:
                    predictor.predict(features, 9)
                self.assertEqual(caught.exception.code, 'invalid_features')
            protocol_path = Path(fixture['protocol_binding']['path'])
            protocol = json.loads(protocol_path.read_text())
            protocol['runtimeVersions']['dependencies']['numpy'] = '0.0.0'
            fixture['protocol_binding'] = _write_json(protocol_path, protocol)
            with self.assertRaises(ValueError) as caught:
                load_fixed_predictor(**fixture, synthetic=True)
            self.assertEqual(caught.exception.code, 'runtime_mismatch')


if __name__ == '__main__':
    unittest.main()
