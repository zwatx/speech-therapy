"""Explicit fixed-selection recovery from an immutable eight-record failure."""
import argparse
import json
from pathlib import Path
import zlib

from nisqa_ingest import selected_pilot as original
from nisqa_ingest.discovery import (binding, read, write, require, checked_review,
                                    check_ledger, fresh, transport_snapshot)

HERE, ROOT = original.HERE, original.ROOT
OLD = original.BASE/'selected-audio-target-pilot-v1'
OLD_SHA = '1095eab4bda306c90015d3e8253779bd427f5cfd8cf371721ba4f9a6e18d20a3'
FAILURE_SHA = '51f80e796a6994b79b5e1d206c5f197524b5ca9501da6c1c9fcffff4ebc59ae1'
TARGET_SHA = 'dab74ab2508edf7461ecf0166d094414bfa4b711f7b97b1da4f1296e1c611e1a'
PROTOCOL = ROOT/'docs/model/nisqa-selected-audio-recovery-v1.md'
METHOD = ROOT/'work/nisqa-ingest-20260927/selected-pilot-recovery-method.md'
SOURCE_NAMES = ('selected_recovery.py', 'test_selected_recovery.py',
                'frozen_directory_transport.py', 'test_frozen_directory_transport.py')
FLAGS = dict(**original.FLAGS, readSpeechOnly=True, speakerAgeCoverageVerified=False, nonspeechTruthAvailable=False,
             gpuUsed=False)


def checked_record(record, request, archive, validator):
    require((record['path'], record['identitySha256']) ==
            (request['path'], request['identitySha256']), 'Frozen record join differs')
    acquired = record['acquired']; member = request['directoryEntry']
    require(acquired['member'] == member and acquired['size'] == member['file_size'],
            'Frozen member identity differs')
    require(acquired['archive'] == dict(url=archive['url'], size=archive['size'],
            validator=validator, fullArchiveMd5Verified=False), 'Frozen archive identity differs')
    binding(acquired['path'], acquired['sha256'])
    crc, size = 0, 0
    with Path(acquired['path']).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            crc = zlib.crc32(chunk, crc); size += len(chunk)
    require(size == member['file_size'] and crc & 0xffffffff == member['CRC'],
            'Frozen waveform size or CRC differs')
    return record


