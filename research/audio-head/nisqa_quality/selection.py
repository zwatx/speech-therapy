"""Pure identity-only component selection; publisher codes are not people."""
import hashlib
import json

from nisqa_ingest import source_code_selection as source
from nisqa_ingest.discovery import require

SALT = 'cadence-nisqa-quality-200-v1'
CONDITIONS = ('phone', 'Skype')
PARTITIONS = ('fit', 'selection', 'confirmation')
FLAGS = dict(personIdentityVerified=False, speakerIndependentEvaluationEligible=False,
             speakerAgeCoverageVerified=False, numericTargetsAccessed=False,
             waveformAcquired=False, trainingPerformed=False, modelInferencePerformed=False,
             evaluationAudioAcquired=False, clinicalUseEligible=False, learnerJudgmentsEnabled=False)
POLICY = dict(version='nisqa-quality-component-selection-v1', salt=SALT, count=200,
    conditionQuotas={'phone': 100, 'Skype': 100},
    partitionQuotas={'fit': {'phone': 60, 'Skype': 60}, 'selection': {'phone': 20, 'Skype': 20},
                     'confirmation': {'phone': 20, 'Skype': 20}},
    edges=['readerGroup', 'sourceReferenceID', 'bookCode'],
    componentID='SHA256 canonical sorted book/group/reference sets',
    pilotExclusion='full graph closure touching any inspected pilot group, book or reference',
    ordering='phone then Skype; exclusive-condition components before shared; salted component hash then ID',
    memberOrdering='salted group hash then group ID; salted file hash then path',
    partitionOrdering='within each condition salted partition hash of component ID then ID',
    namespaces=['component', 'group', 'file', 'partition'],
    hashFormat='UTF8 salt NUL namespace NUL value; canonical JSON sorted keys and compact separators',
    reservations='every row of each chosen component belongs only to its assigned partition',
    noReplacement=True, sourceCodeSemantics='approximate publisher provenance; not verified people',
    **FLAGS)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def identity_hash(row):
    return hashlib.sha256(canonical(row).encode()).hexdigest()


def digest(namespace, value):
    return hashlib.sha256((SALT+'\0'+namespace+'\0'+value).encode()).hexdigest()


def _validated_rows(rows):
    require(isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows),
            'Identity-only eligible rows required')
    require(all('path' in r and 'publisherMetadata' in r for r in rows), 'Eligible lineage fields missing')
    prepared = source.prepare_inventory(dict(
        training=[dict(path=r['path'], metadata=r['publisherMetadata']) for r in rows],
        columns=list(source.FIELDS), **source.INVENTORY_FLAGS))
    expected = prepared['eligible']
    require(sorted(rows, key=lambda r: r['path']) == expected,
            'Eligible rows contain undeclared fields or differ from validated opaque lineage')
    return expected


def build_components(eligible_rows, pilot_selected20):
    """Build over every row first, then exclude the transitive pilot closure.

    The driver binds and requires the real 1,020-row input. This pure function
    also accepts smaller synthetic inventories for meaningful graph tests.
    """
    rows = _validated_rows(eligible_rows)
    require(isinstance(pilot_selected20, list) and len(pilot_selected20) == 20
            and all(isinstance(r, dict) for r in pilot_selected20), 'Exactly twenty pilot identities required')
    by_path = {r['path']: r for r in rows}
    pilot = []
    for row in pilot_selected20:
        require('path' in row and row['path'] in by_path, 'Pilot identity absent from complete inventory')
        expected = by_path[row['path']]
        require(row == dict(expected, identitySha256=identity_hash(expected)),
                'Pilot identity or metadata binding differs')
        pilot.append(row)
    require(len({r['path'] for r in pilot}) == 20 and len({r['readerGroup'] for r in pilot}) == 20,
            'Distinct original pilot groups required')
    pilot.sort(key=lambda r: r['path'])
    parent = {}
    def find(node):
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]
    def join(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)
    for row in rows:
        path = ('path', row['path'])
        for field in POLICY['edges']:
            join(path, (field, row[field]))
    groups = {}
    for row in rows:
        groups.setdefault(find(('path', row['path'])), []).append(row)
    pilot_sets = {field: {r[field] for r in pilot} for field in POLICY['edges']}
    components = []
    for members in groups.values():
        sets = {field: sorted({r[field] for r in members}) for field in POLICY['edges']}
        component_id = identity_hash(sets)
        touches = {field: sorted(set(sets[field]) & pilot_sets[field]) for field in POLICY['edges']}
        excluded = any(touches.values())
        components.append(dict(componentID=component_id, membership=sets,
            rows=members, paths=[r['path'] for r in members],
            conditionSupport={c: sum(r['captureCondition'] == c for r in members) for c in CONDITIONS},
            excludedByPilot=excluded, pilotTouches=touches))
    components.sort(key=lambda c: c['componentID'])
    remaining = [c for c in components if not c['excludedByPilot']]
    support = dict(totalRows=len(rows), totalComponents=len(components),
        excludedComponents=len(components)-len(remaining),
        excludedRows=sum(len(c['rows']) for c in components if c['excludedByPilot']),
        remainingComponents=len(remaining), remainingRows=sum(len(c['rows']) for c in remaining),
        remainingGroups=len({g for c in remaining for g in c['membership']['readerGroup']}),
        remainingBooks=len({g for c in remaining for g in c['membership']['bookCode']}),
        conditionComponents={condition: sum(bool(c['conditionSupport'][condition]) for c in remaining)
                             for condition in CONDITIONS})
    return dict(eligibleRows=rows, pilotSelected=pilot, components=components, support=support,
        pilotClosure=[c['componentID'] for c in components if c['excludedByPilot']],
        eligibilityExclusions=[dict(path=r['path'], componentID=c['componentID'], reason='pilot component closure')
                               for c in components if c['excludedByPilot'] for r in c['rows']], **FLAGS)


