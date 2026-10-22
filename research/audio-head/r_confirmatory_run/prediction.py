"""Fixed feature-only confirmation predictions; no fitting or audio processing."""
from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import types

import numpy as np
import scipy
from scipy.special import expit


FEATURE_WIDTH = 1037
TARGET_ID = 16
CANDIDATE_SHA256 = '7867466527c7f2edbeb2df12416c5b63b97bb66f9f95270f368b1a0d746a815d'
RETAINED_MANIFEST_SHA256 = 'bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf'
FROZEN_PROTOCOL_SHA256 = '458872741505a761719ff29d6be48abc8e06d4b402566a8e0625612b259b9940'
_STATE_SHAPES = {'embed_mean': (1024,), 'components': (16, 1024),
                 'column_mean': (30,), 'column_std': (30,),
                 'eigenvalues': (1024,), 'coef': (31,), 'lambda': ()}


class PredictionError(ValueError):
    """Fixed diagnostics without source values, model data, or paths."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _features(features):
    if (not isinstance(features, np.ndarray) or features.dtype != np.float32
            or features.ndim != 2 or features.shape[0] < 1
            or features.shape[1] != FEATURE_WIDTH or not np.isfinite(features).all()):
        raise PredictionError('invalid_features')
    return features


def _probabilities(probabilities, count):
    values = np.asarray(probabilities)
    if (values.dtype.kind != 'f' or values.shape != (count,)
            or not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1)):
        raise PredictionError('invalid_retained_probabilities')
    return values.astype(np.float64)


def _candidate_state(state, *, production=False):
    if type(state) is not dict or set(state) != set(_STATE_SHAPES) | {'indices'}:
        raise PredictionError('invalid_candidate_state')
    for key, shape in _STATE_SHAPES.items():
        value = state[key]
        if (not isinstance(value, np.ndarray) or value.dtype != np.float64
                or value.shape != shape or not np.isfinite(value).all()):
            raise PredictionError('invalid_candidate_state')
    indices = state['indices']
    if (not isinstance(indices, np.ndarray) or indices.dtype.kind not in 'iu'
            or indices.ndim != 1 or not 1 <= len(indices) <= 10000000
            or (production and len(indices) != 4534) or np.any(indices < 0)
            or len(np.unique(indices)) != len(indices)):
        raise PredictionError('invalid_candidate_state')
    # The frozen fitter sorts eigenvalues descending and checks only rank 16.
    # Unused covariance eigenvalues can be slightly negative from roundoff.
    eigenvalues = state['eigenvalues']
    if (state['lambda'].item() != .01 or np.any(state['column_std'] <= 0)
            or eigenvalues[15] <= 1e-12 * max(1, eigenvalues[0])):
        raise PredictionError('invalid_candidate_state')
    with np.errstate(over='ignore', invalid='ignore'):
        gram = state['components'] @ state['components'].T
    if (not np.isfinite(gram).all()
            or not np.allclose(gram, np.eye(16), rtol=0, atol=1e-8)):
        raise PredictionError('invalid_candidate_state')
    return state


def predict_candidate(features, retained_probabilities, state):
    """Apply the closed PCA16 + 13 scalars + retained-logit formula."""
    values = _features(features).astype(np.float64)
    retained = _probabilities(retained_probabilities, len(values))
    state = _candidate_state(state)
    try:
        with np.errstate(over='raise', divide='raise', invalid='raise'):
            clipped = np.clip(retained, 1e-6, 1 - 1e-6)
            retained_logit = np.log(clipped) - np.log1p(-clipped)
            raw = np.column_stack(((values[:, :1024] - state['embed_mean']) @ state['components'].T,
                                   values[:, 1024:], retained_logit))
            design = (raw - state['column_mean']) / state['column_std']
            logits = state['coef'][0] + design @ state['coef'][1:]
    except FloatingPointError:
        raise PredictionError('candidate_numerical_failure') from None
    probabilities = expit(logits)
    if (not np.isfinite(logits).all() or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0) or np.any(probabilities > 1)):
        raise PredictionError('candidate_numerical_failure')
    return probabilities


# Every repository dependency is read at its fixed source location. Bundle code
# is never executed; its unchanged loader receives only the declared directory.
_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATHS = {
    'prediction': Path(__file__).resolve(),
    'retainedLoader': _ROOT / 'research/audio-head/ages_6_12_bundle/inference.py',
    'retainedPackageInit': _ROOT / 'research/audio-head/ages_6_12_bundle/__init__.py',
    'retainedModelSource': _ROOT / 'research/audio-head/multiphone_models.py',
    'calibrationPredict': _ROOT / 'research/audio-head/r_confirmatory/calibrate.py',
    'calibrationPackageInit': _ROOT / 'research/audio-head/r_confirmatory/__init__.py',
}
_FROZEN_SOURCES = {
    'retainedLoader': 'dd3009f5b923cb64ce4a6ddf161fdc48480fd0b8bc7cd103d54239c258f41b94',
    'retainedPackageInit': 'cae696b6b14351155a0658eb38d910b584035ea78ac8e4d7766a7cac323a8b84',
    'retainedModelSource': '0e254f967b4c8dc5c5fe0a3bd2cbae05c62c480b6360cdb1912403271568987a',
    'calibrationPredict': 'd73dd06389d8652bf6dd23d7d1dbf2e438baa263d77de663b25bb12d6152538e',
    'calibrationPackageInit': '39d9c5a7b5949300ec8186483eba54b054258050cfb9aed68a80b47fe29f288a',
}
_CANDIDATE_PATH = _ROOT / 'research/audio-head/outputs/percept-r-binary-head-20261002/v1/final/full-dev-candidate.npz'
_RETAINED_PATHS = {
    _ROOT / 'research/audio-head/outputs/multiphone-20260927/ages-6-12-mixture-v1/bundle/manifest.json',
    _ROOT / 'work/ages-6-12-bundle-20260927/portable/bundle/manifest.json',
}
_CONTROL_PATH = _ROOT / 'research/audio-head/outputs/r-confirmatory-preparation-20261003/calibration-v1/fit/control.json'
_PROTOCOL_PATH = _ROOT / 'docs/consumer-assessment/r-confirmatory-frozen-protocol-20261003.json'
_AUDITOR_PATH = _ROOT / 'research/audio-head/r_confirmatory/calibration_audit.py'
_AUDITOR_SHA256 = '7fb1980a02eba3834cfc0c533941a9af6930fab2b8b625d802f5022a773b3520'
_FLAGS = {'researchOnly': True, 'learnerFeedbackEligible': False,
          'clinicalUseEligible': False, 'productionUseEligible': False}
_HEX = re.compile(r'[0-9a-f]{64}')


def _require(condition, code):
    if not condition:
        raise PredictionError(code)


def _binding(value):
    _require(type(value) is dict and set(value) == {'path', 'sha256'}
             and type(value['path']) is str and type(value['sha256']) is str
             and _HEX.fullmatch(value['sha256']) is not None, 'invalid_binding')
    path = Path(value['path'])
    _require(path.is_absolute() and path == path.resolve(), 'invalid_binding_path')
    return path


def _read_verified(binding):
    path = _binding(binding)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            _require(stat.S_ISREG(os.fstat(fd).st_mode), 'nonregular_binding')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = stream.read()
        finally:
            os.close(fd)
    except OSError:
        raise PredictionError('binding_read_failed') from None
    _require(hashlib.sha256(data).hexdigest() == binding['sha256'], 'binding_hash_mismatch')
    return data


def _json(data):
    def pairs(items):
        result = {}
        for name, value in items:
            _require(name not in result, 'invalid_json')
            result[name] = value
        return result

    def constant(_):
        raise PredictionError('invalid_json')

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError):
        raise PredictionError('invalid_json') from None


def _semantic_digest(value):
    try:
        data = json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError):
        raise PredictionError('invalid_json') from None
    return hashlib.sha256(data).hexdigest()


def _protocol_pin(protocol, path):
    try:
        relative = path.relative_to(_ROOT).as_posix()
    except ValueError:
        relative = str(path)
    entries = protocol.get('bindings')
    _require(type(entries) is dict, 'invalid_protocol_bindings')
    entry = entries.get(relative, entries.get(str(path)))
    _require(type(entry) is dict and type(entry.get('sha256')) is str
             and _HEX.fullmatch(entry['sha256']) is not None, 'missing_protocol_binding')
    return {'path': str(path), 'sha256': entry['sha256']}


def _load_module(name, path, data, *, model_source=None):
    """Execute only pinned source bytes, without reopening code or cache reuse."""
    module = types.ModuleType(name)
    module.__file__ = str(path)
    namespace = module.__dict__
    if model_source is not None:
        original_import = builtins.__import__

        def pinned_import(import_name, globals=None, locals=None, fromlist=(), level=0):
            if import_name == 'multiphone_models' and level == 0:
                return model_source
            return original_import(import_name, globals, locals, fromlist, level)

        namespace['__builtins__'] = {**vars(builtins), '__import__': pinned_import}
    exec(compile(data, str(path), 'exec'), namespace)
    return module


def _sources(bindings):
    _require(type(bindings) is dict and set(bindings) == set(SOURCE_PATHS), 'invalid_source_bindings')
    blobs = {}
    for name, path in SOURCE_PATHS.items():
        _require(_binding(bindings[name]) == path, 'source_path_mismatch')
        if name != 'prediction':
            _require(bindings[name]['sha256'] == _FROZEN_SOURCES[name], 'frozen_source_mismatch')
        blobs[name] = _read_verified(bindings[name])
    return blobs


def _runtime(protocol, torch_module):
    versions = protocol.get('runtimeVersions')
    _require(type(versions) is dict and type(versions.get('dependencies')) is dict,
             'runtime_mismatch')
    actual = {'numpy': np.__version__, 'scipy': scipy.__version__,
              'torch': torch_module.__version__}
    _require(versions.get('python') == platform.python_version()
             and all(versions['dependencies'].get(name) == value
                     for name, value in actual.items()), 'runtime_mismatch')


def _candidate_npz(data, *, production):
    try:
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            _require(len(archive.files) == 8 and set(archive.files) == set(_STATE_SHAPES) | {'indices'},
                     'invalid_candidate_state')
            state = {name: archive[name].copy() for name in archive.files}
    except PredictionError:
        raise
    except Exception:
        raise PredictionError('invalid_candidate_checkpoint') from None
    _candidate_state(state, production=production)
    for value in state.values():
        value.setflags(write=False)
    return state


def _flags(value):
    return type(value) is dict and all(value.get(name) is expected for name, expected in _FLAGS.items())


def _calibration_proof(protocol, control, bindings, records, sources, *, production):
    """Check byte anchors and the saved audit's distinct semantic control digest."""
    try:
        declaration, fit, audit, completed = (records[name] for name in
                                               ('declaration', 'fitCompletion', 'audit', 'auditCompletion'))
        control_pin = bindings['control']
        _require(type(declaration['schemaVersion']) is int and declaration['schemaVersion'] == 1
                 and declaration['artifactType'] == 'saved_dev_calibration_declaration'
                 and declaration['root'] == str(Path(control_pin['path']).parent.parent)
                 and _flags(declaration), 'invalid_calibration_provenance')
        for record, stage in ((fit, 'fit'), (completed, 'audit')):
            _require(type(record.get('schemaVersion')) is int and record['schemaVersion'] == 1
                     and record['stage'] == stage and record['status'] == 'completed'
                     and record['calibrationFitPerformed'] is True and _flags(record)
                     and record['control'] == control_pin
                     and record['declaration'] == bindings['declaration'], 'invalid_calibration_provenance')
        _require(completed['fitCompletion'] == bindings['fitCompletion']
                 and completed['audit'] == bindings['audit']
                 and fit['payload'] == declaration['payload']
                 and fit['environment'] == declaration['environment'], 'invalid_calibration_provenance')
        fixed = protocol['fixedCalibration']
        _require(audit['outcome'] == 'verified' and _flags(audit)
                 and audit['controlSha256'] == _semantic_digest(control)
                 and audit['inputSha256'] == control['inputDigest'] == _semantic_digest(control['canonicalInput'])
                 and audit['auditorSourceSha256'] == _AUDITOR_SHA256
                 and _protocol_pin(protocol, _AUDITOR_PATH)['sha256'] == _AUDITOR_SHA256,
                 'invalid_calibration_provenance')
        _require(control['source'] == {'module': 'r_confirmatory.calibrate',
                                      'sha256': sources['calibrationPredict']['sha256']}
                 and declaration['sourceBindings']['fit'] == sources['calibrationPredict'],
                 'invalid_calibration_provenance')
        children, tokens = control['fullChildDenominator'], control['selectedTokenDenominator']
        _require(type(children) is int and children > 0 and type(tokens) is int and tokens > 0
                 and audit['fullChildDenominator'] == children == fixed['fullDEVChildren']
                 and audit['selectedTokenDenominator'] == tokens == fixed['fitTokens']
                 and declaration['expectedCounts']['devChildren'] == children
                 and declaration['expectedCounts']['completeTokens'] == tokens
                 and (not production or (children, tokens) == (119, 4534)), 'invalid_calibration_provenance')
        norm = audit['projectedGradientInfinityNorm']
        _require(type(norm) in (float, int) and np.isfinite(norm) and 0 <= norm <= 1e-8
                 and audit['numericTolerance'] == {'absolute': 1e-10, 'relative': 1e-10}
                 and fixed['auditOutcome'] == 'verified', 'invalid_calibration_provenance')
        _require(all(control[name] == fixed['calibration'][name] for name in
                     ('coefficients', 'transform', 'recipe')), 'invalid_calibration_provenance')
    except (KeyError, TypeError, OverflowError):
        raise PredictionError('invalid_calibration_provenance') from None


