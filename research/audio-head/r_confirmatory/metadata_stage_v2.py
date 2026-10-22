"""Version 2 metadata projection lifecycle with explicit annotation dispositions; opens only declared reserved XML members.

Outcome text co-resident in XML passes through the parser without extraction.
No audio, ratings, features, or model APIs are available in this module.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile
from contextlib import contextmanager

SAFE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
SOURCES = {'stage':'metadata_stage_v2.py','projection':'structural_projection_v2.py','selection':'select.py'}
SOURCE_PATHS = {key:Path(__file__).with_name(name).resolve() for key,name in SOURCES.items()}
SOURCE_PATHS['historicalEligibility'] = Path(__file__).resolve().parents[3]/'work/percept-r-check-20260930/reviewed-v1/tokens.py'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def read_bound_json(binding):
    data=Path(binding['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=binding['sha256']: raise ValueError('binding_changed')
    return json.loads(data)


def _file_identity(stat):
    return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


@contextmanager
def bound_archive(binding):
    path=Path(binding['path'])
    with path.open('rb') as stream:
        original=_file_identity(os.fstat(stream.fileno()))
        def check():
            if _file_identity(path.stat())!=original or _file_identity(os.fstat(stream.fileno()))!=original:
                raise ValueError('archive_changed')
            stream.seek(0); h=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
            if h.hexdigest()!=binding['sha256']: raise ValueError('archive_changed')
            if _file_identity(path.stat())!=original or _file_identity(os.fstat(stream.fileno()))!=original:
                raise ValueError('archive_changed')
            stream.seek(0)
        check()
        with zipfile.ZipFile(stream) as archive:
            yield archive
        check()


def save(path,value):
    data=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest()


def verify(bindings,keys):
    if type(bindings) is not dict or set(bindings)!=set(keys): raise ValueError('invalid_binding_set')
    for binding in bindings.values():
        if not isinstance(binding,dict) or not {'path','sha256'} <= set(binding): raise ValueError('invalid_binding')
        if not re.fullmatch('[0-9a-f]{64}',binding['sha256']) or digest(binding['path'])!=binding['sha256']: raise ValueError('binding_changed')


def verify_sources(bindings):
    verify(bindings,SOURCE_PATHS)
    for key,path in SOURCE_PATHS.items():
        if Path(bindings[key]['path']).resolve()!=path: raise ValueError('wrong_source')


def metadata_inventory(split,inventory,names,expected_children=80):
    """Validate complete reserved roster/inventory against ZIP central directory."""
    children=split['test']; folders=split['folders']['test']
    if len(children)!=expected_children or len(set(children))!=len(children) or any(not isinstance(c,str) or not re.fullmatch('[1-9][0-9]*',c) for c in children): raise ValueError('invalid_reserved_roster')
    if set(children)&set(split['dev']): raise ValueError('split_overlap')
    if len(set(folders))!=len(folders) or set(folders)&set(split['folders']['dev']): raise ValueError('folder_overlap')
    if any(not SAFE.fullmatch(f) or f.rsplit('_',1)[-1] not in children for f in folders): raise ValueError('invalid_folder')
    if {f.rsplit('_',1)[-1] for f in folders}!=set(children): raise ValueError('incomplete_child_folders')
    if not set(folders)<=set(inventory['folders']) or not set(folders)<=set(inventory['sessions']): raise ValueError('missing_inventory_folder')
    expected=[]
    for folder in sorted(folders):
        for row in inventory['sessions'][folder]:
            session=row['session']
            if not isinstance(session,str) or not SAFE.fullmatch(session): raise ValueError('invalid_session')
            expected.append(f'0phon/{folder}/{session}.xml')
    if len(set(expected))!=len(expected) or len(expected)!=split['sessions']['test']: raise ValueError('session_count_differs')
    if len(set(names))!=len(names): raise ValueError('duplicate_archive_member')
    if any(n.startswith('/') or '\\' in n or '..' in n.split('/') for n in names): raise ValueError('unsafe_archive_member')
    actual={n for n in names if n.endswith('.xml') and len(n.split('/'))>=3 and n.split('/')[0]=='0phon' and n.split('/')[1] in folders}
    if actual!=set(expected): raise ValueError('archive_session_set_differs')
    return sorted(expected)


def declare_metadata(bindings,source_bindings,fresh_root,expected_children=80):
    verify(bindings,{'archive','split','sessions'}); verify_sources(source_bindings)
    split=read_bound_json(bindings['split']); inventory=read_bound_json(bindings['sessions'])
    with bound_archive(bindings['archive']) as z:
        names=metadata_inventory(split,inventory,z.namelist(),expected_children)
        if any(z.getinfo(n).file_size>16*1024*1024 or z.getinfo(n).flag_bits&1 for n in names): raise ValueError('unsupported_archive_entry')
    verify_sources(source_bindings)
    root=Path(fresh_root); root.mkdir(mode=0o700)
    declaration={'schemaVersion':1,'status':'declared_metadata_projection_before_XML_read','inputBindings':bindings,'sourceBindings':source_bindings,'expectedChildren':expected_children,'members':names,'children':sorted(split['test']),'researchOnly':True,'testAudioAllowed':False,'outcomeExtractionAllowed':False,'metadataVersion':2,'annotationEligibility':'Resolved nonempty ARPABET Target rows only; absent or valid empty target annotations are explicitly ineligible before cap, as frozen historical source.'}
    sha=save(root/'declaration.json',declaration)
    return {'path':str(root/'declaration.json'),'sha256':sha}


def run_metadata(root,declaration_sha):
    root=Path(root)
    declaration=read_bound_json({'path':str(root/'declaration.json'),'sha256':declaration_sha})
    phase=root/'projection'; phase.mkdir(mode=0o700)
    save(phase/'started.json',{'declarationSha256':declaration_sha,'status':'started_terminal_attempt'})
    try:
        bindings=declaration['inputBindings']; verify(bindings,{'archive','split','sessions'}); verify_sources(declaration['sourceBindings'])
        from .structural_projection_v2 import project_session
        from .select import prepare_selection
        split=read_bound_json(bindings['split']); inventory=read_bound_json(bindings['sessions'])
        tokens=[]; sessions=[]; opened=[]
        with bound_archive(bindings['archive']) as z:
            members=metadata_inventory(split,inventory,z.namelist(),declaration['expectedChildren'])
            if members!=declaration['members'] or sorted(split['test'])!=declaration['children']: raise ValueError('declaration_inventory_differs')
            for name in members:
                _,folder,leaf=name.split('/'); session=leaf[:-4]
                with z.open(name) as stream: projection=project_session(stream,folder,session)
                opened.append(name)
                sessions.append({'member':name,'ageYears':projection['ageYears'],'recordCount':len(projection['records'])})
                for row in projection['records']:
                    tokens.append({'childId':folder.rsplit('_',1)[-1],'tokenId':'/'.join((folder,session,row['recordId'])),'folder':folder,'session':session,'recordId':row['recordId'],'ageYears':projection['ageYears'],'startSeconds':row['startSeconds'],'endSeconds':row['endSeconds'],'phones':row['phones'],'targetMetadataStatus':row['targetMetadataStatus']})
        verify_sources(declaration['sourceBindings'])
        payload={'children':[{'childId':c} for c in declaration['children']],'tokens':tokens}
        known=[{k:v for k,v in row.items() if k!='targetMetadataStatus'} for row in tokens if row['targetMetadataStatus']=='resolved' and row['phones']]
        unannotated=[row for row in tokens if row['targetMetadataStatus'] in ('missing_target_tier','empty_target_tier')]
        if len(known)+len(unannotated)!=len(tokens): raise ValueError('unreconciled_annotation')
        child_counts=[]
        for child in declaration['children']:
            rows=[r for r in tokens if r['childId']==child]
            child_counts.append({'childId':child,'structuralRecords':len(rows),'selectorInputRecords':sum(r['targetMetadataStatus']=='resolved' for r in rows),'annotationIneligibleRecords':sum(r['targetMetadataStatus']!='resolved' for r in rows),'missingTargetTierRecords':sum(r['targetMetadataStatus']=='missing_target_tier' for r in rows),'emptyTargetTierRecords':sum(r['targetMetadataStatus']=='empty_target_tier' for r in rows)})
        totals={k:sum(row[k] for row in child_counts) for k in ('structuralRecords','selectorInputRecords','annotationIneligibleRecords','missingTargetTierRecords','emptyTargetTierRecords')}
        selector_payload={'children':payload['children'],'tokens':known}
        selection=prepare_selection(selector_payload)
        payload_sha=save(phase/'structural-input.json',payload)
        selector_sha=save(phase/'selection-input.json',selector_payload)
        selection_sha=save(phase/'selection.json',selection)
        receipt={'schemaVersion':1,'status':'verified_structural_projection_selection','declarationSha256':declaration_sha,'payloadSha256':payload_sha,'selectionSha256':selection_sha,'selectedMembershipSha256':selection['selectedMembershipSha256'],'openedMembers':opened,'sessions':sessions,'counts':selection['counts'],'selectorInputSha256':selector_sha,'recordReconciliation':{'totals':totals,'children':child_counts,'annotationIneligibleTokenIds':[r['tokenId'] for r in unannotated]},'testStructuralMetadataRead':True,'outcomeFieldsCoResidentInStreamedXML':True,'testOutcomeValuesExtracted':False,'testOutcomeValuesInterpreted':False,'testOutcomeValuesRetained':False,'testOutcomeValuesLogged':False,'testOutcomeValuesExposed':False,'testAudioMembersOpened':False,'testAudioDecoded':False,'modelInferencePerformed':False,'limitations':['Co-resident outcome bytes necessarily streamed through Expat; no outcome values extracted.','Numeric IDs do not establish biological independence.','No reserved outcomes, accuracy, or learner feedback verified.']}
        receipt_sha=save(phase/'receipt.json',receipt)
        return {'selectionPath':str(phase/'selection.json'),'selectionSha256':selection_sha,'receiptPath':str(phase/'receipt.json'),'receiptSha256':receipt_sha}
    except Exception:
        save(phase/'failure.json',{'status':'failed_terminal_attempt','errorCode':'metadata_execution_failed','declarationSha256':declaration_sha})
        raise ValueError('metadata_execution_failed') from None
