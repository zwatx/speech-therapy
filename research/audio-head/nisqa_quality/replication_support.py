"""Pure blind replication identities and a separate 40-row target boundary."""
import copy
import csv
import hashlib
import math
import re

from nisqa_ingest import routing, selected_targets, source_code_selection as source
from nisqa_ingest.discovery import require
from nisqa_quality import selection as selector, targets

SALT = 'cadence-nisqa-quality-replication-40-v1'
FLAGS = dict(selector.FLAGS, qualityTargetsInterpreted=False, replicationLabelsAccessed=False)
POLICY = dict(version='nisqa-quality-replication-support-v1', salt=SALT, count=40,
    partition='replication', conditionQuotas={'phone':20,'Skype':20},
    edges=list(selector.POLICY['edges']),
    ordering='phone20 then Skype20 unused components; salted component hash then ID',
    memberOrdering='salted group hash then group ID; salted file hash then path',
    namespaces=['component','group','file'], hashFormat='UTF8 salt NUL namespace NUL value',
    exclusions='complete full-graph pilot and all current200 component closures',
    reservations='all rows and group/book/reference codes of every chosen component',
    supportedNominalGroupForm='atomic DNS-reader_<readerNumberCode>; approximate codes, not people',
    noReplacement=True, oneReplicationDraw=True, outcomeDependentSelection=False, **FLAGS)
TARGET_POLICY = dict(copy.deepcopy(selected_targets.POLICY),
    version='nisqa-quality-replication-targets-v1', selectedCount=40, partition='replication',
    invalidValues='null plus generic per-field error; no replacement, dropping, clipping or token exposure')
_NUMBER = re.compile(selected_targets.NUMBER,re.ASCII)


class ReplicationTargetError(ValueError):
    """Generic driver-visible category; messages never contain target tokens."""
    def __init__(self,reason):
        self.reason=reason
        super().__init__('Replication target '+reason+' failed; no replacement permitted')


def digest(namespace,value):
    return hashlib.sha256((SALT+'\0'+namespace+'\0'+value).encode()).hexdigest()


def _reservation(components,selected):
    return dict(componentIDs=sorted(c['componentID'] for c in components),
        membership={field:sorted({value for c in components for value in c['membership'][field]})
                    for field in POLICY['edges']},
        reservedPaths=sorted(r['path'] for c in components for r in c['rows']),
        selectedPaths=[r['path'] for r in selected])


def select_replication(graph,current_study_selected):
    """Reserve all previous closures, then choose once without reading outcomes."""
    require(isinstance(graph,dict) and 'eligibleRows' in graph and 'pilotSelected' in graph,
            'Validated full component graph required')
    require(graph==selector.build_components(graph['eligibleRows'],graph['pilotSelected']),
            'Full graph, pilot closure or identity flags differ')
    require(all(r['readerGroup']=='DNS-reader_'+r['readerNumberCode'] for r in graph['eligibleRows']),
            'Fixed atomic nominal group inventory required')
    targets.validate_selected(current_study_selected)
    by_path={row['path']:(component,row) for component in graph['components'] for row in component['rows']}
    study_ids=set()
    for row in current_study_selected:
        require(row['path'] in by_path,'Current study identity absent from full graph')
        component,original=by_path[row['path']]
        expected=dict(original,componentID=component['componentID'],partition=row['partition'])
        require(not component['excludedByPilot'] and row==dict(expected,identitySha256=selector.identity_hash(expected)),
                'Current study graph identity or pilot exclusion differs')
        study_ids.add(component['componentID'])
    require(len(study_ids)==200,'Exactly 200 current study components required')
    eligible=[c for c in graph['components'] if not c['excludedByPilot'] and c['componentID'] not in study_ids]
    support=dict(components=len(eligible),rows=sum(len(c['rows']) for c in eligible),
        groups=len({v for c in eligible for v in c['membership']['readerGroup']}),
        books=len({v for c in eligible for v in c['membership']['bookCode']}),
        references=len({v for c in eligible for v in c['membership']['sourceReferenceID']}),
        conditionComponents={condition:sum(bool(c['conditionSupport'][condition]) for c in eligible)
                             for condition in selector.CONDITIONS},
        bothConditionComponents=sum(all(c['conditionSupport'][condition] for condition in selector.CONDITIONS) for c in eligible))
    used=set(); selected=[]
    by_id={c['componentID']:c for c in eligible}
    for condition in selector.CONDITIONS:
        ordered=sorted((c for c in eligible if c['conditionSupport'][condition] and c['componentID'] not in used),
                       key=lambda c:(digest('component',c['componentID']),c['componentID']))
        require(len(ordered)>=20,'Insufficient unused components for fixed replication capture quota')
        for component in ordered[:20]:
            options=[r for r in component['rows'] if r['captureCondition']==condition]
            group=min({r['readerGroup'] for r in options},key=lambda g:(digest('group',g),g))
            original=min((r for r in options if r['readerGroup']==group),key=lambda r:(digest('file',r['path']),r['path']))
            record=dict(original,componentID=component['componentID'],partition='replication')
            record['identitySha256']=selector.identity_hash(record); selected.append(record)
            used.add(component['componentID'])
    validate_selected40(selected)
    reservations=dict(pilot=_reservation([c for c in graph['components'] if c['excludedByPilot']],graph['pilotSelected']),
        currentStudy=_reservation([c for c in graph['components'] if c['componentID'] in study_ids],
                                  sorted(current_study_selected,key=lambda r:r['path'])),
        replication=_reservation([by_id[cid] for cid in sorted(used)],selected))
    for prior in ('pilot','currentStudy'):
        require(all(not set(reservations[prior]['membership'][field]) &
                    set(reservations['replication']['membership'][field]) for field in POLICY['edges']),
                'Replication component provenance overlaps prior sample')
    selected_paths={r['path'] for r in selected}; evidence=[]
    for component in graph['components']:
        cid=component['componentID']
        reason=('pilot component closure' if component['excludedByPilot'] else 'current200 component closure' if cid in study_ids
                else 'replication reserved unselected member' if cid in used else 'untouched reserve; not chosen by fixed hash')
        evidence.extend(dict(path=r['path'],componentID=cid,reason=reason) for r in component['rows'] if r['path'] not in selected_paths)
    return dict(selected=selected,selectedCount=40,selectedComponentCount=40,conditionCounts={'phone':20,'Skype':20},
        graph=copy.deepcopy(graph),componentMembership=copy.deepcopy(graph['components']),remainingSupport=support,
        pilotClosure=list(graph['pilotClosure']),currentStudyComponentIDs=sorted(study_ids),reservations=reservations,
        exclusions=evidence,exclusionEvidence=copy.deepcopy(evidence),policy=copy.deepcopy(POLICY),**FLAGS)


