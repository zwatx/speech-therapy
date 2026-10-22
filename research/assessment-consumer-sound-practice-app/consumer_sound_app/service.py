"""One shared heavy-job owner, bounded capture tombstones and explicit cancellation."""
from copy import deepcopy
import os
from pathlib import Path
import stat
import threading
import uuid
from mobile_admission.service import block
from . import contract as c

class SoundService:
    def __init__(self,executor,catalog,worker,observer,source_check,*,csrf_token):
        self.executor,self.catalog,self.worker,self.observer=executor,catalog,worker,observer
        self.source_check=source_check;self.csrf_token=csrf_token;self.nonce=str(uuid.uuid4())
        self.initial=source_check();self.lock=threading.Lock();self.contexts={};self.captures=set();self.attempts=set();self.active=None;self.job_epoch=0
        if self._phone_blocked():self.executor.mark_blocked()
    def _phone_blocked(self):
        with self.lock:
            if self.active is not None:return False
            epoch=self.job_epoch
        try:
            evidence=getattr(self.observer,'latched',False) is not False or any(path.name!='last-supervision.json' for path in Path(self.observer.runtime_dir).iterdir())
        except OSError:evidence=True
        with self.lock:
            return evidence and self.active is None and self.job_epoch==epoch
    def declaration(self):
        if self._phone_blocked():self.executor.mark_blocked()
        available=not self.executor.is_blocked()
        try:c.need(c.canonical(self.source_check())==c.canonical(self.initial),'source_binding_failed')
        except (OSError,ValueError):available=False
        return c.validate_declaration({'schemaVersion':1,'kind':c.KIND,'purpose':c.PURPOSE,'serverNonce':self.nonce,
            'csrfToken':self.csrf_token,'binding':deepcopy(self.initial),'policy':deepcopy(c.POLICY),
            'processingAvailable':available,'claimLimits':dict(c.CLAIMS)})
    def _current(self,owner):
        with self.lock:return self.contexts.get(owner['sessionId'])==(owner['generation'],owner['contextSha256'])
    def reset(self,raw):
        value=c.strict_json(raw)
        c.need(c.exact(value,('schemaVersion','serverNonce','sessionId','generation')) and type(value['schemaVersion']) is int and value['schemaVersion']==1
            and value['serverNonce']==self.nonce and type(value['sessionId']) is str and 1<=len(value['sessionId'])<=64
            and all(char.isascii() and (char.isalnum() or char in '-_') for char in value['sessionId'])
            and type(value['generation']) is int and 1<=value['generation']<=2147483647)
        with self.lock:
            session=value['sessionId'];previous=self.contexts.get(session)
            c.need(previous is None or value['generation']>previous[0],'stale_ownership')
            c.need(session in self.contexts or len(self.contexts)<8,'context_limit')
            self.contexts[session]=(value['generation'],None)
            if self.active and self.active[0]['sessionId']==session:self.active[1].set()
        return {'schemaVersion':1,'resetAccepted':True,'serverNonce':self.nonce,'sessionId':session,'generation':value['generation']}
    def cancel(self,raw):
        value=c.strict_json(raw)
        c.need(c.exact(value,('schemaVersion','serverNonce','attemptId','requestSha256','ownership'))
            and type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['serverNonce']==self.nonce
            and c.uuid(value['attemptId']) and c.hex64(value['requestSha256']) and self.worker.valid_owner(value['ownership']))
        accepted=False
        with self.lock:
            if self.active:
                owner,event,expected=self.active
                if c.canonical(owner)==c.canonical(value['ownership']) and value['attemptId']==expected['attemptId'] and value['requestSha256']==expected['requestSha256']:
                    event.set();accepted=True
        return {'schemaVersion':1,'cancelAccepted':accepted,'serverNonce':self.nonce,'attemptId':value['attemptId'],'requestSha256':value['requestSha256']}
    def _claim(self,request):
        owner=request['ownership'];session=owner['sessionId'];capture=owner['captureId'];attempt=request['attemptId']
        with self.lock:
            if capture in self.captures:return 'capture_already_checked'
            if attempt in self.attempts:return 'attempt_already_checked'
            if len(self.captures)>=128:return 'attempt_limit'
            previous=self.contexts.get(session)
            if previous and (owner['generation']<previous[0] or (owner['generation']==previous[0] and previous[1] not in (None,owner['contextSha256']))):return 'stale_ownership'
            if previous is None and len(self.contexts)>=8:return 'context_limit'
            self.contexts[session]=(owner['generation'],owner['contextSha256'])
            self.captures.add(capture);self.attempts.add(attempt)
        return None
    def _diagnostic(self,outcome,private):
        reference=outcome.get('supervisionDiagnostic');c.need(c.exact(reference,('path','sha256','requestSha256')),'invalid_evidence')
        # Exact owned observer path; never open an output-provided arbitrary path or symlink.
        path=Path(self.observer.runtime_dir)/'last-supervision.json'
        c.need(reference['path']==str(path),'invalid_evidence')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd);c.need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and 0<info.st_size<=65536,'invalid_evidence')
            raw=os.read(fd,65537);c.need(len(raw)==info.st_size and c.sha(raw)==reference['sha256'],'invalid_evidence')
        finally:os.close(fd)
        c.need((info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(path.lstat().st_dev,path.lstat().st_ino,path.lstat().st_size,path.lstat().st_mtime_ns,path.lstat().st_ctime_ns),'invalid_evidence')
        request_hash=self.worker.digest(self.worker.canonical(private).encode());c.need(reference['requestSha256']==request_hash,'invalid_evidence')
        diagnostic=c.strict_json(raw);self.worker.validate_supervision_diagnostic(diagnostic,private,request_hash)
        return diagnostic
    def _create_intent(self,state):
        path=self.executor.runtime/'cleanup-required'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            info=os.fstat(fd);state['identity']=(info.st_dev,info.st_ino)
            os.write(fd,b'phone cleanup required\n');os.fsync(fd)
        finally:os.close(fd)
        fd=os.open(self.executor.runtime,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def _remove_intent(self,state):
        path=self.executor.runtime/'cleanup-required';info=path.lstat()
        c.need((info.st_dev,info.st_ino)==state['identity'] and stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
            and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'cleanup_unconfirmed')
        path.unlink();fd=os.open(self.executor.runtime,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def _run(self,request,audio,private,expected,cancel,state):
        owner=request['ownership']
        if self.executor.is_blocked():return c.response(expected,'unavailable','processing_unavailable')
        if not self._current(owner):return c.response(expected,'unavailable','stale_ownership')
        if c.canonical(self.source_check())!=c.canonical(self.initial):return c.response(expected,'unavailable','source_binding_failed')
        self._create_intent(state)
        with self.lock:
            self.job_epoch+=1
            self.active=(deepcopy(owner),cancel,deepcopy(expected))
            if self.contexts.get(owner['sessionId'])!=(owner['generation'],owner['contextSha256']):cancel.set()
        state['cleaned']=False
        outcome=self.observer.observe(audio,owner,is_current=self._current,cancellation_event=cancel)
        c.need(type(outcome) is dict and type(outcome.get('cleanupConfirmed')) is bool,'invalid_evidence')
        if outcome['cleanupConfirmed'] is not True:return c.response(expected,'unavailable','cleanup_unconfirmed')
        # Provided recovery evidence must agree before either owner intent may be released.
        diagnostic=None
        if 'supervisionDiagnostic' in outcome:
            diagnostic=self._diagnostic(outcome,private)
            if diagnostic['cleanupConfirmed'] is not True:return c.response(expected,'unavailable','cleanup_unconfirmed')
        state['cleaned']=True
        if cancel.is_set() or not self._current(owner):return c.response(expected,'unavailable','cancelled')
        if c.canonical(self.source_check())!=c.canonical(self.initial):return c.response(expected,'unavailable','source_binding_failed')
        if outcome.get('status')=='observed':return c.project_worker(outcome,private,expected,self.worker,diagnostic)
        c.need(outcome.get('status')=='unavailable' and c.false_claims(outcome.get('claimLimits')) and outcome.get('inferenceCalls') is None,'invalid_evidence')
        reason=outcome.get('reason');return c.response(expected,'unavailable',reason if reason in ('cancelled','timeout','stale_ownership') else 'worker_unavailable')
    def execute(self,raw):
        request,audio,private,expected,supported=c.prepare(raw,self.declaration(),self.worker,self.catalog)
        if not supported:return c.response(expected,'unsupported','unsupported_prompt')
        refusal=self._claim(request)
        if refusal:return c.response(expected,'unavailable',refusal)
        if not self.executor.slot.acquire(blocking=False):return c.response(expected,'unavailable','busy')
        state={'identity':None,'cleaned':True};cancel=threading.Event();result=None
        try:
            try:result=self._run(request,audio,private,expected,cancel,state)
            except (OSError,ValueError,TypeError,KeyError):result=c.response(expected,'unavailable','invalid_evidence' if state['cleaned'] else 'cleanup_unconfirmed')
            finally:
                if state['identity'] is not None:
                    if state['cleaned']:
                        try:self._remove_intent(state)
                        except (OSError,ValueError):state['cleaned']=False
                    if not state['cleaned']:
                        self.executor.mark_blocked();result=c.response(expected,'unavailable','cleanup_unconfirmed')
            # Keep active identity and exclusive slot through intent unlink/fsync and these final guards.
            with self.lock:
                if cancel.is_set() or self.contexts.get(request['ownership']['sessionId'])!=(request['ownership']['generation'],request['ownership']['contextSha256']):
                    if not self.executor.is_blocked():result=c.response(expected,'unavailable','cancelled')
                elif c.canonical(self.source_check())!=c.canonical(self.initial):
                    if not self.executor.is_blocked():result=c.response(expected,'unavailable','source_binding_failed')
                return result
        except (OSError,ValueError,TypeError,KeyError):return c.response(expected,'unavailable','source_binding_failed')
        finally:
            with self.lock:self.active=None
            self.executor.slot.release()
