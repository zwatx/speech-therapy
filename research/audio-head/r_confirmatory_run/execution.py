"""Terminal fixed prediction execution, separate from outcome access.

Production mode decodes only explicitly declared selected recordings. Calling
these APIs does not authorize that access. Development uses synthetic inputs or
the separately permitted engineering fixture, never the reserved study.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import signal
import stat
import subprocess
import zipfile
from contextlib import contextmanager
import numpy as np

from . import stages
from .prediction import load_fixed_predictor, SOURCE_PATHS as PREDICTION_SOURCES, PredictionError
from .requests import project_selected_requests, cut_arguments

ROOT = Path(__file__).resolve().parents[3]
AUDIO = ROOT / 'research/audio-head'
PYTHON_INVOCATION = AUDIO / '.venv/bin/python'
NODE_EXECUTABLE = Path('/Users/zacharywilson/.local/share/mise/installs/node/24/bin/node')
CONTRACT = AUDIO / 'position_inference/contract-v2.json'
CONTRACT_SHA = 'f089324f893253f7dafb0b8920ed04eaf9d2e182e969645ccc7bcb1618d4d9ce'
PARENT_CONTRACT = AUDIO / 'experiments/multiphone-research-audio-v1.json'
EXTRACTOR_MANIFEST = AUDIO / 'outputs/multiphone-20260926/phonetic-final/unweighted-all-age/manifest.json'
EXTRACTOR_MANIFEST_SHA = 'd3c95f8d42fddb692708f7431ef4cf48a5abc4ab1be6a5e1afc4f5f705bb0be6'
SNAPSHOT = AUDIO / 'outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'
ARCHIVE = {'path': str(AUDIO / 'outputs/percept-r-source/PERCEPT-R.zip'),
           'sha256': '589535842e92a53a79c2614a0e07e9d357b79a4a421d61e5df7ecaebfd651a62'}
RAW_SOURCE_PATHS = tuple(AUDIO / name for name in (
    'position_inference/__init__.py', 'position_inference/audio.py',
    'multiphone_research_audio.py', 'multiphone_research_ctc.ts'))


class ExtractionFailure(ValueError):
    """Declared processing failure; integrity errors use RunStageError instead."""


@contextmanager
def _held_verified(binding):
    path = stages._path(binding['path'])
    directory_fd = stages._directory(path.parent)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(fd)
        stages._require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                        and before.st_nlink == 1, 'unsafe_source')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            stages._require(hashlib.file_digest(stream, 'sha256').hexdigest() == binding['sha256'], 'source_hash_differs')
            stream.seek(0)
            yield stream
            stream.seek(0)
            stages._require(hashlib.file_digest(stream, 'sha256').hexdigest() == binding['sha256'], 'source_hash_differs')
            after = os.fstat(fd)
            current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            stages._require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), 'source_identity_changed')
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory_fd)


def _copy_recording(binding, directory, directory_fd):
    copy_path = directory / 'source.wav'
    fd = os.open(copy_path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, 'wb') as destination, _held_verified(binding) as source:
        os.fchmod(destination.fileno(), 0o600)
        sha = hashlib.sha256()
        while block := source.read(65536):
            sha.update(block)
            destination.write(block)
        destination.flush()
        os.fsync(destination.fileno())
        stages._require(sha.hexdigest() == binding['sha256'], 'copied_source_hash_differs')
    return {'path': str(copy_path), 'sha256': binding['sha256']}


def read_extracted_features(directory, report_pin, audio_pin, prompt_pin, prompt, config, parent):
    """Validate serialized extractor output, without using its incidental head scores."""
    directory = Path(directory)
    stages._require(report_pin['path'] == str(directory / 'report.json'), 'extractor_report_path_differs')
    report = stages._json(stages._binding(report_pin, private=True))
    target = prompt['targets'][0]
    expected_target = {**target, 'modelTargetId': 16}
    matrix = report.get('featureMatrix', {})
    rows = report.get('targets', [])
    stages._require(report.get('schemaVersion') == 2 and report.get('complete') is True
        and report.get('researchOnly') is True and report.get('trainingPerformed') is False
        and report.get('clinicalUseEligible') is False and report.get('learnerFeedbackEligible') is False
        and report.get('contractSha256') == config['contract']['sha256']
        and report.get('headManifestSha256') == config['extractorManifest']['sha256']
        and report.get('featureSourceBindingSha256') == parent['featureSourceBindingSha256']
        and report.get('inputBindings', {}).get('audio') == audio_pin
        and report.get('inputBindings', {}).get('prompt') == prompt_pin
        and matrix == {'path': 'features.npy', 'dtype': 'float32', 'shape': [1, 1037],
                       'columns': parent['featureColumns']}
        and report.get('canonicalPrompt', {}).get('transcript') == prompt['transcript']
        and report.get('canonicalPrompt', {}).get('canonicalPhones') == prompt['words'][0]['phones']
        and len(rows) == 1 and all(rows[0].get(k) == v for k, v in expected_target.items())
        and report.get('ctcRuntime', {}).get('fetchAttempts') == 0, 'extractor_output_differs')
    features_pin = {'path': str(directory / 'features.npy'), 'sha256': report['filesSha256']['features.npy']}
    blob = stages._binding(features_pin, private=True)
    values = np.load(io.BytesIO(blob), allow_pickle=False)
    stages._require(isinstance(values, np.ndarray) and values.dtype == np.float32
                    and values.shape == (1, 1037) and np.isfinite(values).all(), 'extractor_features_differs')
    return values[0], {'report': report_pin, 'features': features_pin}


def _file_pin(path):
    """Stream large declared recordings rather than copying them into memory."""
    path = stages._path(path)
    directory_fd = stages._directory(path.parent)
    fd = None
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(fd)
        stages._require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                        and before.st_nlink == 1, 'unsafe_recording')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(fd)
        stages._require((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'recording_changed')
        return {'path': str(path), 'sha256': sha}
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory_fd)


def _run(arguments, timeout, *, decoder=False):
    # Fixed argument arrays, no shell, no downloaded runtime or arbitrary logs.
    process = subprocess.Popen(arguments, cwd=AUDIO, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                env={**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                     'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'})
    try:
        code = process.wait(timeout=timeout)
    except BaseException as error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        if isinstance(error, subprocess.TimeoutExpired):
            raise ExtractionFailure('worker_timeout') from None
        raise
    if code != 0 and decoder:
        raise ExtractionFailure('decoder_failed')
    stages._require(code == 0, 'extractor_worker_failed')


def extract_recording(directory, source_pin, token, prompt, runtime, parent_contract):
    """One private exclusive cut/extraction attempt; no retry or app capture guards."""
    directory = stages._path(directory)
    stages._require(directory.is_relative_to(AUDIO / 'outputs'), 'extractor_output_root_differs')
    try:
        fd = stages._fresh(directory)
    except OSError:
        raise stages.RunStageError('extraction_destination_consumed') from None
    try:
        stages._write(fd, directory, 'started.json', {'schemaVersion': 1, 'tokenId': token['tokenId'],
                          'source': source_pin, 'runtime': runtime, **stages.FLAGS})
        decoded_source = _copy_recording(source_pin, directory, fd)
        for role in ('python', 'node', 'ffmpeg', 'contract', 'extractorManifest'):
            stages._binding(runtime[role])
        prompt_pin = stages._write(fd, directory, 'prompt.json', prompt)
        clip = directory / 'clip.wav'
        # Fresh directory owns the clip name. Never infer success from ffmpeg -n.
        stages._require(not clip.exists() and not clip.is_symlink(), 'clip_already_exists')
        arguments = cut_arguments(runtime['ffmpeg']['path'], decoded_source['path'], token, clip)
        _run(arguments, 120, decoder=True)
        clip.chmod(0o600)
        clip_pin = _file_pin(str(clip))
        output = directory / 'raw'
        _run([runtime['pythonInvocation'], '-m', 'position_inference.audio',
              '--wav', str(clip), '--wav-sha256', clip_pin['sha256'],
              '--prompt', prompt_pin['path'], '--prompt-sha256', prompt_pin['sha256'],
              '--bundle', str(Path(runtime['extractorManifest']['path']).parent),
              '--manifest-sha256', runtime['extractorManifest']['sha256'],
              '--contract', runtime['contract']['path'], '--contract-sha256', runtime['contract']['sha256'],
              '--phonetic-snapshot', runtime['phoneticSnapshot'], '--node', runtime['node']['path'],
              '--output', str(output)], 180)
        report_pin = _file_pin(str(output / 'report.json'))
        features, outputs = read_extracted_features(output, report_pin, clip_pin, prompt_pin,
                                                   prompt, runtime, parent_contract)
        stages._require(_file_pin(source_pin['path']) == source_pin, 'recording_binding_differs')
        for role in ('python', 'node', 'ffmpeg', 'contract', 'extractorManifest'):
            stages._binding(runtime[role])
        receipt = stages._write(fd, directory, 'completion.json', {'schemaVersion': 1,
            'status': 'completed', 'tokenId': token['tokenId'], 'source': source_pin,
            'decodedSource': decoded_source, 'clip': clip_pin, 'prompt': prompt_pin, 'outputs': outputs, 'runtime': runtime,
            'cutArguments': arguments, 'incidentalExtractorHeadScoresUsed': False, **stages.FLAGS})
        return features, receipt
    except BaseException as error:
        code = str(error) if isinstance(error, ExtractionFailure) else 'extraction_integrity_failure'
        if not isinstance(error, Exception):
            code = 'interrupted'
        stages._write(fd, directory, 'failure.json', {'schemaVersion': 1, 'status': 'failed',
                      'code': code, 'tokenId': token['tokenId'], **stages.FLAGS})
        if isinstance(error, ExtractionFailure) or not isinstance(error, Exception):
            raise
        raise stages.RunStageError('extraction_integrity_failure') from None
    finally:
        os.close(fd)


def _raw_config(config, selected, protocol):
    stages._require(set(config) == {'schemaVersion', 'mode', 'archive', 'sessions', 'runtime'}
                    and config['schemaVersion'] == 1 and config['mode'] == 'reserved_test', 'invalid_execution_inputs')
    runtime = config['runtime']
    stages._require(set(runtime) == {'python', 'pythonInvocation', 'node', 'ffmpeg', 'contract', 'extractorManifest',
                                   'phoneticSnapshot', 'sourceBindings'}, 'invalid_extractor_runtime')
    stages._require(config['archive'] == ARCHIVE
        and runtime['contract'] == {'path': str(CONTRACT), 'sha256': CONTRACT_SHA}
        and runtime['extractorManifest'] == {'path': str(EXTRACTOR_MANIFEST), 'sha256': EXTRACTOR_MANIFEST_SHA}
        and runtime['phoneticSnapshot'] == str(SNAPSHOT), 'frozen_extractor_identity_differs')
    expected = {str(p): protocol['bindings'][str(p.relative_to(ROOT))]['sha256'] for p in RAW_SOURCE_PATHS}
    stages._require(runtime['sourceBindings'] == expected, 'extractor_source_identity_differs')
    stages._require(runtime['pythonInvocation'] == str(PYTHON_INVOCATION), 'python_environment_path_differs')
    for role, executable in (('python', PYTHON_INVOCATION),
                             ('ffmpeg', Path('/opt/homebrew/bin/ffmpeg')), ('node', NODE_EXECUTABLE)):
        stages._require(runtime[role]['path'] == str(executable.resolve()), 'executable_path_differs')
    needed = {(t['folder'], t['session']) for t in selected}
    sessions = {}
    for row in config['sessions']:
        stages._require(set(row) == {'folder', 'session', 'xmlMember', 'recording'}, 'invalid_session_binding')
        key = row['folder'], row['session']
        stages._require(key in needed and key not in sessions
            and row['xmlMember'] == f'0phon/{key[0]}/{key[1]}.xml', 'session_membership_differs')
        if row['recording'] is not None:
            stages._require(row['recording']['path'] == str(AUDIO / 'outputs/percept-r-source/media' / key[0] / (key[1]+'.wav')),
                            'recording_path_differs')
            stages._anchor(row['recording']['sha256'])
        sessions[key] = row
    stages._require(set(sessions) == needed, 'incomplete_session_manifest')
    # All role/path checks above precede source, archive, recording access.
    for path, sha in expected.items():
        stages._binding({'path': path, 'sha256': sha})
    for role in ('python', 'node', 'ffmpeg', 'contract', 'extractorManifest'):
        stages._binding(runtime[role])
    parent_pin = protocol['bindings'][str(PARENT_CONTRACT.relative_to(ROOT))]
    parent = stages._json(stages._binding({'path': str(PARENT_CONTRACT), 'sha256': parent_pin['sha256']}))
    return sessions, runtime, parent


def generate_predictions(root, declaration_sha256, execution_inputs_binding):
    """Invoke the fixed adapter and publish one anchored full-roster envelope.

    Synthetic mode accepts explicitly invented float32 features and fabricated
    model artifacts. Production accepts only the fixed raw-recording path.
    There is no caller-supplied model/prediction callback or feature-cache mode.
    """
    def generate(root, declaration, declaration_pin, directory, previous):
        profile = declaration['profile']
        stages._require(profile.get('executionInputs') == execution_inputs_binding, 'execution_inputs_not_declared')
        for role, path in {'execution': Path(__file__).resolve(),
                           'requests': Path(__file__).with_name('requests.py'),
                           **PREDICTION_SOURCES}.items():
            stages._require(profile['sourceBindings'].get(role, {}).get('path') == str(path), 'missing_execution_source')
        config = stages._json(stages._binding(execution_inputs_binding, private=True))
        synthetic = profile['mode'] == 'synthetic'
        inputs = profile['inputBindings']
        prepared = stages._json(stages._binding(inputs['preparedTokens']))
        selected = [t for t in prepared['tokens'] if t['disposition'] == 'selected']
        selected.sort(key=lambda t: (t['childId'], t['tokenId']))
        fixed = load_fixed_predictor(inputs['candidate'], inputs['retained'], inputs['calibration'],
            {k: profile['sourceBindings'][k] for k in PREDICTION_SOURCES},
            protocol_binding=inputs['frozenProtocol'], synthetic=synthetic)
        stages._require(fixed.production_bound is (not synthetic), 'predictor_mode_differs')
        evidence = []
        arms = {arm: [] for arm in ('candidate', 'retained', 'calibration')}
        if synthetic:
            stages._require(set(config) == {'schemaVersion', 'mode', 'featureRows'}
                and config['schemaVersion'] == 1 and config['mode'] == 'synthetic', 'invalid_synthetic_execution')
            feature_rows = {}
            for row in config['featureRows']:
                stages._require(set(row) == {'tokenId', 'features', 'ageYears'}
                    and row['tokenId'] not in feature_rows, 'invalid_synthetic_feature_row')
                feature_rows[row['tokenId']] = row
            stages._require(set(feature_rows) == {t['tokenId'] for t in selected}, 'synthetic_membership_differs')
            requests = {t['tokenId']: {'status': 'prepared'} for t in selected}
            archive = None
        else:
            protocol = stages._json(stages._binding(inputs['frozenProtocol']))
            sessions, runtime, parent = _raw_config(config, selected, protocol)
            requests = {}
            with _held_verified(ARCHIVE) as archive_source, zipfile.ZipFile(archive_source) as archive:
                names = archive.namelist()
                stages._require(len(names) == len(set(names)), 'duplicate_archive_member')
                for key, session in sessions.items():
                    tokens = [t for t in selected if (t['folder'], t['session']) == key]
                    with archive.open(session['xmlMember']) as stream:
                        projected = project_selected_requests(stream, *key, tokens[0]['ageYears'], tokens)
                    requests.update({row['tokenId']: row for row in projected})
            archive = None
        try:
            for i, token in enumerate(selected):
                identity = {k: token[k] for k in ('childId', 'tokenId')}
                request = requests[token['tokenId']]
                failure = None
                if token.get('unmappablePhones'):
                    failure = 'selected_unsupported_phones'
                elif token.get('belowReaderMinimum'):
                    failure = 'selected_below_reader_minimum'
                elif request['status'] != 'prepared':
                    failure = request['failureCode']
                elif not synthetic and sessions[(token['folder'], token['session'])]['recording'] is None:
                    failure = 'selected_recording_unavailable'
                if failure is None:
                    try:
                        if synthetic:
                            row = feature_rows[token['tokenId']]
                            features = np.asarray(row['features'], dtype=np.float32)
                            age = row['ageYears']
                        else:
                            source = sessions[(token['folder'], token['session'])]['recording']
                            features, receipt = extract_recording(directory / f'token-{i:04d}', source, token,
                                request['prompt'], runtime, parent)
                            evidence.append(receipt)
                            age = token['ageYears']
                        prediction = fixed.predict(features, age)
                    except PredictionError as error:
                        if error.code not in {'invalid_features', 'invalid_completed_age'}:
                            raise
                        failure = 'shared_prediction_input_failure'
                    except ExtractionFailure:
                        failure = 'selected_extraction_failed'
                for arm in arms:
                    terminal = {'failureCode': failure} if failure is not None else prediction[arm]
                    arms[arm].append({**identity, 'status': 'failed', 'reason': terminal['failureCode']}
                        if 'failureCode' in terminal else {**identity, 'status': 'processed', 'probability': terminal['pError']})
        finally:
            if archive is not None:
                archive.close()
        stages._binding(execution_inputs_binding, private=True)
        fd = stages._directory(directory, private=True)
        try:
            envelope = {'schemaVersion': 1, 'declaration': declaration_pin,
                'predictionSource': profile['sourceBindings']['prediction'], 'inputBindings': inputs,
                'payload': {'children': profile['children'], 'selectedTokens': profile['selectedTokens'], 'arms': arms}}
            predictions = stages._write(fd, directory, 'predictions.json', envelope)
            receipt = stages._write(fd, directory, 'receipt.json', {'schemaVersion': 1,
                'executionSource': profile['sourceBindings']['execution'], 'predictionSource': profile['sourceBindings']['prediction'],
                'inputBindings': inputs, 'executionInputs': execution_inputs_binding,
                'productionBound': not synthetic, 'terminalTokens': len(selected), 'syntheticFixture': synthetic,
                'extractorCompletions': evidence, 'predictorProvenance': fixed.provenance, **stages.FLAGS})
            return {'predictions': predictions, 'executionInputs': execution_inputs_binding, 'receipt': receipt}
        finally:
            os.close(fd)
    return stages._phase(root, declaration_sha256, 'prediction-output', generate)
