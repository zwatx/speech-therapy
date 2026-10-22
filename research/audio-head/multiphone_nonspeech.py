"""Three fixed non-speech observations through the unchanged research adapter."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import wave

import numpy as np
import torch

import multiphone_research_audio as raw

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
PROTOCOL = HERE/'../../docs/model/multiphone-nonspeech-protocol.md'
FINAL_LEDGER = BASE/'phonetic-final-queue-v1.json'
FINAL_LEDGER_SHA = '8b9a2c51e0e9b47c7ceccd904a7257b1901b9c7ea70f0ae9d048ee23354aa280'
SNAPSHOT = HERE/'outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'
CONTRACT_SHA = 'c077e68e37fa68da36a44194094e5c07c40e1866148834c68b6fbd24a5da9782'
VARIANTS = ('unweighted-all-age', 'unweighted-child-only', 'weighted-all-age', 'weighted-child-only')
CONDITIONS = ('zero', 'gaussian', 'sine440')
PROMPT = {'schemaVersion': 1, 'language': 'en', 'transcript': 'BALL',
          'words': [{'text': 'BALL', 'phones': ['B', 'AO1', 'L']}],
          'targets': [{'id': 'ball-b', 'wordIndex': 0, 'phoneIndex': 0, 'targetPhone': 'B'}]}
require = raw.require


def now():
    return datetime.now(timezone.utc).isoformat()


def signal_bytes(condition):
    require(condition in CONDITIONS, 'Unknown fixed condition')
    if condition == 'zero':
        x = np.zeros(32000, dtype=np.float64)
    elif condition == 'gaussian':
        x = np.random.Generator(np.random.PCG64(20260926)).normal(size=32000)
        x *= .1 / np.sqrt(np.mean(x*x))
    else:
        x = np.sqrt(2)*.1*np.sin(2*np.pi*440*np.arange(32000, dtype=np.float64)/16000)
    integer = np.rint(x*32768)
    require(np.isfinite(integer).all() and integer.min() >= -32768 and integer.max() <= 32767,
            'No clipping is permitted in fixed signal generation')
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
        stream.writeframes(integer.astype('<i2').tobytes())
    return buffer.getvalue()


def declare(output):
    output = Path(output).absolute()
    require(not output.exists() and output.resolve().is_relative_to((HERE/'outputs').resolve()), 'Fresh ignored output required')
    ledger, ledger_pin = raw.read_bound_json(FINAL_LEDGER, FINAL_LEDGER_SHA)
    require(ledger['complete'] is True and tuple(j['variant'] for j in ledger['jobs']) == VARIANTS,
            'Expected four completed final exports in fixed order')
    contract, _, _, _, pins = raw.load_contract(raw.CONTRACT, CONTRACT_SHA, SNAPSHOT)
    pins.update({'protocol': raw.binding(PROTOCOL), 'diagnosticSource': raw.binding(__file__), 'finalLedger': ledger_pin})
    heads = []
    for job in ledger['jobs']:
        require(job['state'] == 'complete' and job['replay']['verifiedExact'] is True, 'Final head not replayed')
        bundle = Path(job['output'])
        manifest, manifest_pin = raw.read_bound_json(bundle/'manifest.json', job['manifestSha256'])
        pins['head/'+job['variant']+'/manifest'] = manifest_pin
        for filename, expected in manifest['filesSha256'].items():
            require(filename in raw.inference.FILES, 'Unexpected bundle file')
            pins['head/'+job['variant']+'/'+filename] = raw.binding(bundle/filename, expected)
        heads.append({'variant': job['variant'], 'bundle': str(bundle), 'manifestSha256': job['manifestSha256']})
    node = shutil.which('node'); require(node is not None, 'Node runtime missing')
    pins['nodeExecutable'] = raw.binding(node)
    output.mkdir(parents=True, mode=0o700)
    raw.write_json(output/'prompt.json', PROMPT)
    pins['prompt'] = raw.binding(output/'prompt.json')
    signals = []
    for condition in CONDITIONS:
        path = output/(condition+'.wav'); path.write_bytes(signal_bytes(condition)); path.chmod(0o600)
        pins['signal/'+condition] = raw.binding(path)
        samples = raw.read_rating_pcm(path, pins['signal/'+condition]['sha256'])
        signals.append({'condition': condition, **pins['signal/'+condition], 'recordingMeasurements': raw.recording_measurements(samples)})
    raw.guard(pins)
    plan = {'schemaVersion': 1, 'declaredAt': now(), 'inferencePerformed': False, 'trainingPerformed': False,
            'device': 'cpu', 'threads': 2, 'signals': signals, 'prompt': pins['prompt'], 'heads': heads,
            'snapshot': str(SNAPSHOT), 'contractSha256': CONTRACT_SHA, 'node': node, 'inputFiles': pins,
            'repeats': 1, 'semanticAbstentionImplemented': False, 'protocolPath': str(PROTOCOL.absolute()),
            'humanLabelsAvailable': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    raw.write_json(output/'plan.json', plan)
    return {'plan': str(output/'plan.json'), 'sha256': raw.digest(output/'plan.json')}


def checked_plan(path, expected_sha):
    plan, captured = raw.read_bound_json(path, expected_sha)
    require(plan['schemaVersion'] == 1 and [s['condition'] for s in plan['signals']] == list(CONDITIONS)
            and [h['variant'] for h in plan['heads']] == list(VARIANTS)
            and plan['device'] == 'cpu' and plan['threads'] == 2 and plan['repeats'] == 1
            and plan['inferencePerformed'] is False and plan['humanLabelsAvailable'] is False,
            'Fixed diagnostic declaration differs')
    pins = {**plan['inputFiles'], 'declaration': captured}
    raw.guard(pins)
    require(json.loads(Path(plan['prompt']['path']).read_text()) == PROMPT, 'Canonical prompt differs')
    for signal in plan['signals']:
        require(Path(signal['path']).read_bytes() == signal_bytes(signal['condition'])
                and raw.digest(signal['path']) == signal['sha256'], 'Declared signal bytes differ')
    require(pins['diagnosticSource']['sha256'] == raw.digest(__file__)
            and pins['protocol']['sha256'] == raw.digest(PROTOCOL), 'Diagnostic source/protocol differs')
    return plan, pins


def run(plan_path, expected_sha):
    started_at, start = now(), time.perf_counter()
    plan, pins = checked_plan(plan_path, expected_sha)
    result_dir = Path(plan_path).parent/'results'
    require(not result_dir.exists(), 'Fresh diagnostic run required; no repeats or implicit resume')
    result_dir.mkdir(mode=0o700)
    torch.set_num_threads(2)
    outcomes, artifacts = [], {}
    for signal in plan['signals']:
        raw.guard(pins)
        condition = signal['condition']; extracted = result_dir/condition
        first = plan['heads'][0]
        args = SimpleNamespace(contract=raw.CONTRACT, contract_sha256=plan['contractSha256'],
            wav=Path(signal['path']), wav_sha256=signal['sha256'], prompt=Path(plan['prompt']['path']),
            prompt_sha256=plan['prompt']['sha256'], bundle=Path(first['bundle']),
            manifest_sha256=first['manifestSha256'], phonetic_snapshot=Path(plan['snapshot']),
            output=extracted, node=plan['node'])
        outcome = {'condition': condition, 'audioSha256': signal['sha256'],
                   'semanticAbstentionImplemented': False, 'recordingMeasurements': signal['recordingMeasurements']}
        try:
            raw.run(args)
        except Exception as error:
            # A failed extraction is an observation, never a semantic speech rejection.
            raw.guard(pins)
            outcome.update(pipelineAccepted=False, error=f'{type(error).__name__}: {error}',
                           errorMeaning='Runtime/contract failure; not a validated non-speech rejection')
            partial = extracted.with_name(extracted.name+'.partial')
            for path in sorted(partial.glob('*')) if partial.exists() else []:
                if path.is_file(): artifacts[str(path)] = raw.digest(path)
        else:
            report, report_pin = raw.read_bound_json(extracted/'report.json')
            artifacts[report_pin['path']] = report_pin['sha256']
            require(report['complete'] is True and report['canonicalPrompt']['transcript'] == 'BALL'
                    and report['canonicalPrompt']['canonicalPhones'] == ['B','AO1','L']
                    and len(report['targets']) == 1
                    and all(report['targets'][0][k] == v for k,v in PROMPT['targets'][0].items())
                    and report['targets'][0]['modelTargetId'] == 0
                    and report['headManifestSha256'] == first['manifestSha256']
                    and report['contractSha256'] == plan['contractSha256']
                    and report['inputBindings']['audio'] == raw.binding(signal['path'],signal['sha256'])
                    and report['inputBindings']['prompt'] == plan['prompt']
                    and report['runtime']['device'] == 'cpu' and report['runtime']['threads'] == 2
                    and report['ctcRuntime']['fetchAttempts'] == 0,
                    'Adapter target identity differs')
            raw.guard(report['inputBindings'])
            for name,pin in report['inputBindings'].items():
                pins['extraction/'+condition+'/'+name] = pin
            for name, sha in report['filesSha256'].items():
                require(raw.digest(extracted/name) == sha, 'Adapter artifact differs')
                artifacts[str(extracted/name)] = sha
            features = np.load(extracted/'features.npy', allow_pickle=False)
            require(features.dtype == np.float32 and features.shape == (1,1037) and np.isfinite(features).all(), 'Feature matrix differs')
            probabilities = {}
            for head_spec in plan['heads']:
                head = raw.inference.load_head(Path(head_spec['bundle']), head_spec['manifestSha256'])
                require(head.feature_source_binding_sha256 == report['featureSourceBindingSha256']
                        and list(head.feature_columns) == report['featureMatrix']['columns'], 'Head feature semantics differ')
                probabilities[head_spec['variant']] = head.predict(features, np.array([0], dtype=np.int64))[0].tolist()
            require(probabilities[first['variant']] == report['targets'][0]['subjectiveCorpusRatingProbabilities'],
                    'Feature-level first head differs from adapter probabilities')
            require(report['recordingMeasurements'] == signal['recordingMeasurements'], 'Recording measurements changed')
            outcome.update(pipelineAccepted=True, extractionReport=report_pin,
                recordingMeasurements=report['recordingMeasurements'], target=report['targets'][0],
                canonicalPathDiagnostics=report['canonicalPathDiagnostics'],
                featureMatrix=report['featureMatrix'], featureSha256=report['filesSha256']['features.npy'],
                finiteFeatures=True, probabilitiesByVariant=probabilities,
                firstHeadReplayExact=True, ctcFetchAttempts=report['ctcRuntime']['fetchAttempts'])
        outcomes.append(outcome)
    raw.guard(pins)
    require(all(raw.digest(path) == sha for path,sha in artifacts.items()), 'Derived diagnostic artifact changed')
    report = {'schemaVersion':1,'complete':True,'startedAt':started_at,'finishedAt':now(),
              'elapsedSeconds':time.perf_counter()-start,'planPath':str(Path(plan_path).absolute()),
              'planSha256':expected_sha,'inputFiles':pins,'artifactSha256':artifacts,'outcomes':outcomes,
              'device':'cpu','threads':2,'trainingPerformed':False,'modelSelectionPerformed':False,
              'humanLabelsAvailable':False,'accuracyMeasured':False,'clinicalUseEligible':False,
              'learnerFeedbackEligible':False,'semanticAbstentionImplemented':False,
              'interpretation':'Three fixed non-speech signals with an intended canonical prompt. Outputs are corpus-vote probabilities, not evidence of speech, pronunciation correctness or a rejection policy. Runtime failures are not semantic abstentions.'}
    raw.write_json(result_dir/'report.json', report)
    return {'report':str(result_dir/'report.json'),'sha256':raw.digest(result_dir/'report.json')}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    declare_parser=sub.add_parser('declare'); declare_parser.add_argument('--output',type=Path,required=True)
    run_parser=sub.add_parser('run'); run_parser.add_argument('--plan',type=Path,required=True); run_parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    print(json.dumps(declare(args.output) if args.command=='declare' else run(args.plan,args.sha256),indent=2))
