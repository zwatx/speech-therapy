"""Pinned local official files; this module never acquires or executes scripts."""
import hashlib,json,os,stat
from pathlib import Path
from .policy import AdmissionError,POLICY_SHA

ROOT=Path(__file__).resolve().parents[3]
MODEL_ROOT=ROOT/'work/roadmap-completion-20261004/admission/models'
MODEL_MANIFEST_SHA='8a8054e4c434e9106e9bb625d27c3219089c7a6b643504ad893a531c3b4e6c37'

def private_read(path,maximum):
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            before=os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1 or before.st_size>maximum):raise AdmissionError('model_unavailable')
            pieces=[];left=maximum+1
            while left:
                piece=os.read(fd,min(left,1024*1024))
                if not piece:break
                pieces.append(piece);left-=len(piece)
            raw=b''.join(pieces);after=os.fstat(fd)
            if len(raw)>maximum or any(getattr(before,key)!=getattr(after,key) for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_nlink')):raise AdmissionError('model_unavailable')
            return raw
        finally:os.close(fd)
    except OSError:raise AdmissionError('model_unavailable') from None

def check_models():
    for directory in (MODEL_ROOT,MODEL_ROOT/'whisper'):
        info=directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise AdmissionError('model_unavailable')
    raw=private_read(MODEL_ROOT/'manifest.json',100000)
    if hashlib.sha256(raw).hexdigest()!=MODEL_MANIFEST_SHA:raise AdmissionError('model_unavailable')
    manifest=json.loads(raw)
    for record in manifest['files']:
        data=private_read(MODEL_ROOT/record['relativePath'],300000000)
        if len(data)!=record['bytes'] or hashlib.sha256(data).hexdigest()!=record['sha256']:raise AdmissionError('model_unavailable')
    return manifest

def readiness():
    try:check_models();ready=True
    except (AdmissionError,OSError,ValueError,KeyError):ready=False
    return {'ready':ready,'reason':None if ready else 'model_unavailable','policySha256':POLICY_SHA,
            'modelManifestSha256':MODEL_MANIFEST_SHA,'asrModel':'openai/whisper-base.en',
            'asrRevision':'911407f4214e0e1d82085af863093ec0b66f9cd6','vadModel':'snakers4/silero-vad',
            'vadRevision':'1e261b036686cd0017d500ee96acd1c4ba572a9d','networkRequiredForInference':False}
