"""Declare and run known licensed/reference challenges; retain all attempts."""
import array,hashlib,io,json,math,os,random,stat,time,wave
from collections import Counter
from pathlib import Path
from .adapter import recognize,assess,declaration
from .models import ROOT,private_read
from .policy import AdmissionError,CLAIMS,POLICY,canonical,digest,decide
from reference_assets import validate_registry
from consumer_assessment import bridge

SOURCE=ROOT/'work/assessment-real-data-20261004'

def write(path,value):
    path=Path(path)
    info=path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise AdmissionError('unsafe_output_directory')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        data=canonical(value)+b'\n'
        while data:
            count=os.write(fd,data);data=data[count:]
        os.fsync(fd)
    finally:os.close(fd)

def pcm(samples):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as out:
        out.setparams((1,2,16000,len(samples),'NONE','not compressed'));out.writeframes(array.array('h',samples).tobytes())
    return buffer.getvalue()

def frames(raw):
    with wave.open(io.BytesIO(raw),'rb') as source:return array.array('h',source.readframes(source.getnframes()))

def prompt_for(decision):
    variant=decision['preferredVariantId'];index=decision['chosenOccurrenceIndexByVariant'][variant]
    return {'schemaVersion':2,'language':'en','transcript':decision['word'],
            'words':[{'text':decision['word'],'phones':decision['phonesByVariant'][variant]}],
            'targets':[{'id':decision['promptId']+'-index-'+str(index),'wordIndex':0,'phoneIndex':index,'targetPhone':decision['targetPhone']}]}

def inputs():
    registry_raw=private_read(SOURCE/'references/assets.json',8000000)
    registry=json.loads(registry_raw);validate_registry(registry,require_complete=True)
    pack_raw=private_read(SOURCE/'engineering-pack.json',8000000);pack=json.loads(pack_raw)
    decisions={}
    for item in pack['prompts']:decisions.setdefault(item['decision']['sourceWord'],item['decision'])
    assets={asset['sourceWord']:asset for asset in registry['assets']}
    if set(assets)!=set(decisions) or len(assets)!=13:raise AdmissionError('reference_set_changed')
    audio={}
    for word,asset in sorted(assets.items()):
        raw=private_read(asset['wavPath'],132096)
        if hashlib.sha256(raw).hexdigest()!=asset['wavSha256']:raise AdmissionError('source_audio_changed')
        audio[word]=raw
    generated={'silence':pcm([0]*16000),'tone':pcm([round(1000*math.sin(2*math.pi*220*i/16000)) for i in range(19200)]),
               'noise':pcm([random.Random(20261004+i).randint(-1800,1800) for i in range(16000)]),
               'clipping':pcm([32767]+[0]*15999),'malformed':b'not-a-WAV'}
    cases=[];blobs={}
    for word in sorted(audio):
        cid='original-'+word;blobs[cid]=audio[word]
        cases.append({'caseId':cid,'kind':'original','expectedWord':word,'prompt':prompt_for(decisions[word]),'sources':[word]})
    words=sorted(audio)
    for index,word in enumerate(words):
        following=words[(index+1)%len(words)];cid='concatenated-'+word+'-'+following
        blobs[cid]=pcm(list(frames(audio[word]))+[0]*1600+list(frames(audio[following])))
        cases.append({'caseId':cid,'kind':'concatenated','expectedWord':word,'prompt':prompt_for(decisions[word]),'sources':[word,following]})
    for kind,raw in generated.items():
        cid='generated-'+kind;blobs[cid]=raw
        cases.append({'caseId':cid,'kind':'generated','expectedWord':'rabbit','prompt':prompt_for(decisions['rabbit']),'sources':[]})
    for word in ('rabbit','banana'):
        cid='replicate-'+word;blobs[cid]=audio[word]
        cases.append({'caseId':cid,'kind':'replicate','expectedWord':word,'prompt':prompt_for(decisions[word]),'sources':[word]})
    for case in cases:
        case['audioSha256']=hashlib.sha256(blobs[case['caseId']]).hexdigest()
        case['promptSha256']=hashlib.sha256(bridge.canonical_bytes(case['prompt'])).hexdigest()
    source={'referenceRegistrySha256':hashlib.sha256(registry_raw).hexdigest(),'engineeringPackSha256':hashlib.sha256(pack_raw).hexdigest(),
            'attributions':[{'sourceWord':a['sourceWord'],'author':a['author'],'licenseId':a['licenseId'],
              'sourcePageUrl':a['sourcePageUrl'],'licenseUrl':a['licenseUrl'],'wavSha256':a['wavSha256']} for a in registry['assets']]}
    return cases,blobs,source