class FixedPredictor:
    """Three fixed feature-only arms, with independent numerical terminal results."""

    def __init__(self):
        raise PredictionError('factory_required')

    @classmethod
    def _from_verified_sources(cls, *, retained, state, control, calibration_predict,
                               source_bindings, production_bound, provenance):
        # This private construction path is called only after fixed factory
        # checks; the public API offers no model/callback constructor arguments.
        instance = object.__new__(cls)
        instance._retained = retained
        instance._state = state
        instance._control = control
        instance._calibration_predict = calibration_predict
        instance._sources = copy.deepcopy(source_bindings)
        instance._production_bound = production_bound
        instance._provenance = copy.deepcopy(provenance)
        return instance

    @property
    def production_bound(self):
        return self._production_bound

    @property
    def provenance(self):
        return copy.deepcopy(self._provenance)

    def predict(self, features, age_completed):
        _require(type(age_completed) is int and 6 <= age_completed <= 12, 'invalid_completed_age')
        _require(isinstance(features, np.ndarray) and features.dtype == np.float32
                 and features.shape == (FEATURE_WIDTH,), 'invalid_features')
        matrix = _features(features.reshape(1, FEATURE_WIDTH))
        _sources(self._sources)
        result = {}
        try:
            predicted = self._retained.predict(matrix, np.array([TARGET_ID], dtype=np.int64),
                                               age_years=age_completed)
            probabilities = predicted['probabilities']
            _require(isinstance(probabilities, np.ndarray) and probabilities.dtype.kind == 'f'
                     and probabilities.shape == (1, 3) and np.isfinite(probabilities).all()
                     and np.all(probabilities >= 0) and np.all(probabilities <= 1)
                     and np.isclose(probabilities.sum(), 1., rtol=0, atol=1e-8),
                     'invalid_retained_distribution')
            p_error = float(probabilities[0, 0] + probabilities[0, 1])
            _probabilities(np.array([p_error]), 1)
            result['retained'] = {'probabilities': probabilities[0].tolist(), 'pError': p_error}
        except Exception:
            result['retained'] = {'failureCode': 'retained_prediction_failure'}
            result['candidate'] = {'failureCode': 'retained_dependency_unavailable'}
            result['calibration'] = {'failureCode': 'retained_dependency_unavailable'}
        else:
            try:
                result['candidate'] = {'pError': float(predict_candidate(matrix, np.array([p_error]), self._state)[0])}
            except Exception:
                result['candidate'] = {'failureCode': 'candidate_prediction_failure'}
            try:
                calibrated = self._calibration_predict(self._control, [p_error])
                _require(type(calibrated) is list and len(calibrated) == 1, 'invalid_calibration_output')
                calibrated_value = _probabilities(np.asarray(calibrated), 1)[0]
                result['calibration'] = {'pError': float(calibrated_value)}
            except Exception:
                result['calibration'] = {'failureCode': 'calibration_prediction_failure'}
        _sources(self._sources)
        return result


