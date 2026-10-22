"""Phase-separated nominal ratings; confirmation access needs an external barrier."""
import copy
import math
import re

from nisqa_ingest import routing, selected_targets, source_code_selection as source
from nisqa_ingest.discovery import require
from nisqa_quality import selection

POLICY = dict(copy.deepcopy(selected_targets.POLICY), version='nisqa-quality-partition-targets-v1',
              selectedCount=200, phases={'fit-selection': ['fit','selection'], 'confirmation': ['confirmation']},
              invalidValues='preserve generic per-field error and null; never replace, clip or expose token')
_NUMBER = re.compile(selected_targets.NUMBER, re.ASCII)


def validate_selected(selected200):
    require(isinstance(selected200,list) and len(selected200)==200 and
            all(isinstance(r,dict) for r in selected200), 'Exactly 200 selected identity records required')
    decoded=[]
    for row in selected200:
        require({'path','publisherMetadata','componentID','partition','identitySha256','readerGroup'} <= set(row),
                'Selected identity fields missing')
        decoded.append(source._row(dict(path=row['path'],metadata=row['publisherMetadata'])))
    # The declaration verifies atomic groups over the full fixed1020 inventory.
    # Composite future inventories require a new parser and full group mapping;
    # caller-provided DNS prefixes cannot establish a nominal group here.
    groups=source._components(decoded)
    for row,expected in zip(selected200,decoded):
        require(row['readerGroup']==groups[expected['readerNumberCode']]
                and re.fullmatch('[0-9a-f]{64}',str(row['componentID'])) is not None
                and row['partition'] in selection.PARTITIONS, 'Selected provenance or partition invalid')
        expected.update(readerGroup=row['readerGroup'],componentID=row['componentID'],partition=row['partition'])
        require(row==dict(expected,identitySha256=selection.identity_hash(expected)),
                'Selected identity metadata or hash differs')
    require(all(len({r[key] for r in selected200})==200 for key in ('path','componentID','readerGroup')),
            'Selected identities/components/groups must be distinct')
    for partition,quotas in selection.POLICY['partitionQuotas'].items():
        require({c:sum(r['partition']==partition and r['captureCondition']==c for r in selected200)
                 for c in selection.CONDITIONS}==quotas, 'Fixed partition capture quotas differ')
    return selected200


def parse_partition_targets(stream, selected200, phase):
    """Route first, skip all other phases, and expose only authorized rows.

    CSV tokenization includes combined strings; this never indexes discarded
    targets. Missing and invalid nominal ratings stay incomplete, without
    replacement. The helper's confirmation phase is for a future reviewed
    model/prediction barrier; the ingestion CLI does not authorize it.
    """
    require(phase in POLICY['phases'], 'Unknown target phase')
    selected=validate_selected(selected200)
    wanted=[r for r in selected if r['partition'] in POLICY['phases'][phase]]
    by_path={r['path']:r for r in wanted}
    reader,header,index=routing._reader(stream,('db','filepath_deg')+routing.TARGETS)
    found={}
    for row in reader:
        db,path,training=routing._identity(row,index)
        if path not in by_path: continue
        require(training and db==routing.TRAIN, 'Selected target identity is not training-only')
        require(path not in found, 'Duplicate selected target identity')
        require(len(row)==len(header), 'Selected target row width differs')
        quality,missing,errors={},{},{}
        for name in routing.TARGETS:
            token=row[index[name]]
            quality[name]=None
            if type(token) is str and token in ('','NaN'):
                missing[name]=token
            elif type(token) is str and _NUMBER.fullmatch(token) is not None:
                try: value=float(token)
                except (ValueError,OverflowError): value=float('nan')
                if math.isfinite(value) and 1<=value<=5: quality[name]=value
                else: errors[name]='Invalid selected nominal quality value'
            else: errors[name]='Invalid selected nominal quality value'
        identity=by_path[path]
        found[path]=dict(db=db,path=path,partition=identity['partition'],componentID=identity['componentID'],
                        identitySha256=identity['identitySha256'],quality=quality,declaredMissing=missing,errors=errors)
    require(set(found)==set(by_path), 'Selected target identities missing; no replacement permitted')
    rows=[found[r['path']] for r in wanted]
    missing_counts={name:sum(name in r['declaredMissing'] for r in rows) for name in routing.TARGETS}
    invalid_counts={name:sum(name in r['errors'] for r in rows) for name in routing.TARGETS}
    return dict(rows=rows,phase=phase,selectedPaths=[r['path'] for r in rows],
        completeTargets=not any(missing_counts.values()) and not any(invalid_counts.values()),
        missingCounts=missing_counts,invalidCounts=invalid_counts,policy=copy.deepcopy(POLICY),
        trainingOnly=True,csvTokenizationIncludesCombinedFields=True,
        confirmationTargetsAccessed=phase=='confirmation')
