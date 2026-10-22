"""Freeze and execute metadata-only discovery; no quality target conversion."""
import argparse
import csv
import hashlib
import io
import json
import platform
import sys
import zlib
from pathlib import Path, PurePosixPath

import requests

from nisqa_ingest import routing

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
EVIDENCE = ROOT / 'work/nisqa-ingest-20260927/source-evidence'
PROTOCOL = ROOT / 'docs/model/nisqa-training-ingestion-protocol.md'
ARCHIVE = dict(url='https://zenodo.org/records/4728081/files/NISQA_Corpus.zip',
               size=15945499507, advertisedMd5='c4997a873e9397dd6d1fa787d70c3106')
DOC_HASHES = {
    'record.json': 'cf8b6fee229e39fcaf7a04a00036148fab9ba8a44da45a50cdadd7a347fafad5',
    'readme.txt': '0c68b07860dcf9c0d73e6969ba78f6026b94866f697fc1549d837096f12e4a54',
    'corpus-wiki.md': '893b9939df6df87e69fbf4aa36c987a92681d55757d61eade61340c42675e1a0',
    'official-config.yaml': '92e7985f91e8c20a86ae32e1bd582c518ed9d92edc87f3a13863822854c21e6e',
}
SOURCE_NAMES = ('__init__.py', 'discovery.py', 'remote_zip.py', 'routing.py',
                'test_discovery.py', 'test_remote_zip.py', 'test_routing.py')
LIMIT = 16 * 1024 * 1024
MEMBER_LIMIT = 8 * 1024 * 1024
FLAGS = dict(trainingPerformed=False, modelInferencePerformed=False,
             evaluationAudioAcquired=False, qualityTargetsInterpreted=False,
             clinicalUseEligible=False, learnerJudgmentsEnabled=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path, expected=None):
    path = Path(path).absolute()
    require(path.is_file() and not path.is_symlink(), 'Regular artifact required')
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    require(expected is None or value == expected, 'Pinned artifact differs')
    return dict(path=str(path), sha256=value)


def read(pin):
    binding(pin['path'], pin['sha256'])
    return json.loads(Path(pin['path']).read_text())


def guard(pins):
    for pin in pins.values():
        binding(pin['path'], pin['sha256'])


def write(path, value):
    with Path(path).open('x') as stream:
        Path(path).chmod(0o600)
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def declaration():
    docs = {name: binding(EVIDENCE/name, sha) for name, sha in DOC_HASHES.items()}
    docs['sourceManifest'] = binding(EVIDENCE/'manifest.json')
    manifest = read(docs['sourceManifest'])
    require(manifest['corpusMembersAcquired'] is False
            and {r['name'] for r in manifest['records']} == set(DOC_HASHES)
            and all(r.get('status') == 200 and r['sha256'] == DOC_HASHES[r['name']]
                    for r in manifest['records']), 'Incomplete source-document evidence')
    record = read(docs['record.json'])
    obj = next(f for f in record['files'] if f['key'] == 'NISQA_Corpus.zip')
    require(record['id'] == 4728081 and obj['size'] == ARCHIVE['size']
            and obj['checksum'] == 'md5:' + ARCHIVE['advertisedMd5'], 'Official object differs')
    return dict(study='nisqa-training-ingestion-discovery-v1', archive=ARCHIVE,
                protocol=binding(PROTOCOL), documents=docs,
                sources={name: binding(Path(__file__).parent/name) for name in SOURCE_NAMES},
                runtime=dict(python=sys.version, requests=requests.__version__,
                             zlib=zlib.ZLIB_VERSION, platform=platform.platform()),
                allowedHosts=['zenodo.org'], metadataTransferLimit=LIMIT,
                pilotTransferLimit=256*1024*1024,
                metadataMemberMaxBytes=MEMBER_LIMIT,
                phases=['directory', 'metadata', 'identity-inventory'], **FLAGS)


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
    guard(value['sources']); guard(value['documents'])
    return value, pin


def checked_review(path, plan_sha):
    pin = binding(path)
    value = read(pin)
    require(value.get('planSha256') == plan_sha and value.get('verdict') == 'clear'
            and value.get('blockingFindings') == [] and value.get('independent') is True
            and isinstance(value.get('reviewer'), str), 'Independent clear source review required')
    return pin