def load_fixed_predictor(candidate_binding, retained_manifest_binding, calibration_binding,
                         source_bindings, *, protocol_binding, synthetic=False):
    """Load pinned fixed inference only; synthetic=True can never be production bound."""
    _require(type(synthetic) is bool, 'invalid_execution_mode')
    candidate_path, manifest_path, control_path, protocol_path = (
        _binding(value) for value in
        (candidate_binding, retained_manifest_binding, calibration_binding, protocol_binding))
    if not synthetic:
        _require(candidate_path == _CANDIDATE_PATH and candidate_binding['sha256'] == CANDIDATE_SHA256
                 and manifest_path in _RETAINED_PATHS
                 and retained_manifest_binding['sha256'] == RETAINED_MANIFEST_SHA256
                 and control_path == _CONTROL_PATH and protocol_path == _PROTOCOL_PATH
                 and protocol_binding['sha256'] == FROZEN_PROTOCOL_SHA256, 'production_binding_mismatch')
    _require(manifest_path.name == 'manifest.json'
             and control_path.name == 'control.json' and control_path.parent.name == 'fit',
             'purpose_binding_mismatch')
    protocol = _json(_read_verified(protocol_binding))
    _require(type(protocol) is dict and type(protocol.get('schemaVersion')) is int and protocol['schemaVersion'] == 1, 'invalid_protocol')
    source_blobs = _sources(source_bindings)
    for name, pin in source_bindings.items():
        if name != 'prediction':
            _require(_protocol_pin(protocol, SOURCE_PATHS[name]) == pin, 'protocol_source_mismatch')
    for pin, path in ((candidate_binding, candidate_path), (retained_manifest_binding, manifest_path),
                      (calibration_binding, control_path)):
        _require(_protocol_pin(protocol, path) == pin, 'purpose_binding_mismatch')
    _require(protocol.get('candidateCheckpointSha256') == candidate_binding['sha256']
             and protocol.get('retainedManifestSha256') == retained_manifest_binding['sha256'],
             'purpose_binding_mismatch')
    control_root = control_path.parent.parent
    proof_bindings = {'control': copy.deepcopy(calibration_binding)}
    for name, relative in (('declaration', 'declaration.json'), ('fitCompletion', 'fit/completion.json'),
                           ('audit', 'audit/audit.json'), ('auditCompletion', 'audit/completion.json')):
        proof_bindings[name] = _protocol_pin(protocol, control_root / relative)
    # All external byte anchors precede control/checkpoint parsing and imports.
    proof_blobs = {name: _read_verified(pin) for name, pin in proof_bindings.items()}
    candidate_blob = _read_verified(candidate_binding)
    manifest_blob = _read_verified(retained_manifest_binding)
    control = _json(proof_blobs['control'])
    proof_records = {name: _json(data) for name, data in proof_blobs.items() if name != 'control'}
    _calibration_proof(protocol, control, proof_bindings, proof_records, source_bindings,
                       production=not synthetic)
    manifest = _json(manifest_blob)
    _require(type(manifest) is dict and type(manifest.get('featureWidth')) is int
             and manifest['featureWidth'] == FEATURE_WIDTH and type(manifest.get('targetPhones')) is list
             and len(manifest['targetPhones']) > TARGET_ID and manifest['targetPhones'][TARGET_ID] == 'R',
             'invalid_retained_manifest')
    state = _candidate_npz(candidate_blob, production=not synthetic)
    model_source = _load_module('multiphone_models', SOURCE_PATHS['retainedModelSource'], source_blobs['retainedModelSource'])
    _runtime(protocol, model_source.torch)
    retained_source = _load_module('ages_6_12_bundle.inference', SOURCE_PATHS['retainedLoader'],
                                   source_blobs['retainedLoader'], model_source=model_source)
    calibration_source = _load_module('r_confirmatory.calibrate', SOURCE_PATHS['calibrationPredict'], source_blobs['calibrationPredict'])
    try:
        calibration_source.predict_calibration(control, [.5])
    except Exception:
        raise PredictionError('invalid_calibration_control') from None
    try:
        retained = retained_source.load_bundle(manifest_path.parent, retained_manifest_binding['sha256'])
    except Exception:
        raise PredictionError('invalid_retained_bundle') from None
    _sources(source_bindings)
    provenance = {'productionBound': not synthetic, 'researchOnly': True,
                  'learnerFeedbackEligible': False, 'clinicalUseEligible': False, 'productionUseEligible': False,
                  'candidateCheckpointSha256': candidate_binding['sha256'],
                  'retainedManifestSha256': retained_manifest_binding['sha256'],
                  'calibrationControlFileSha256': calibration_binding['sha256'],
                  'calibrationControlSemanticSha256': _semantic_digest(control),
                  'calibrationAuditSha256': proof_bindings['audit']['sha256'],
                  'frozenProtocolSha256': protocol_binding['sha256'], 'sourceBindings': source_bindings}
    return FixedPredictor._from_verified_sources(retained=retained, state=state, control=control,
                          calibration_predict=calibration_source.predict_calibration,
                          source_bindings=source_bindings, production_bound=not synthetic,
                          provenance=provenance)
