"""Fixed twenty training recordings: selected ratings, bounded audio, waveform audit."""
import argparse
import json
from pathlib import Path

import numpy as np

from nisqa_ingest import discovery_v2, source_code_selection as selection
from nisqa_ingest.discovery import (binding, checked_review, check_ledger, fresh,
    guard, read, require, transport_snapshot, write)

HERE, ROOT = discovery_v2.HERE, discovery_v2.ROOT
BASE = HERE/'outputs/nisqa-20260927'
DISCOVERY = BASE/'discovery-v2'
SELECTION = BASE/'source-code-selection-v2'
PROTOCOL = ROOT/'docs/model/nisqa-selected-audio-target-pilot-v1.md'
SELECTION_SHA = 'b5a6b2011d45390070baac40718d2028f831051ab2dab2bac1b2fd5a606f1b0b'
METADATA_SHA = 'd8d476a5363d05277cedc9a454c3673f5d5e1e1f96e87bf5fbf5e3dc4c323222'
DIRECTORY_SHA = 'fce81a689c61f4d90e8169d1e2bfe2b5a094515371ab7f02f847b036f2c7d8fb'
SOURCE_NAMES = ('selected_pilot.py', 'test_selected_pilot.py', 'selected_targets.py',
    'test_selected_targets.py', 'waveform_audit.py', 'test_waveform_audit.py')
FLAGS = dict(trainingPerformed=False, modelInferencePerformed=False,
    evaluationAudioAcquired=False, clinicalUseEligible=False, learnerJudgmentsEnabled=False,
    personIdentityVerified=False, speakerIndependentEvaluationEligible=False,
    fullArchiveMd5Verified=False)


def audio_requests(selected, members):
    require(len(selected) == 20 and len({r['path'] for r in selected}) == 20
            and len({r['archiveMember'] for r in selected}) == 20, 'Fixed twenty identities required')
    names = {row['archiveMember'] for row in selected}
    entries = {row['filename']: row for row in members if row['filename'] in names}
    require(len(entries) == 20, 'Exact selected archive members required')
    result = []
    for row in selected:
        require(row['path'].startswith('NISQA_TRAIN_LIVE/deg/')
                and row['archiveMember'] == 'NISQA_Corpus/'+row['path'],
                'Selected training member join differs')
        entry = entries[row['archiveMember']]
        require(not entry.get('directory', False) and 0 < entry['file_size'] <= 128*1024*1024
                and 0 < entry['compress_size'] <= 64*1024*1024,
                'Selected member exceeds fixed limits')
        result.append(dict(identitySha256=row['identitySha256'], path=row['path'],
            member=row['archiveMember'], directoryEntry=entry))
    return result