def fresh(root, label):
    require(not any((root/name).exists() for name in
                    (label, label+'-started.json', label+'-freeze.json', label+'-failure.json')),
            'Preserve partial phase; no implicit restart')
    (root/label).mkdir()


def metadata_requests(members):
    """Only notices and training-side/schema tables; never an audio member."""
    chosen = []
    for member in members:
        name = member['filename']
        path = PurePosixPath(name)
        if member.get('is_dir', False) or name.endswith('/'):
            continue
        parent, base = str(path.parent), path.name.lower()
        if parent not in ('NISQA_Corpus', 'NISQA_Corpus/NISQA_TRAIN_LIVE'):
            continue
        notice = (base in ('readme.txt', 'readme.md', 'license.txt', 'licence.txt')
                  or base.endswith(('_license.txt', '_licence.txt')))
        table = (parent == 'NISQA_Corpus' and path.name == 'NISQA_corpus_file.csv')
        train_table = parent.endswith('/NISQA_TRAIN_LIVE') and base.endswith('.csv')
        if notice or table or train_table:
            require(0 <= member['file_size'] <= MEMBER_LIMIT
                    and 0 <= member['compress_size'] <= MEMBER_LIMIT,
                    'Metadata member exceeds declared bound')
            chosen.append(dict(filename=name, role='notice' if notice else 'metadata',
                               directoryEntry=member))
    require(any(c['filename'] == 'NISQA_Corpus/NISQA_corpus_file.csv' for c in chosen),
            'Official combined file table absent; no guessed replacement')
    require(any(c['role'] == 'notice' and '/NISQA_TRAIN_LIVE/' in c['filename'] for c in chosen),
            'Training subset notice absent')
    require(len(chosen) <= 20, 'Metadata request list exceeds declared bound')
    return sorted(chosen, key=lambda c: c['filename'])


def transport(root, plan):
    from nisqa_ingest.remote_zip import RemoteZip
    return RemoteZip(plan['archive']['url'], expected_size=plan['archive']['size'],
                     output_directory=root/'transport', max_bytes=plan['pilotTransferLimit'],
                     metadata_bytes=plan['metadataTransferLimit'],
                     allowed_hosts=tuple(plan['allowedHosts']))


def transport_snapshot(remote, output):
    """Freeze copies; the persistent ledger itself changes in later phases."""
    value = remote.manifest()
    for name in ('state', 'journal'):
        pin = value[name]
        binding(pin['path'], pin['sha256'])
        target = output/(name+'.snapshot')
        with target.open('xb') as stream:
            stream.write(Path(pin['path']).read_bytes())
        target.chmod(0o600)
        value[name] = binding(target)
    return value


def check_ledger(root, frozen):
    for name, live_name in (('state', 'transport-state.json'), ('journal', 'request-journal.jsonl')):
        pin = frozen[name]
        binding(pin['path'], pin['sha256'])
        binding(root/'transport'/live_name, pin['sha256'])


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


def metadata_identity(records):
    """Read headers and identities only; do not emit or interpret targets."""
    headers, inventory_value = {}, None
    for record in records:
        if record['role'] != 'metadata' or not record['filename'].endswith('.csv'):
            continue
        pin = record['acquired']
        binding(pin['path'], pin['sha256'])
        require(Path(pin['path']).stat().st_size <= MEMBER_LIMIT, 'CSV exceeds declared bound')
        text = Path(pin['path']).read_bytes().decode('utf-8-sig')
        stream = io.StringIO(text, newline='')
        try:
            header = next(csv.reader(stream, strict=True))
        except StopIteration:
            raise ValueError('CSV header absent') from None
        require(header and len(header) == len(set(header)), 'Invalid CSV header')
        headers[record['filename']] = header
        if record['filename'] == 'NISQA_Corpus/NISQA_corpus_file.csv':
            require(inventory_value is None, 'Duplicate combined metadata member')
            inventory_value = routing.inventory(io.StringIO(text, newline=''))
    require(inventory_value is not None, 'Combined metadata not acquired')
    return dict(headers=headers, identities=inventory_value,
                groupSemanticsVerified=False, selectedIdentitiesFrozen=False,
                readinessForAudioAcquisition=False, **FLAGS)


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
