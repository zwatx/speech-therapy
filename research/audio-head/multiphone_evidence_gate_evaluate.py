"""Evaluate the fixed research evidence policy; no fitting or new acoustic inference."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import multiphone_evidence_gate as gate

raw = gate.raw
BASE = raw.HERE / 'outputs/multiphone-20260926'
FEATURES = BASE / 'ctc-local-full/features/features.json'
FEATURES_SHA = 'd6dbcb1d4d36153af2e13577fb4e39d4c23e6cabcb511f69990b968dbde6279a'


def bound_clip(clip, entry, cache, config_sha):
    """Read only the declared author-training waveform and its bound posteriors."""
    raw.require(entry['clipId'] == clip['id'] and entry['audioSha256'] == clip['audioSha256']
                and entry['sampleCount'] == clip['sampleCount'] and entry['configSha256'] == config_sha
                and entry['vocabularySize'] == 392, 'CTC entry binding differs')
    path = (cache / entry['path']).resolve()
    raw.require(path.is_relative_to(cache.resolve()), 'CTC path escapes cache')
    pins = {'audio': raw.binding(clip['audioPath'], clip['audioSha256']),
            'posterior': raw.binding(path, entry['sha256'])}
    samples = raw.read_rating_pcm(Path(clip['audioPath']), clip['audioSha256']).numpy()
    raw.require(len(samples) == clip['sampleCount'], 'Waveform sample count differs')
    logp = np.fromfile(path, dtype='<f4').reshape(-1, 392)
    raw.require(len(logp) == entry['frames'], 'CTC entry frame count differs')
    decision = gate.assess(samples, logp)
    raw.guard(pins)
    return decision, pins


def counts(rows):
    return {'clips': len({r['clipId'] for r in rows}), 'speakers': len({r['speakerId'] for r in rows}),
            'positions': len(rows), 'rating0Votes': sum(r['raterCounts'][0] for r in rows),
            'below2Votes': sum(sum(r['raterCounts'][:2]) for r in rows),
            'rating0Positions': sum(r['raterCounts'][0] > 0 for r in rows),
            'below2Positions': sum(sum(r['raterCounts'][:2]) > 0 for r in rows)}


def summarize(rows, decisions):
    return {state: counts([r for r in rows if state == 'total' or
                           decisions[r['clipId']]['ratingAvailable'] == (state == 'retained')])
            for state in ('total', 'retained', 'withheld')}


def evaluate(output):
    raw.require(not output.exists() and output.resolve().is_relative_to((raw.HERE/'outputs').resolve()),
                'Choose fresh ignored output directory')
    features, fpin = raw.read_bound_json(FEATURES, FEATURES_SHA)
    manifest, mpin = raw.read_bound_json(features['manifestPath'], features['manifestSha256'])
    cohort, cpin = raw.read_bound_json(manifest['cohortPath'], manifest['cohortSha256'])
    index, ipin = raw.read_bound_json(features['ctcIndexPath'], features['ctcIndexSha256'])
    cache = Path(ipin['path']).parent
    config, cfgpin = raw.read_bound_json(cache/'config.json', index['configSha256'])
    raw.require(cohort['authorPartition'] == manifest['authorPartition'] == 'train'
                and features['complete'] and features['fullCohortCoverage'] and index['complete']
                and config['manifestSha256'] == mpin['sha256'], 'Expected complete author-training cache')
    raw.local.validate_manifest_rows(manifest, cohort)
    rows = [r for r in cohort['rows'] if r['trainingEligible']]
    raw.require(len(manifest['clips']) == 2495 and len(rows) == 14837
                and len({r['targetPhone'] for r in rows}) == 23
                and set(index['entries']) == {c['id'] for c in manifest['clips']}, 'Full cohort coverage differs')
    pins = {'features': fpin, 'manifest': mpin, 'cohort': cpin, 'index': ipin, 'config': cfgpin,
            'evaluationSource': raw.binding(__file__), 'gateSource': raw.binding(gate.__file__),
            'localSource': raw.binding(raw.local.__file__), 'rawSource': raw.binding(raw.__file__),
            'pcmSource': raw.binding(raw.HERE/'speechocean_r_probe.py'),
            'policyProtocol': raw.binding(raw.HERE.parent.parent/'docs/model/multiphone-evidence-gate-protocol.md'),
            'mapping': raw.binding(raw.local.RECIPE, manifest['recipeSha256'])}
    decisions, bindings = {}, {}
    for clip in manifest['clips']:
        decision, binding = bound_clip(clip, index['entries'][clip['id']], cache, cfgpin['sha256'])
        decisions[clip['id']], bindings[clip['id']] = decision, binding
    tables = {}
    for population, selected in [('allAge', rows), ('child6to12', [r for r in rows if 6 <= r['age'] <= 12])]:
        tables[population] = {'overall': summarize(selected, decisions), 'phones': {
            phone: summarize([r for r in selected if r['targetPhone'] == phone], decisions)
            for phone in sorted({r['targetPhone'] for r in rows})}}
    output.mkdir(parents=True, mode=0o700)
    examples = {}
    for label, path in [('zero', BASE/'nonspeech-boundary-v1/results/zero/report.json'),
                        ('gaussian', BASE/'nonspeech-boundary-v1/results/gaussian/report.json'),
                        ('sine440', BASE/'nonspeech-boundary-v1/results/sine440/report.json'),
                        ('real', BASE/'raw-research-verification-v1/0-unweighted-all-age/report.json')]:
        original, pin = raw.read_bound_json(path)
        result = gate.filter_report(path, pin['sha256'], output/(label+'-gated.json'))
        filtered = json.loads(Path(result['report']).read_text())
        expected = (original['targets'] if label == 'real' else None)
        if expected is not None:
            raw.require(result['decision']['ratingAvailable'] and
                        [r['subjectiveCorpusRatingProbabilities'] for r in filtered['targets']] ==
                        [r['subjectiveCorpusRatingProbabilities'] for r in original['targets']], 'Real probability parity failed')
        else:
            raw.require(not result['decision']['ratingAvailable'] and
                        all(r['subjectiveCorpusRatingProbabilities'] is None for r in filtered['targets']),
                        'Abstained report exposes probabilities')
        examples[label] = result
    raw.guard(pins)
    result = {'complete': True, 'researchOnly': True, 'policy': gate.POLICY, 'inputBindings': pins,
              'clipBindings': bindings, 'decisions': decisions, 'retention': tables, 'rawReportChecks': examples,
              'authorTestRead': False, 'speechPresenceValidated': False, 'promptMatchValidated': False,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
              'meaning': 'Exploratory corpus retention and known-negative checks; not validated VAD or clinical false rejection'}
    raw.write_json(output/'report.json', result)
    return {'report': str(output/'report.json'), 'sha256': raw.digest(output/'report.json'),
            'retention': {k:v['overall'] for k,v in tables.items()}, 'rawChecks': examples}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.output), indent=2))