def select_study(graph):
    """Choose exactly 200 metadata-only components and reserve their full rows."""
    require(isinstance(graph, dict) and 'eligibleRows' in graph and 'pilotSelected' in graph,
            'Validated component graph required')
    require(graph == build_components(graph['eligibleRows'], graph['pilotSelected']),
            'Component graph or identity-only flags differ')
    eligible = [c for c in graph['components'] if not c['excludedByPilot']]
    by_id = {c['componentID']: c for c in eligible}
    candidates = {condition: {c['componentID'] for c in eligible if c['conditionSupport'][condition]}
                  for condition in CONDITIONS}
    require(all(len(ids) >= 100 for ids in candidates.values())
            and len(candidates['phone'] | candidates['Skype']) >= 200,
            'Insufficient distinct components for fixed capture quotas')
    used, selected = set(), []
    reservation = {}
    for condition, other in (('phone','Skype'), ('Skype','phone')):
        ordered = sorted(candidates[condition], key=lambda component_id:
            (component_id in candidates[other], digest('component', component_id), component_id))
        available = [component_id for component_id in ordered if component_id not in used]
        require(len(available) >= 100, 'Insufficient distinct components for fixed capture quotas')
        chosen = available[:100]
        used.update(chosen)
        chosen.sort(key=lambda component_id: (digest('partition',component_id), component_id))
        for rank, component_id in enumerate(chosen):
            partition = 'fit' if rank < 60 else 'selection' if rank < 80 else 'confirmation'
            component = by_id[component_id]
            options = [r for r in component['rows'] if r['captureCondition'] == condition]
            nominal_groups = {r['readerGroup'] for r in options}
            group = min(nominal_groups, key=lambda value: (digest('group',value),value))
            row = min((r for r in options if r['readerGroup'] == group),
                      key=lambda r: (digest('file',r['path']),r['path']))
            record = dict(row, componentID=component_id, partition=partition)
            record['identitySha256'] = identity_hash(record)
            selected.append(record)
            reservation[component_id] = partition
    partitions = {}
    for partition in PARTITIONS:
        components = [by_id[component_id] for component_id in sorted(reservation)
                      if reservation[component_id] == partition]
        partitions[partition] = dict(componentIDs=[c['componentID'] for c in components],
            membership={field: sorted({value for c in components for value in c['membership'][field]})
                        for field in POLICY['edges']},
            reservedPaths=sorted(r['path'] for c in components for r in c['rows']),
            selectedPaths=[r['path'] for r in selected if r['partition'] == partition])
    for i, partition in enumerate(PARTITIONS):
        rows = [r for r in selected if r['partition'] == partition]
        require({condition: sum(r['captureCondition'] == condition for r in rows) for condition in CONDITIONS}
                == POLICY['partitionQuotas'][partition], 'Partition capture quotas differ')
        for other in PARTITIONS[i+1:]:
            require(not set(partitions[partition]['componentIDs']) & set(partitions[other]['componentIDs'])
                    and all(not set(partitions[partition]['membership'][field]) &
                            set(partitions[other]['membership'][field]) for field in POLICY['edges']),
                    'Reserved partition provenance overlaps')
    require(len(selected) == len({r['path'] for r in selected}) == len(used) == 200
            and len({r['readerGroup'] for r in selected}) == 200, 'Fixed distinct selection differs')
    chosen_paths = {r['path'] for r in selected}
    exclusions = []
    for component in graph['components']:
        cid = component['componentID']
        reason = ('pilot component closure' if component['excludedByPilot'] else
                  'reserved unselected member' if cid in used else 'not chosen by fixed component selector')
        exclusions.extend(dict(path=row['path'], componentID=cid, partition=reservation.get(cid), reason=reason)
                          for row in component['rows'] if row['path'] not in chosen_paths)
    return dict(selected=selected, selectedCount=200, selectedComponentCount=200,
        conditionCounts={c: sum(r['captureCondition'] == c for r in selected) for c in CONDITIONS},
        partitionCounts={p: sum(r['partition'] == p for r in selected) for p in PARTITIONS},
        support=graph['support'], eligibility=graph['eligibleRows'], componentMembership=graph['components'],
        pilotClosure=graph['pilotClosure'], eligibilityExclusions=graph['eligibilityExclusions'],
        exclusions=exclusions, partitions=partitions, **FLAGS)