def prepare_plan():
    cases,_,source=inputs();binding=declaration()
    if not binding['ready']:raise AdmissionError('model_unavailable')
    return {'schemaVersion':1,'kind':'known-reference-admission-challenges','policy':POLICY,'declaration':binding,
            'source':source,'runnerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'harnessAgeYears':9,'actualSpeakerAge':'unknown','fittingOrTuningAllowed':False,
            'cases':cases,'denominators':{'uniqueOriginalClips':13,'derivedClips':18,'exactByteReplicates':2,
              'acousticAttempts':33,'crossWordComparisons':169,'admissionAttempts':33},'claimLimits':dict(CLAIMS)}

def run_plan(plan,expected_sha,new_root):
    if digest(plan)!=expected_sha or digest(prepare_plan())!=expected_sha:raise AdmissionError('plan_changed')
    _,blobs,_=inputs()
    root=Path(new_root);root.mkdir(mode=0o700)
    write(root/'plan.json',plan);rows=[];evidence_by_word={};bridge_calls=[]
    for number,case in enumerate(plan['cases'],1):
        cid=case['caseId'];raw=blobs[cid]
        binding={'caseId':cid,'attemptNumber':number,'audioSha256':case['audioSha256'],'planSha256':expected_sha,
                 'modelManifestSha256':plan['declaration']['modelManifestSha256'],'policySha256':plan['declaration']['policySha256']}
        write(root/('%02d-started.json'%number),binding)
        started=time.monotonic()
        try:evidence=recognize(raw)
        except Exception as error:
            write(root/('%02d-terminal.json'%number),{**binding,'status':'unavailable','reason':'unexpected_runner_failure','elapsedSeconds':time.monotonic()-started})
            raise AdmissionError('run_incomplete') from None
        write(root/('%02d-recognition.json'%number),evidence)
        def traced_bridge(request):
            call_number=len(bridge_calls)+1;request_sha=hashlib.sha256(request).hexdigest()
            write(root/('bridge-%02d-started.json'%call_number),{**binding,'requestSha256':request_sha,
                  'evidenceSha256':evidence['evidenceSha256'],'promptSha256':case['promptSha256']})
            begin=time.monotonic();response=bridge.assess(request)
            trace={**binding,'requestSha256':request_sha,'response':response,'elapsedSeconds':time.monotonic()-begin}
            write(root/('bridge-%02d-terminal.json'%call_number),trace);bridge_calls.append(trace)
            return response
        result=assess(raw,case['prompt'],recognition_evidence=evidence,research_bridge=traced_bridge)
        row={**binding,'kind':case['kind'],'expectedWord':case['expectedWord'],'recognitionEvidenceSha256':evidence['evidenceSha256'],
             'elapsedSeconds':time.monotonic()-started,'recognitionRuntime':evidence['runtime'],'result':result}
        write(root/('%02d-terminal.json'%number),row);rows.append(row)
        if case['kind']=='original':evidence_by_word[case['expectedWord']]=evidence
    comparisons=[{'sourceWord':source,'expectedWord':expected,'decision':decide(evidence,expected)}
                 for source,evidence in sorted(evidence_by_word.items()) for expected in sorted(evidence_by_word)]
    write(root/'cross-word-comparisons.json',comparisons)
    replicas=[]
    for word in ('rabbit','banana'):
        original=evidence_by_word[word]
        number=next(i for i,c in enumerate(plan['cases'],1) if c['caseId']=='replicate-'+word)
        repeated=json.loads(private_read(root/('%02d-recognition.json'%number),100000))
        keys=('status','reason','capture','speechEvidence','recognition','binding','claimLimits')
        replicas.append({'sourceWord':word,'sameExactAudioSha256':original['binding']['audioSha256']==repeated['binding']['audioSha256'],
                         'sameAcousticEvidenceExceptRuntime':digest({k:original[k] for k in keys})==digest({k:repeated[k] for k in keys}),
                         'childRepeatabilityEstablished':False})
    report={'schemaVersion':1,'planSha256':expected_sha,'denominators':plan['denominators'],
            'terminalAttempts':len(rows),'startedAttempts':len(plan['cases']),'actualAcousticWorkerCalls':sum(r['recognitionRuntime']['acousticCalls'] for r in rows),
            'actualResearchBridgeCalls':len(bridge_calls),'processed':sum(r['result']['status']=='processed' for r in rows),
            'unavailableReasons':dict(Counter(r['result']['reason'] for r in rows if r['result']['status']=='unavailable')),
            'crossWordAdmitted':sum(c['decision']['admitted'] for c in comparisons),'crossWordFalseMatchProbesAdmitted':sum(c['decision']['admitted'] and c['sourceWord']!=c['expectedWord'] for c in comparisons),
            'crossWordMismatchComparisonDenominator':156,'replicates':replicas,'allAttempts':rows,
            'claimLimits':dict(CLAIMS),'meaning':'Known public source words/generated challenges, not human phonetic truth or untouched intended-child validation'}
    write(root/'report.json',report)
    return report