def declaration():
    from nisqa_ingest.frozen_directory_transport import POLICY
    old, old_pin = original.load(OLD/'plan.json', OLD_SHA)
    failure_pin = binding(OLD/'audio-failure.json', FAILURE_SHA)
    failure = read(failure_pin)
    require(failure['plan'] == old_pin and failure['completedCount'] == 8
            and failure['samplePreserved'] is True, 'Exact original terminal failure required')
    previous = failure['transport']
    state = read(previous['state']); binding(previous['journal']['path'], previous['journal']['sha256'])
    require(previous['bytesRead'] == previous['budgetSpent'] == 20131489
            and previous['metadataRead'] == previous['metadataBudgetSpent'] == 15436716
            and all(state[key] == 0 for key in ('reserved', 'reservedMetadata', 'uncertainBytes', 'uncertainMetadata')),
            'Original failure budget anchor differs')
    require(state['bytesRead'] == previous['bytesRead'] and state['metadataRead'] == previous['metadataRead']
            and state['settings'] == previous['settings'] and state['validator'] == previous['validator'],
            'Failure snapshot state differs')
    targets_pin = binding(OLD/'targets-freeze.json', TARGET_SHA)
    targets = read(targets_pin)
    require(targets['plan'] == old_pin and targets['complete'] is True
            and targets['completeTargets'] is True, 'Completed original targets required')
    # Pin the existing target artifact without decoding or previewing values.
    binding(targets['targets']['path'], targets['targets']['sha256'])
    partial_pin = binding(Path(old['discoveryRoot'])/'transport/selected-audio-08.wav.partial')
    require(Path(partial_pin['path']).stat().st_size == 917504, 'Original failed partial size differs')
    members = read(old['inputs']['members'])
    require(old['requests'] == original.audio_requests(old['selected'], members),
            'Original directory/request identities differ')
    records = []
    pins = {}
    for index, request in enumerate(old['requests'][:8]):
        pin = binding(OLD/'audio'/f'record-{index:02d}.json'); pins[str(index)] = pin
        record = checked_record(read(pin), request, old['archive'], previous['validator'])
        require(Path(record['acquired']['path']) == Path(old['discoveryRoot'])/'transport'/f'selected-audio-{index:02d}.wav',
                'Original output path differs')
        records.append(record)
    for index in range(8, 20):
        require(not (OLD/'audio'/f'record-{index:02d}.json').exists(), 'Original completed prefix differs')
    return dict(study='nisqa-selected-audio-recovery-v1', protocol=binding(PROTOCOL),
        methodReview=binding(METHOD), sources={n: binding(Path(__file__).parent/n) for n in SOURCE_NAMES},
        originalPlan=old_pin, failure=failure_pin, targetsFreeze=targets_pin, failedPartial=partial_pin,
        targets=targets['targets'], directoryFreeze=old['inputs']['directoryFreeze'],
        members=old['inputs']['members'], prefixRecordPins=pins, prefixRecords=records,
        selected=old['selected'], requests=old['requests'], archive=old['archive'],
        runtime=old['runtime'], discoveryRoot=old['discoveryRoot'], previousTransport=previous,
        transportPolicy=POLICY, outputNames=[f'resume-audio-{i:02d}.wav' for i in range(8,20)],
        **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh research output required')
    plan = declaration()
    check_ledger(Path(plan['discoveryRoot']), plan['previousTransport'])
    checked_output_names(plan)
    output.mkdir(parents=True, mode=0o700)
    write(output/'plan.json', plan)
    return binding(output/'plan.json')


def load(path, sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs') and Path(path).name == 'plan.json',
            'Canonical recovery plan required')
    pin = binding(path, sha); plan = read(pin)
    require(plan == declaration(), 'Recovery source, input, protocol or runtime changed')
    # Mutable live ledger is deliberately checked only at declaration/run start.
    return plan, pin


def transport(plan):
    from nisqa_ingest.frozen_directory_transport import FrozenDirectoryZip
    settings = plan['previousTransport']['settings']
    return FrozenDirectoryZip(plan['archive']['url'], expected_size=plan['archive']['size'],
        output_directory=Path(plan['discoveryRoot'])/'transport',
        frozen_members=read(plan['members']), selected_names=[r['member'] for r in plan['requests']],
        max_bytes=settings['maxBytes'], metadata_bytes=settings['metadataBytes'], allowed_hosts=('zenodo.org',))


def checked_extension(plan):
    prior = plan['previousTransport']
    binding(plan['failedPartial']['path'], plan['failedPartial']['sha256'])
    journal = Path(plan['discoveryRoot'])/'transport/request-journal.jsonl'
    require(journal.read_bytes().startswith(Path(prior['journal']['path']).read_bytes()),
            'Inherited journal prefix differs')
    state = json.loads((Path(plan['discoveryRoot'])/'transport/transport-state.json').read_text())
    require(prior['bytesRead'] <= state['bytesRead'] <= prior['settings']['maxBytes']
            and prior['metadataRead'] <= state['metadataRead'] <= prior['settings']['metadataBytes'],
            'Inherited spending changed')
    require(state['settings'] == prior['settings'] and state['validator'] == prior['validator']
            and all(state[key] == 0 for key in ('reserved','reservedMetadata','uncertainBytes','uncertainMetadata')),
            'Completed transport state differs')


def checked_output_names(plan):
    folder = Path(plan['discoveryRoot'])/'transport'
    require(all(not (folder/name).exists() and not (folder/(name+'.partial')).exists()
                for name in plan['outputNames']), 'Preserve existing recovery outputs; no overwrite')


def audit(plan, pin, reviewed, root, acquisition_pin):
    from nisqa_ingest.waveform_audit import audit_wav
    fresh(root, 'audit')
    write(root/'audit-started.json', dict(plan=pin, review=reviewed, acquisitionFreeze=acquisition_pin))
    frozen = read(acquisition_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin, 'Matching acquisition freeze required')
    records = read(frozen['records'])
    require(len(records) == 20, 'Exactly twenty acquired records required')
    # This authorized execution reads existing selected data only for exact joins/completeness.
    targets = read(plan['targets'])
    require(targets['trainingOnly'] is True and targets['selectedPaths'] == [r['path'] for r in plan['requests']]
            and len(targets['rows']) == 20
            and [r['path'] for r in targets['rows']] == targets['selectedPaths'], 'Frozen target joins differ')
    complete = targets['completeTargets'] is True and all(
        r['db'] == 'NISQA_TRAIN_LIVE' and set(r['quality']) == {'mos','noi','dis','col','loud'}
        and not r['declaredMissing'] and all(v is not None for v in r['quality'].values()) for r in targets['rows'])
    results = []
    for index, (record, request) in enumerate(zip(records, plan['requests'])):
        checked_record(record, request, plan['archive'], frozen['transport']['validator'])
        try:
            result = dict(path=record['path'], identitySha256=record['identitySha256'], success=True,
                          audit=audit_wav(record['acquired']['path']))
        except ValueError:
            result = dict(path=record['path'], identitySha256=record['identitySha256'], success=False,
                          errorType='ValueError', reason='Selected waveform audit failed')
        binding(record['acquired']['path'], record['acquired']['sha256'])
        write(root/'audit'/f'audit-{index:02d}.json', result); results.append(result)
    write(root/'audit/audits.json', results)
    load(pin['path'], pin['sha256'])
    checked_extension(plan)
    decoded = sum(r['success'] for r in results)
    write(root/'audit-freeze.json', dict(complete=True, plan=pin, review=reviewed,
        acquisitionFreeze=acquisition_pin, targetsFreeze=plan['targetsFreeze'],
        audits=binding(root/'audit/audits.json'), selectedCount=20, decodedCount=decoded,
        allSelectedDecoded=decoded == 20, completeTargets=complete, ingestionReady=decoded == 20 and complete,
        **FLAGS))
    return binding(root/'audit-freeze.json')


def run(path, sha, review):
    plan, pin = load(path, sha); reviewed = checked_review(review, sha)
    root = Path(pin['path']).parent
    fresh(root, 'acquisition')
    write(root/'acquisition-started.json', dict(plan=pin, review=reviewed))
    remote, records = None, list(plan['prefixRecords'])
    try:
        check_ledger(Path(plan['discoveryRoot']), plan['previousTransport'])
        checked_output_names(plan)
        remote = transport(plan); remote.bootstrap()
        require(remote.members() == read(plan['members']), 'Frozen archive directory differs')
        allowed = [r['member'] for r in plan['requests']]
        for index, record in enumerate(records):
            checked_record(record, plan['requests'][index], plan['archive'], plan['previousTransport']['validator'])
            write(root/'acquisition'/f'record-{index:02d}.json', record)
        for index, request in enumerate(plan['requests'][8:], 8):
            acquired = remote.acquire(request['member'], allowlist=allowed,
                output_name=plan['outputNames'][index-8], metadata=False,
                max_compressed=64*1024*1024, max_uncompressed=128*1024*1024)
            record = dict(path=request['path'], identitySha256=request['identitySha256'], acquired=acquired)
            checked_record(record, request, plan['archive'], plan['previousTransport']['validator'])
            write(root/'acquisition'/f'record-{index:02d}.json', record); records.append(record)
        write(root/'acquisition/records.json', records)
        load(path, sha)
        checked_extension(plan)
        write(root/'acquisition-freeze.json', dict(complete=True, plan=pin, review=reviewed,
            records=binding(root/'acquisition/records.json'), selectedCount=20, retainedCount=8, acquiredCount=12,
            transport=transport_snapshot(remote, root/'acquisition'), **FLAGS))
    except Exception as error:
        failure = dict(plan=pin, errorType=type(error).__name__, completedCount=len(records), samplePreserved=True)
        if remote is not None: failure['transport'] = transport_snapshot(remote, root/'acquisition')
        write(root/'acquisition-failure.json', failure)
        raise
    finally:
        if remote is not None: remote.close()
    try:
        return audit(plan, pin, reviewed, root, binding(root/'acquisition-freeze.json'))
    except Exception as error:
        write(root/'audit-failure.json', dict(plan=pin, errorType=type(error).__name__, samplePreserved=True))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run'))
    for name in ('output','plan','review'): parser.add_argument('--'+name, type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    result = declare(args.output) if args.command == 'declare' else run(args.plan,args.plan_sha256,args.review)
    print(json.dumps(result))


if __name__ == '__main__': main()