def declaration():
    from nisqa_ingest.selected_targets import POLICY as TARGET_POLICY
    from nisqa_ingest.waveform_audit import POLICY as WAVEFORM_POLICY
    selected_pin = binding(SELECTION/'selection-freeze.json', SELECTION_SHA)
    selected_freeze = read(selected_pin)
    selected_plan, _ = selection.load(selected_freeze['plan']['path'], selected_freeze['plan']['sha256'])
    checked_review(selected_freeze['review']['path'], selected_freeze['plan']['sha256'])
    require(selected_freeze['complete'] is True, 'Completed selection required')
    selected = read(selected_freeze['selected'])
    require(selected == selection.select20(read(selected_freeze['eligible'])), 'Selection replay differs')
    metadata_pin = binding(DISCOVERY/'metadata-freeze.json', METADATA_SHA)
    directory_pin = binding(DISCOVERY/'directory-freeze.json', DIRECTORY_SHA)
    metadata, directory = read(metadata_pin), read(directory_pin)
    require(metadata['complete'] is True and directory['complete'] is True
            and metadata['plan'] == directory['plan'] == selected_plan['inputs']['discoveryPlan'],
            'Discovery lineage differs')
    original_plan, _ = discovery_v2.load(directory['plan']['path'], directory['plan']['sha256'])
    records = read(metadata['records'])
    combined = [r for r in records if r['filename'] == 'NISQA_Corpus/NISQA_corpus_file.csv']
    require(len(combined) == 1, 'Unique combined file table required')
    csv_pin = binding(combined[0]['acquired']['path'], combined[0]['acquired']['sha256'])
    evidence = ROOT/'work/nisqa-ingest-20260927'
    documents = dict(thesis=binding(evidence/'thesis-evidence/mittag-thesis.pdf',
        '5bb0593985c4ced3f592c029a31f3d3c5e9e1d2e45d9fddce0b6e0362ded4060'),
        scaleFindings=binding(evidence/'thesis-scale-findings.md'),
        scaleReview=binding(evidence/'thesis-scale-method-review.md'))
    return dict(study='nisqa-selected-audio-target-pilot-v1', protocol=binding(PROTOCOL),
        inputs=dict(selectionFreeze=selected_pin, selected=selected_freeze['selected'],
            eligible=selected_freeze['eligible'], metadataFreeze=metadata_pin,
            directoryFreeze=directory_pin, members=directory['members'], combinedCSV=csv_pin),
        documents=documents, sources={n: binding(Path(__file__).parent/n) for n in SOURCE_NAMES},
        runtime=dict(**original_plan['runtime'], numpy=np.__version__),
        archive=original_plan['archive'], selected=selected['selected'],
        requests=audio_requests(selected['selected'], read(directory['members'])),
        previousTransport=metadata['transport'], discoveryRoot=str(DISCOVERY),
        targetPolicy=TARGET_POLICY, waveformPolicy=WAVEFORM_POLICY,
        **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh research output required')
    plan = declaration()
    check_ledger(Path(plan['discoveryRoot']), plan['previousTransport'])
    output.mkdir(parents=True, mode=0o700)
    write(output/'plan.json', plan)
    return binding(output/'plan.json')


def load(path, sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs') and Path(path).name == 'plan.json',
            'Canonical pilot plan required')
    pin = binding(path, sha)
    plan = read(pin)
    require(plan == declaration(), 'Pilot source, input, protocol or runtime changed')
    guard(plan['inputs']); guard(plan['sources']); guard(plan['documents'])
    return plan, pin


def _start(path, sha, review, phase):
    plan, pin = load(path, sha)
    reviewed = checked_review(review, sha)
    root = Path(pin['path']).parent
    fresh(root, phase)
    write(root/(phase+'-started.json'), dict(plan=pin, review=reviewed))
    return plan, pin, reviewed, root


def targets(path, sha, review):
    from nisqa_ingest.selected_targets import parse_selected_targets
    plan, pin, reviewed, root = _start(path, sha, review, 'targets')
    try:
        with Path(plan['inputs']['combinedCSV']['path']).open(newline='', encoding='utf-8') as stream:
            value = parse_selected_targets(stream, [r['path'] for r in plan['selected']])
        write(root/'targets/selected-targets.json', value)
        load(path, sha)
        write(root/'targets-freeze.json', dict(complete=True, plan=pin, review=reviewed,
            targets=binding(root/'targets/selected-targets.json'),
            completeTargets=value['completeTargets'], numericTargetsAccessed=True,
            qualityTargetsInterpreted=True, **FLAGS))
        return binding(root/'targets-freeze.json')
    except Exception as error:
        write(root/'targets-failure.json', dict(plan=pin, errorType=type(error).__name__,
            samplePreserved=True, numericTargetsAccessMayHaveOccurred=True))
        raise


def transport(plan):
    from nisqa_ingest.http_transport_v2 import RemoteZipV2
    settings = plan['previousTransport']['settings']
    return RemoteZipV2(plan['archive']['url'], expected_size=plan['archive']['size'],
        output_directory=Path(plan['discoveryRoot'])/'transport',
        max_bytes=settings['maxBytes'], metadata_bytes=settings['metadataBytes'],
        allowed_hosts=('zenodo.org',))


def audio(path, sha, review):
    plan, pin, reviewed, root = _start(path, sha, review, 'audio')
    remote = None
    records = []
    try:
        check_ledger(Path(plan['discoveryRoot']), plan['previousTransport'])
        remote = transport(plan)
        remote.bootstrap()
        require(remote.members() == read(plan['inputs']['members']), 'Archive directory changed')
        allowed = [r['member'] for r in plan['requests']]
        for index, request in enumerate(plan['requests']):
            acquired = remote.acquire(request['member'], allowlist=allowed,
                output_name=f'selected-audio-{index:02d}.wav', metadata=False,
                max_compressed=64*1024*1024, max_uncompressed=128*1024*1024)
            require(acquired['member'] == request['directoryEntry'], 'Acquired member identity differs')
            record = dict(path=request['path'], identitySha256=request['identitySha256'], acquired=acquired)
            write(root/'audio'/f'record-{index:02d}.json', record)
            records.append(record)
        write(root/'audio/records.json', records)
        load(path, sha)
        write(root/'audio-freeze.json', dict(complete=True, plan=pin, review=reviewed,
            records=binding(root/'audio/records.json'), selectedCount=20,
            waveformAcquired=True, transport=transport_snapshot(remote, root/'audio'), **FLAGS))
        return binding(root/'audio-freeze.json')
    except Exception as error:
        value = dict(plan=pin, errorType=type(error).__name__, completedCount=len(records),
                     samplePreserved=True)
        if remote is not None:
            value['transport'] = transport_snapshot(remote, root/'audio')
        write(root/'audio-failure.json', value)
        raise
    finally:
        if remote is not None:
            remote.close()


def waveforms(path, sha, review, audio_sha):
    from nisqa_ingest.waveform_audit import audit_wav
    plan, pin, reviewed, root = _start(path, sha, review, 'waveforms')
    try:
        audio_pin = binding(root/'audio-freeze.json', audio_sha)
        frozen = read(audio_pin)
        require(frozen['complete'] is True and frozen['plan'] == pin, 'Completed matching audio required')
        check_ledger(Path(plan['discoveryRoot']), frozen['transport'])
        records = read(frozen['records'])
        require(len(records) == 20 and [(r['path'], r['identitySha256']) for r in records]
                == [(r['path'], r['identitySha256']) for r in plan['requests']],
                'Fixed selected waveform joins differ')
        results = []
        for index, record in enumerate(records):
            acquired = record['acquired']
            binding(acquired['path'], acquired['sha256'])
            require(acquired['member'] == plan['requests'][index]['directoryEntry'], 'Waveform member differs')
            try:
                result = dict(path=record['path'], identitySha256=record['identitySha256'],
                              success=True, audit=audit_wav(acquired['path']))
            except ValueError as error:
                result = dict(path=record['path'], identitySha256=record['identitySha256'],
                              success=False, errorType=type(error).__name__, reason=str(error))
            binding(acquired['path'], acquired['sha256'])
            write(root/'waveforms'/f'audit-{index:02d}.json', result)
            results.append(result)
        write(root/'waveforms/audits.json', results)
        load(path, sha)
        write(root/'waveforms-freeze.json', dict(complete=True, plan=pin, review=reviewed,
            audioFreeze=audio_pin, audits=binding(root/'waveforms/audits.json'), selectedCount=20,
            decodedCount=sum(r['success'] for r in results),
            allSelectedDecoded=all(r['success'] for r in results), **FLAGS))
        return binding(root/'waveforms-freeze.json')
    except Exception as error:
        write(root/'waveforms-failure.json', dict(plan=pin, errorType=type(error).__name__, samplePreserved=True))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'targets', 'audio', 'waveforms'))
    for name in ('output', 'plan', 'review'):
        parser.add_argument('--'+name, type=Path)
    for name in ('plan-sha256', 'audio-sha256'):
        parser.add_argument('--'+name)
    args = parser.parse_args()
    if args.command == 'declare':
        result = declare(args.output)
    elif args.command == 'targets':
        result = targets(args.plan, args.plan_sha256, args.review)
    elif args.command == 'audio':
        result = audio(args.plan, args.plan_sha256, args.review)
    else:
        result = waveforms(args.plan, args.plan_sha256, args.review, args.audio_sha256)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