def validate_selected40(selected):
    require(isinstance(selected,list) and len(selected)==40 and all(isinstance(r,dict) for r in selected),
            'Exactly forty replication identity records required')
    for row in selected:
        require({'path','publisherMetadata','componentID','partition','readerGroup','identitySha256'}<=set(row),
                'Replication identity fields missing')
        original=source._row(dict(path=row['path'],metadata=row['publisherMetadata']))
        require(row['readerGroup']=='DNS-reader_'+original['readerNumberCode']
            and row['partition']=='replication' and re.fullmatch('[0-9a-f]{64}',str(row['componentID'])) is not None,
            'Replication source group, partition or component invalid')
        expected=dict(original,readerGroup=row['readerGroup'],componentID=row['componentID'],partition='replication')
        require(row==dict(expected,identitySha256=selector.identity_hash(expected)),
                'Replication identity metadata or hash differs')
    require(all(len({r[key] for r in selected})==40 for key in ('path','readerGroup','componentID')),
            'Replication paths, groups and components must be distinct')
    require([r['captureCondition'] for r in selected]==['phone']*20+['Skype']*20,
            'Fixed replication order and capture quotas differ')
    return selected


def parse_replication_targets(stream,selected40):
    """Parse only the separately authorized forty rows; drivers own review barriers.

    CSV tokenization reads combined strings. Other targets are never indexed.
    Invalid scalar values remain null with generic errors and incomplete counts.
    Structural failures raise ReplicationTargetError(reason='parse'|'coverage'|'join').
    """
    try: selected=validate_selected40(selected40)
    except (ValueError,KeyError,TypeError): raise ReplicationTargetError('join') from None
    by_path={r['path']:r for r in selected}; found={}
    try: reader,header,index=routing._reader(stream,('db','filepath_deg')+routing.TARGETS)
    except (ValueError,csv.Error,UnicodeError): raise ReplicationTargetError('parse') from None
    try:
        for row in reader:
            try: db,path,training=routing._identity(row,index)
            except (ValueError,KeyError,TypeError): raise ReplicationTargetError('join') from None
            if path not in by_path: continue
            if not training or db!=routing.TRAIN: raise ReplicationTargetError('join')
            if path in found: raise ReplicationTargetError('coverage')
            if len(row)!=len(header): raise ReplicationTargetError('parse')
            quality,missing,errors={},{},{}
            for name in routing.TARGETS:
                token=row[index[name]]; quality[name]=None
                if type(token) is str and token in ('','NaN'): missing[name]=token
                elif type(token) is str and _NUMBER.fullmatch(token) is not None:
                    try: value=float(token)
                    except (ValueError,OverflowError): value=float('nan')
                    if math.isfinite(value) and 1<=value<=5: quality[name]=value
                    else: errors[name]='Invalid selected nominal quality value'
                else: errors[name]='Invalid selected nominal quality value'
            identity=by_path[path]
            found[path]=dict(db=db,path=path,partition='replication',componentID=identity['componentID'],
                identitySha256=identity['identitySha256'],quality=quality,declaredMissing=missing,errors=errors)
    except (csv.Error,UnicodeError): raise ReplicationTargetError('parse') from None
    if set(found)!=set(by_path): raise ReplicationTargetError('coverage')
    rows=[found[r['path']] for r in selected]
    missing_counts={name:sum(name in r['declaredMissing'] for r in rows) for name in routing.TARGETS}
    invalid_counts={name:sum(name in r['errors'] for r in rows) for name in routing.TARGETS}
    return dict(rows=rows,phase='replication',selectedPaths=[r['path'] for r in rows],
        completeTargets=not any(missing_counts.values()) and not any(invalid_counts.values()),
        missingCounts=missing_counts,invalidCounts=invalid_counts,policy=copy.deepcopy(TARGET_POLICY),
        trainingOnly=True,csvTokenizationIncludesCombinedFields=True,replicationLabelsAccessed=True)
