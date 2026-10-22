"""Opaque training lineage strings only; no reader grammar or score decoding."""
import argparse
import csv
import io
import json
from pathlib import Path

from nisqa_ingest.discovery import binding, read, require, write
from nisqa_ingest import discovery_v2

FIELDS = ('con', 'file', 'con_description', 'filename_deg', 'filename_ref',
          'source', 'lang', 'filepath_ref')
TARGETS = ('mos', 'noi', 'col', 'dis', 'loud', 'votes')


def extract(stream, expected_paths):
    rows = csv.reader(stream, strict=True)
    header = next(rows)
    require(len(header) == len(set(header)) and all(x in header for x in
        ('db', 'filepath_deg', *FIELDS)), 'Required unique identity columns absent')
    require(not set(FIELDS) & set(TARGETS), 'Targets are prohibited as lineage inputs')
    index = {name: header.index(name) for name in ('db', 'filepath_deg', *FIELDS)}
    output = {}
    for row in rows:
        require(len(row) == len(header), 'CSV row width differs')
        # Route before touching lineage or target fields in another split.
        if row[index['db']] != 'NISQA_TRAIN_LIVE':
            continue
        path = row[index['filepath_deg']]
        require(path in expected_paths and path not in output, 'Unexpected or repeated training path')
        output[path] = dict(path=path, metadata={name: row[index[name]] for name in FIELDS})
    require(set(output) == set(expected_paths), 'Training identity join incomplete')
    return dict(training=[output[key] for key in sorted(output)],
        columns=list(FIELDS), allValuesOpaqueStrings=True, readerSemanticsVerified=False,
        captureSemanticsVerified=False, numericTargetsAccessed=False,
        selectedIdentitiesFrozen=False, readinessForAudioAcquisition=False)


def declaration():
    root = discovery_v2.HERE/'outputs/nisqa-20260927/discovery-v2'
    plan = binding(root/'plan.json', 'cfd3a8d8dca39330279fcd33bdbe234df8b90d1455a3db4c40c23855ec5f9077')
    discovery_v2.load(plan['path'], plan['sha256'])
    freeze = binding(root/'identity-inventory-freeze.json',
        '810a9f3d38c17a18e8729ab04337e914771247e38dd24adc728a82fa6948dcb3')
    inventory = read(freeze)['inventory']; read(inventory)
    metadata_freeze = binding(root/'metadata-freeze.json',
        'd8d476a5363d05277cedc9a454c3673f5d5e1e1f96e87bf5fbf5e3dc4c323222')
    records_pin = read(metadata_freeze)['records']
    records = read(records_pin)
    combined = next(x['acquired'] for x in records if
        x['filename'] == 'NISQA_Corpus/NISQA_corpus_file.csv')
    binding(combined['path'], combined['sha256'])
    return dict(study='nisqa-opaque-training-lineage-inventory-v1', discoveryPlan=plan,
        identityFreeze=freeze, inventory=inventory, metadataFreeze=metadata_freeze,
        metadataRecords=records_pin, combinedMember=combined,
        columns=list(FIELDS), valuesAreOpaque=True, numericTargetsAccessed=False,
        sources={name: binding(Path(__file__).parent/name) for name in
            ('lineage_inventory.py', 'test_lineage_inventory.py')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    root = args.output.resolve()
    require(root.is_relative_to(discovery_v2.HERE/'outputs'), 'Research output required')
    if args.command == 'declare':
        require(not root.exists(), 'Fresh output required')
        value = declaration()
        root.mkdir(parents=True, mode=0o700)
        write(root/'plan.json', value)
        pin = binding(root/'plan.json')
    else:
        require(isinstance(args.plan_sha256, str) and len(args.plan_sha256) == 64,
            'Caller-pinned plan SHA required')
        plan_pin = binding(root/'plan.json', args.plan_sha256)
        value = read(plan_pin)
        require(value == declaration(), 'Lineage source/input declaration differs')
        require(not any((root/name).exists() for name in ('started.json', 'inventory.json',
            'freeze.json', 'failure.json')), 'No implicit restart')
        write(root/'started.json', dict(plan=plan_pin))
        try:
            expected = {x['path'] for x in read(value['inventory'])['identities']['training']}
            raw = Path(value['combinedMember']['path']).read_bytes()
            require(len(raw) <= discovery_v2.MEMBER_LIMIT, 'Metadata member exceeds bound')
            result = extract(io.StringIO(raw.decode('utf-8-sig'), newline=''), expected)
            require(value == declaration(), 'Inputs changed during routing')
            write(root/'inventory.json', result)
            write(root/'freeze.json', dict(plan=plan_pin, inventory=binding(root/'inventory.json'),
                complete=True, trainingCount=len(result['training']), numericTargetsAccessed=False))
            pin = binding(root/'freeze.json')
        except Exception as error:
            write(root/'failure.json', dict(errorType=type(error).__name__))
            raise
    print(json.dumps(pin))


if __name__ == '__main__':
    main()
