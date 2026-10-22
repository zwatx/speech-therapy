"""Versioned HTTP correction; reuse frozen v1 routing and artifact utilities."""
import argparse
import json
from pathlib import Path

from nisqa_ingest import discovery as original
from nisqa_ingest.discovery import (binding, read, guard, write, require, fresh,
    checked_review, metadata_requests, metadata_identity, transport_snapshot, check_ledger)

HERE, ROOT = original.HERE, original.ROOT
PROTOCOL = ROOT / 'docs/model/nisqa-discovery-transport-v2.md'
FLAGS = original.FLAGS
MEMBER_LIMIT, LIMIT, ARCHIVE = original.MEMBER_LIMIT, original.LIMIT, original.ARCHIVE
PREVIOUS = HERE / 'outputs/nisqa-20260927/discovery-v1'
V2_SOURCE_NAMES = ('discovery_v2.py', 'test_discovery_v2.py',
                   'http_transport_v2.py', 'test_http_transport_v2.py')


def declaration():
    value = original.declaration()
    previous = {name: binding(PREVIOUS/name) for name in
        ('plan.json', 'directory-started.json', 'directory-failure.json',
         'transport/transport-state.json', 'transport/request-journal.jsonl')}
    require(previous['plan.json']['sha256'] ==
        '9736744660f0ea5dcd6a54ee9699eb1d1a9d65cc38cef06f5b883ab7c2cd6d5a',
        'Original plan changed')
    prior = read(previous['transport/transport-state.json'])
    require(all(prior.get(k) == 0 for k in ('bytesRead', 'metadataRead', 'uncertainBytes',
        'uncertainMetadata', 'reserved', 'reservedMetadata')), 'Prior body spending cannot be reset')
    journal = [json.loads(line) for line in Path(previous['transport/request-journal.jsonl']['path']).read_text().splitlines()]
    require(len(journal) == 2 and journal[0]['event'] == 'HEAD'
        and journal[0]['outcome'] == 'verified' and journal[1]['event'] == 'GET'
        and journal[1]['status'] == 206 and journal[1]['outcome'] == 'failed'
        and all(r.get('bytes') == 0 and r.get('uncertainBytes', 0) == 0 for r in journal),
        'Prior zero-body failure evidence differs')
    require(read(previous['directory-failure.json']) == {'error':
        'RemoteZipError: Archive validators changed during range retrieval'}, 'Unexpected prior failure')
    value['documents']['originalProtocol'] = value['protocol']
    value['protocol'] = binding(PROTOCOL)
    value['study'] = 'nisqa-training-ingestion-discovery-v2'
    value['priorFailedDiscovery'] = previous
    value['priorSourceReview'] = checked_review(
        ROOT/'work/nisqa-ingest-20260927/discovery-source-review.json', previous['plan.json']['sha256'])
    value['validatorPolicy'] = dict(dateMinimumGapSeconds=60,
        allowAbsentLastModifiedOnIfRange206=True, requireMatchingETagInETagMode=True)
    value['sources'].update({name: binding(Path(__file__).parent/name) for name in V2_SOURCE_NAMES})
    return value


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh research output required')
    value = declaration()
    output.mkdir(parents=True, mode=0o700)
    write(output/'plan.json', value)
    return binding(output/'plan.json')


def load(path, sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs')
        and Path(path).name == 'plan.json', 'Canonical research plan path required')
    pin = binding(path, sha)
    value = read(pin)
    require(value == declaration(), 'Discovery source/protocol/runtime changed')
    guard(value['sources']); guard(value['documents']); guard(value['priorFailedDiscovery'])
    return value, pin


def transport(root, plan):
    from nisqa_ingest.http_transport_v2 import RemoteZipV2
    return RemoteZipV2(plan['archive']['url'], expected_size=plan['archive']['size'],
        output_directory=root/'transport', max_bytes=plan['pilotTransferLimit'],
        metadata_bytes=plan['metadataTransferLimit'], allowed_hosts=tuple(plan['allowedHosts']))


