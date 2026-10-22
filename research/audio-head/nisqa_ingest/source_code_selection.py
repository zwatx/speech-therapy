"""Freeze twenty identity-only TRAIN_LIVE source-code groups, never people."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from nisqa_ingest import discovery_v2, routing
from nisqa_ingest.discovery import binding, checked_review, fresh, guard, read, require, write
from nisqa_ingest.lineage_inventory import FIELDS

HERE, ROOT = discovery_v2.HERE, discovery_v2.ROOT
PROTOCOL = ROOT/'docs/model/nisqa-source-code-pilot-v2.md'
LINEAGE = HERE/'outputs/nisqa-20260927/lineage-inventory-v1'
FREEZE_SHA = '050df5e68cd39b54b21163e67fa9315e1d4350753694e5c83598d24c2c62430a'
LINEAGE_PLAN_SHA = 'd7cc0eb333e779c4d099d97c514103e9551b1c5d5f6020ebcc78dba3f489d88c'
STUDY = 'nisqa-source-code-selection-v2'
REFERENCE_GRAMMAR = r'book_(?P<book>[0-9]{5})_chp_(?P<chapter>[0-9]{4})_reader_(?P<reader>[0-9]{5})_(?P<segment>[0-9]+)_seg\.wav'
DEGRADED_SUFFIX = r'_live_(?P<capture>phone|skype)_(?P<index>[0-9]+)\.wav'
DESCRIPTIONS = {'VoIP-landline to mobile': 'phone', 'Skype': 'Skype'}
FLAGS = dict(personIdentityVerified=False, speakerIndependentEvaluationEligible=False,
             numericTargetsAccessed=False, waveformAcquired=False,
             trainingPerformed=False, modelInferencePerformed=False,
             evaluationAudioAcquired=False, qualityTargetsInterpreted=False,
             clinicalUseEligible=False, learnerJudgmentsEnabled=False)
INVENTORY_FLAGS = dict(allValuesOpaqueStrings=True, readerSemanticsVerified=False,
    captureSemanticsVerified=False, numericTargetsAccessed=False, selectedIdentitiesFrozen=False,
    readinessForAudioAcquisition=False)
RULES = dict(count=20, conditions={'phone': 10, 'Skype': 10}, source='DNS', language='en',
    referenceGrammar=REFERENCE_GRAMMAR, degradedSuffixGrammar=DEGRADED_SUFFIX,
    group='DNS-reader_ plus sorted connected-component reader codes joined with +',
    merge='approximate reader code across books/chapters; exact source-reference ID links codes',
    salt=routing.SALT, ordering='phone then Skype; exclusive before shared; frozen routing.select',
    hashNamespaces='salt NUL group NUL group-ID; salt NUL file NUL canonical-path',
    noReplacement=True, scoreDefinitionAuditPending=True)


def _safe_path(value):
    require(type(value) is str and value and not value.startswith('/')
            and not any(c in value for c in ('\\', '\x00', ':'))
            and all(part not in ('', '.', '..') for part in value.split('/'))
            and str(PurePosixPath(value)) == value, 'Unsafe canonical lineage path')
    return value


def _row(row):
    require(isinstance(row, dict) and set(row) == {'path', 'metadata'}, 'Unexpected lineage row schema')
    metadata = row['metadata']
    require(isinstance(metadata, dict) and set(metadata) == set(FIELDS)
            and all(type(value) is str for value in metadata.values()),
            'Unexpected or nonopaque lineage metadata schema')
    path = _safe_path(row['path'])
    filename = metadata['filename_deg']
    reference = metadata['filename_ref']
    reference_path = _safe_path(metadata['filepath_ref'])
    require(path == routing.PREFIX + filename and PurePosixPath(path).name == filename
            and reference_path == routing.TRAIN + '/ref/' + reference,
            'Canonical filename or reference path join differs')
    require(metadata['source'] == 'DNS' and metadata['lang'] == 'en', 'Unexpected source or language')
    matched = re.fullmatch(REFERENCE_GRAMMAR, reference)
    require(matched is not None, 'Reference filename does not match declared grammar')
    degraded = re.fullmatch(re.escape(reference[:-4]) + DEGRADED_SUFFIX, filename)
    require(degraded is not None, 'Degraded filename/reference correspondence differs')
    condition = DESCRIPTIONS.get(metadata['con_description'])
    require(condition is not None and condition.lower() == degraded['capture'],
            'Capture description and filename suffix differ')
    return dict(path=path, archiveMember='NISQA_Corpus/' + path,
                filenameDeg=filename, filenameRef=reference, sourceReferenceID=reference_path,
                bookCode=matched['book'], chapterCode=matched['chapter'],
                readerNumberCode=matched['reader'], segmentCode=matched['segment'],
                captureCondition=condition, captureIndex=degraded['index'],
                publisherMetadata=dict(metadata))


def _components(rows):
    """Conservative connected components: codes plus exact reference-ID links."""
    parent = {row['readerNumberCode']: row['readerNumberCode'] for row in rows}
    def find(code):
        while parent[code] != code:
            parent[code] = parent[parent[code]]
            code = parent[code]
        return code
    references = {}
    for row in rows:
        code, reference = row['readerNumberCode'], row['sourceReferenceID']
        if reference in references:
            a, b = find(code), find(references[reference])
            parent[max(a, b)] = min(a, b)
        else:
            references[reference] = code
    components = {}
    for code in sorted(parent):
        components.setdefault(find(code), []).append(code)
    return {code: 'DNS-reader_' + '+'.join(codes)
            for codes in components.values() for code in codes}


def prepare_inventory(value, *, expected_count=None):
    """Validate every opaque training row before deriving eligibility or groups."""
    require(isinstance(value, dict) and set(value) == {'training', 'columns', *INVENTORY_FLAGS}
            and value['columns'] == list(FIELDS)
            and all(value[k] is flag for k, flag in INVENTORY_FLAGS.items()),
            'Unexpected or non-identity lineage inventory')
    require(isinstance(value['training'], list) and value['training']
            and (expected_count is None or len(value['training']) == expected_count),
            'Incomplete lineage training inventory')
    rows = [_row(row) for row in value['training']]
    require(len({row['path'] for row in rows}) == len(rows), 'Duplicate training lineage identity')
    rows.sort(key=lambda row: row['path'])
    mapping = _components(rows)
    groups = {}
    for row in rows:
        row['readerGroup'] = mapping[row['readerNumberCode']]
        groups.setdefault(row['readerGroup'], []).append(row)
    membership = [dict(readerGroup=group,
        readerNumberCodes=sorted({r['readerNumberCode'] for r in members}),
        paths=[r['path'] for r in members],
        sourceReferenceIDs=sorted({r['sourceReferenceID'] for r in members}),
        conditionSupport={condition: sum(r['captureCondition'] == condition for r in members)
                          for condition in ('phone', 'Skype')})
        for group, members in sorted(groups.items())]
    support = dict(eligibleCount=len(rows), sourceCodeGroupCount=len(groups),
        approximateReaderCodeCount=len(mapping),
        conditionRows={c: sum(r['captureCondition'] == c for r in rows) for c in ('phone', 'Skype')},
        conditionGroups={c: sum(any(r['captureCondition'] == c for r in rs) for rs in groups.values())
                         for c in ('phone', 'Skype')},
        exclusiveGroups={c: sum({r['captureCondition'] for r in rs} == {c} for rs in groups.values())
                         for c in ('phone', 'Skype')},
        sharedGroups=sum({r['captureCondition'] for r in rs} == {'phone', 'Skype'} for rs in groups.values()))
    return dict(eligible=rows, groupMembership=membership, support=support,
                eligibilityExclusions=[], sourceCodeSemantics='intended publisher labels; approximate provenance only',
                **FLAGS)


def select20(prepared):
    """Reuse the frozen selector with only its three permitted identity fields."""
    require(isinstance(prepared, dict) and all(prepared.get(k) is v for k, v in FLAGS.items()),
            'Identity-only eligibility evidence required')
    rows = prepared['eligible']
    require(prepared == prepare_inventory(dict(training=[dict(path=r['path'], metadata=r['publisherMetadata'])
                      for r in rows], columns=list(FIELDS), **INVENTORY_FLAGS)),
            'Eligibility evidence was changed or contains undeclared inputs')
    chosen = routing.select([{k: row[k] for k in ('path', 'captureCondition', 'readerGroup')} for row in rows])
    by_path = {row['path']: row for row in rows}
    selected = []
    for choice in chosen:
        row = dict(by_path[choice['path']])
        row['identitySha256'] = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        selected.append(row)
    conditions = {c: sum(r['captureCondition'] == c for r in selected) for c in ('phone', 'Skype')}
    require(len(selected) == len({r['path'] for r in selected}) == 20
            and len({r['readerGroup'] for r in selected}) == 20 and conditions == RULES['conditions'],
            'Fixed twenty-source-group quotas differ')
    chosen_paths = {r['path'] for r in selected}
    excluded = [dict(path=r['path'], readerGroup=r['readerGroup'], reason='not chosen by fixed selector')
                for r in rows if r['path'] not in chosen_paths]
    return dict(selected=selected, selectionExclusions=excluded, selectedCount=20,
                selectedSourceCodeGroupCount=20, conditionCounts=conditions,
                scoreDefinitionAuditPending=True, **FLAGS)


def declaration():
    freeze_pin = binding(LINEAGE/'freeze.json', FREEZE_SHA)
    frozen = read(freeze_pin)
    plan_pin = binding(LINEAGE/'plan.json', LINEAGE_PLAN_SHA)
    require(frozen.get('complete') is True and frozen.get('plan') == plan_pin
            and frozen.get('trainingCount') == 1020 and frozen.get('numericTargetsAccessed') is False,
            'Pinned complete opaque lineage freeze required')
    lineage_plan = read(plan_pin)
    require(lineage_plan['columns'] == list(FIELDS) and lineage_plan['numericTargetsAccessed'] is False
            and lineage_plan['valuesAreOpaque'] is True, 'Lineage declaration differs')
    guard(lineage_plan['sources'])
    inventory_pin = binding(frozen['inventory']['path'], frozen['inventory']['sha256'])
    archive_plan, archive_pin = discovery_v2.load(lineage_plan['discoveryPlan']['path'],
                                                lineage_plan['discoveryPlan']['sha256'])
    sources = {name: binding(Path(__file__).parent/name) for name in
               ('source_code_selection.py', 'test_source_code_selection.py', 'routing.py')}
    return dict(study=STUDY, protocol=binding(PROTOCOL),
                inputs=dict(lineageFreeze=freeze_pin, lineagePlan=plan_pin,
                            lineageInventory=inventory_pin, discoveryPlan=archive_pin),
                sources=sources, lineageSources=lineage_plan['sources'], archiveSources=archive_plan['sources'],
                archive=archive_plan['archive'], runtime=archive_plan['runtime'],
                rules=RULES, expectedInventoryCount=1020, **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh research output required')
    value = declaration()
    output.mkdir(parents=True, mode=0o700)
    write(output/'plan.json', value)
    return binding(output/'plan.json')


def load(path, sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs') and Path(path).name == 'plan.json',
            'Canonical research selection plan required')
    pin = binding(path, sha)
    value = read(pin)
    require(value == declaration(), 'Selection source, input, protocol, or runtime changed')
    guard(value['inputs']); guard(value['sources']); guard(value['lineageSources']); guard(value['archiveSources'])
    binding(PROTOCOL, value['protocol']['sha256'])
    return value, pin


def run(path, sha, review):
    plan, pin = load(path, sha)
    reviewed = checked_review(review, sha)
    root = Path(pin['path']).parent
    fresh(root, 'selection')
    write(root/'selection-started.json', dict(plan=pin, review=reviewed))
    try:
        prepared = prepare_inventory(read(plan['inputs']['lineageInventory']), expected_count=plan['expectedInventoryCount'])
        write(root/'selection/eligible.json', prepared)
        selected = select20(prepared)
        write(root/'selection/selected.json', selected)
        load(path, sha)
        write(root/'selection-freeze.json', dict(complete=True, study=STUDY, plan=pin, review=reviewed,
            eligible=binding(root/'selection/eligible.json'), selected=binding(root/'selection/selected.json'),
            selectedCount=20, selectedSourceCodeGroupCount=20, conditionCounts=selected['conditionCounts'],
            scoreDefinitionAuditPending=True, **FLAGS))
        return binding(root/'selection-freeze.json')
    except Exception as error:
        write(root/'selection-failure.json', dict(errorType=type(error).__name__))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run'))
    for name in ('output', 'plan', 'review'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        require(args.output is not None, 'Declaration output required')
        result = declare(args.output)
    else:
        require(args.plan is not None and args.review is not None
                and isinstance(args.plan_sha256, str) and len(args.plan_sha256) == 64,
                'Pinned plan and independent review required')
        result = run(args.plan, args.plan_sha256, args.review)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