def directory(path, sha, review):
    plan, pin = load(path, sha)
    reviewer = checked_review(review, sha)
    root = Path(pin['path']).parent
    require(not (root/'transport').exists(), 'Directory discovery needs a fresh transport ledger')
    fresh(root, 'directory')
    write(root/'directory-started.json', dict(plan=pin, review=reviewer))
    remote = None
    try:
        remote = transport(root, plan)
        remote.bootstrap()
        members = remote.members()
        write(root/'directory/members.json', members)
        guard(plan['sources']); guard(plan['documents']); binding(PROTOCOL, plan['protocol']['sha256'])
        write(root/'directory-freeze.json', dict(complete=True, plan=pin, review=reviewer,
              members=binding(root/'directory/members.json'),
              transport=transport_snapshot(remote, root/'directory'), **FLAGS))
        return binding(root/'directory-freeze.json')
    except Exception as error:
        write(root/'directory-failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise
    finally:
        if remote is not None:
            remote.close()


def declare_metadata(path, sha, directory_sha):
    plan, pin = load(path, sha)
    root = Path(pin['path']).parent
    require(isinstance(directory_sha, str) and len(directory_sha) == 64, 'Caller-pinned directory SHA required')
    freeze = binding(root/'directory-freeze.json', directory_sha)
    value = read(freeze)
    require(value['complete'] is True and value['plan'] == pin, 'Completed matching directory required')
    checked_review(value['review']['path'], sha)
    check_ledger(root, value['transport'])
    members = read(value['members'])
    requests_value = metadata_requests(members)
    write(root/'metadata-plan.json', dict(plan=pin, directoryFreeze=freeze,
          requests=requests_value, targetFieldsAccessed=False, **FLAGS))
    return binding(root/'metadata-plan.json')


def metadata(path, sha, request_sha):
    plan, pin = load(path, sha)
    root = Path(pin['path']).parent
    request_pin = binding(root/'metadata-plan.json', request_sha)
    requested = read(request_pin)
    frozen = read(requested['directoryFreeze'])
    require(requested['plan'] == pin and frozen['plan'] == pin and frozen['complete'] is True
            and requested['requests'] == metadata_requests(read(frozen['members'])),
            'Metadata request declaration differs')
    checked_review(frozen['review']['path'], sha)
    check_ledger(root, frozen['transport'])
    fresh(root, 'metadata')
    write(root/'metadata-started.json', dict(plan=pin, requestPlan=request_pin))
    remote = None
    try:
        remote = transport(root, plan)
        remote.bootstrap()
        members = remote.members()
        require(members == read(frozen['members']), 'Archive directory changed')
        allowed = [item['filename'] for item in requested['requests']]
        records = []
        for index, item in enumerate(requested['requests']):
            record = remote.acquire(item['filename'], allowlist=allowed,
                                    output_name=f'metadata-{index:02d}',
                                    max_compressed=plan['metadataMemberMaxBytes'],
                                    max_uncompressed=plan['metadataMemberMaxBytes'],
                                    metadata=True)
            records.append(dict(role=item['role'], filename=item['filename'], acquired=record))
        write(root/'metadata/records.json', records)
        guard(plan['sources']); guard(plan['documents']); binding(PROTOCOL, plan['protocol']['sha256'])
        write(root/'metadata-freeze.json', dict(complete=True, plan=pin, requestPlan=request_pin,
              records=binding(root/'metadata/records.json'),
              transport=transport_snapshot(remote, root/'metadata'), **FLAGS))
        return binding(root/'metadata-freeze.json')
    except Exception as error:
        write(root/'metadata-failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise
    finally:
        if remote is not None:
            remote.close()


def identity_inventory(path, sha, metadata_sha):
    plan, pin = load(path, sha)
    root = Path(pin['path']).parent
    require(isinstance(metadata_sha, str) and len(metadata_sha) == 64, 'Caller-pinned metadata SHA required')
    freeze = binding(root/'metadata-freeze.json', metadata_sha)
    frozen = read(freeze)
    require(frozen['complete'] is True and frozen['plan'] == pin, 'Matching metadata freeze required')
    check_ledger(root, frozen['transport'])
    fresh(root, 'identity-inventory')
    write(root/'identity-inventory-started.json', dict(plan=pin, metadataFreeze=freeze))
    try:
        value = metadata_identity(read(frozen['records']))
        write(root/'identity-inventory/inventory.json', value)
        guard(plan['sources']); guard(plan['documents']); binding(PROTOCOL, plan['protocol']['sha256'])
        write(root/'identity-inventory-freeze.json', dict(complete=True, plan=pin,
              metadataFreeze=freeze, inventory=binding(root/'identity-inventory/inventory.json'), **FLAGS))
        return binding(root/'identity-inventory-freeze.json')
    except Exception as error:
        write(root/'identity-inventory-failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'directory', 'declare-metadata', 'metadata',
                                           'identity-inventory'))
    for name in ('output', 'plan', 'review'):
        parser.add_argument('--'+name, type=Path)
    for name in ('plan-sha256', 'request-sha256', 'directory-sha256', 'metadata-sha256'):
        parser.add_argument('--'+name)
    args = parser.parse_args()
    if args.command == 'declare':
        result = declare(args.output)
    elif args.command == 'directory':
        result = directory(args.plan, args.plan_sha256, args.review)
    elif args.command == 'declare-metadata':
        result = declare_metadata(args.plan, args.plan_sha256, args.directory_sha256)
    elif args.command == 'identity-inventory':
        result = identity_inventory(args.plan, args.plan_sha256, args.metadata_sha256)
    else:
        result = metadata(args.plan, args.plan_sha256, args.request_sha256)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
