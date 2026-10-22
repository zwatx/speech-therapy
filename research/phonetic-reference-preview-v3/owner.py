"""Root-admitted one cold subprocess owner; no execution at import/construction."""
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import types


def verified_module(name, raw, expected, injected=None):
    if type(raw) is not bytes or len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
        raise ValueError('sourceChanged')
    module = types.ModuleType(name)
    if injected:
        module.__dict__.update(injected)
    exec(compile(raw,'<verified:'+name+'>','exec',dont_inherit=True),module.__dict__)
    return module


def ancestors(path):
    path = Path(os.path.abspath(path))
    out = []
    for parent in reversed((path.parent, *path.parent.parents)):
        info = os.lstat(parent)
        if not stat.S_ISDIR(info.st_mode): raise ValueError('unsafeParent')
        out.append((parent, info.st_dev, info.st_ino))
    return out


def verify_ancestors(chain):
    for path, dev, ino in chain:
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (dev, ino):
            raise ValueError('ancestorChanged')


def same_file(a, b):
    return all(getattr(a, k) == getattr(b, k) for k in
               ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_nlink'))


def read_regular(path, maximum, expected=None, deadline=None):
    path = Path(os.path.abspath(path))
    chain = ancestors(path)
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise ValueError('unsafeFile')
        raw, digest, count = [],hashlib.sha256(),0
        while True:
            if deadline is not None and time.monotonic() >= deadline: raise ValueError('integrityDeadline')
            block = os.read(fd,1024*1024)
            if not block: break
            count += len(block)
            if count > maximum: raise ValueError('fileLimit')
            digest.update(block)
            if expected is None: raw.append(block)
        after = os.fstat(fd)
        verify_ancestors(chain)
        leaf = os.lstat(path)
        if not stat.S_ISREG(leaf.st_mode) or not same_file(before,after) or not same_file(after,leaf):
            raise ValueError('fileChanged')
        identity = dict(bytes=count,sha256=digest.hexdigest())
        if expected is not None and identity != {'bytes':expected['bytes'],'sha256':expected['sha256']}:
            raise ValueError('identityChanged')
        return b''.join(raw),before,identity
    finally:
        os.close(fd)


def exclusive(path, raw):
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(raw);stream.flush();os.fsync(fd)
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o600: raise ValueError('privatePermissions')
        return info
    finally:
        os.close(fd)


def json_bytes(value):
    return (json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode()


def snapshot_mappings(root, bindings):
    """Closed loader namespace and five exact links under stable ancestors."""
    snapshot = root/bindings['snapshot']
    chain = ancestors(snapshot/'sentinel')
    if sorted(x.name for x in snapshot.iterdir()) != sorted(Path(row['path']).name for row in bindings['assets']):
        raise ValueError('snapshotNamespace')
    for row in bindings['assets']:
        path,resolved = root/row['path'],root/row['resolvedPath']
        if path.parent != snapshot or not path.is_symlink() or os.readlink(path) != row['linkTarget'] or path.resolve() != resolved:
            raise ValueError('snapshotMapping')
    verify_ancestors(chain)


def preflight(root, here, source_sha, bindings_sha, deadline=None, system=None):
    """Root-only actual assembly: full runtime/assets hashed before child startup."""
    raw,_,source_pin = read_regular(here/'SOURCE-v3.json',2000000,deadline=deadline)
    if source_pin['sha256'] != source_sha: raise ValueError('sourceChanged')
    source = json.loads(raw)
    buffers = {}
    for row in source['files']:
        name = row['path']
        if Path(name).is_absolute() or '..' in Path(name).parts: raise ValueError('sourcePath')
        payload,_,identity = read_regular(here/name,2000000,deadline=deadline)
        if identity != {'bytes':row['bytes'],'sha256':row['sha256']}: raise ValueError('sourceChanged')
        buffers[name] = payload
    bindings = json.loads(buffers['BINDINGS-v3.json'])
    if hashlib.sha256(buffers['BINDINGS-v3.json']).hexdigest() != bindings_sha: raise ValueError('bindingsChanged')
    read_regular(Path(bindings['python']),1000000,bindings['python_pin'],deadline=deadline)
    runtime_raw,_,runtime_pin = read_regular(root/bindings['runtime_manifest']['path'],20000000,deadline=deadline)
    if runtime_pin != {k:bindings['runtime_manifest'][k] for k in ('bytes','sha256')}: raise ValueError('runtimeChanged')
    runtime = json.loads(runtime_raw)
    if len(runtime['files']) != 27713 or len(runtime['inventory']) != 27695 or len(runtime['records']) != 31: raise ValueError('runtimeCounts')
    for row in runtime['files']:
        read_regular(root/row['path'],2000000000,row,deadline=deadline)
    # Inventory is names, while files additionally records observed generated code.
    base = root/bindings['site_packages']
    inventory = []
    for path in base.rglob('*'):
        if deadline is not None and time.monotonic() >= deadline: raise ValueError('integrityDeadline')
        if path.is_file(): inventory.append(str(path.relative_to(root)))
    inventory.sort()
    if inventory != sorted(runtime['inventory']): raise ValueError('runtimeInventory')
    if len(bindings['assets']) != 5: raise ValueError('assetCount')
    snapshot_mappings(root,bindings)
    if system is None or system['writerPolicy'] != 'SerializedTrustedWritersV3': raise ValueError('systemBoundary')
    read_regular(Path('/bin/ps'),10000000,system['psPin'],deadline=deadline)
    # Root separately reads/reviews the installed-system attestation. This is
    # explicitly a trusted installed-system boundary, not a closure hash claim.
    raw,_,pin = read_regular(root/system['attestation']['path'],2000000,deadline=deadline)
    if pin != {k:system['attestation'][k] for k in ('bytes','sha256')}: raise ValueError('systemBoundary')
    record = json.loads(raw)
    if (set(record) != {'schema','interpreterStartupAndStdlib','dynamicLibraries','processInspectionTool',
                        'trustedSerializedWriters','psPin','pythonPin'} or record.get('schema') != 'ReviewedInstalledSystemBoundaryV3' or
        record.get('interpreterStartupAndStdlib') is not True or record.get('dynamicLibraries') is not True or
        record.get('processInspectionTool') is not True or record.get('trustedSerializedWriters') is not True or
        record.get('psPin') != system['psPin'] or record.get('pythonPin') != bindings['python_pin']):
        raise ValueError('systemBoundary')
    for row in bindings['assets']:
        path,resolved = root/row['path'],root/row['resolvedPath']
        if not path.is_symlink() or os.readlink(path) != row['linkTarget'] or path.resolve() != resolved: raise ValueError('snapshotMapping')
        read_regular(resolved,2000000000,row,deadline=deadline)
    snapshot_mappings(root,bindings)
    identities = dict(source=source_pin,bindings=dict(bytes=len(buffers['BINDINGS-v3.json']),sha256=bindings_sha),
                      runtime=runtime_pin,model=bindings['assets'][-1],vocabulary=bindings['assets'][3])
    return buffers,bindings,identities


BOOTSTRAP = r'''
import sys,json,hashlib,types,resource
resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152))
settings=json.loads(sys.stdin.buffer.read(200000))
sys.path.insert(0,settings['site_packages'])
def audit(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.posix_spawn','os.fork','os.forkpty'):
        raise RuntimeError('offlineWorkerDenied')
sys.addaudithook(audit)
modules={}
for name in ('contract','owner','worker'):
    raw=settings['sources'][name].encode('utf-8')
    pin=settings['pins'][name]
    if len(raw)!=pin['bytes'] or hashlib.sha256(raw).hexdigest()!=pin['sha256']: raise RuntimeError('sourceChanged')
    m=types.ModuleType(name)
    if name=='worker': m.contract=modules['contract']; m.integrity=modules['owner']
    exec(compile(raw,'<verified:'+name+'>','exec',dont_inherit=True),m.__dict__)
    modules[name]=m
modules['worker'].main(settings)
'''


class Owner:
    def __init__(self, contract, root, here, staging):
        self.contract,self.root,self.here,self.staging = contract,Path(root),Path(here),Path(staging)
        self.state = 'inactive'
        self.borrowed = None
        self.borrow_stat = None
        self.identities = None
        self.buffers = None
        self.bindings = None
        self.cancel = threading.Event()
        self.presentation_generation = 0
        self.lock = threading.Lock()
        self.process = None
        self.call_state = 'not_started'
        self.writer_lock = threading.RLock()
        self.borrow_chain = None
        self.ledger = []

    def activate(self, admission, expected_admission_sha):
        # Caller root must independently bind exact source review AND future execution job.
        c = self.contract
        c.require(self.state == 'inactive' and type(admission) is dict and
                  set(admission) == {'schema','active','source_sha','bindings_sha','review_sha','job_sha','deadline_seconds','integrity_seconds','collection_seconds','system'} and
                  admission['schema'] == 'PhoneticReferenceRootAdmissionV3' and admission['active'] is True and
                  type(admission['deadline_seconds']) is int and 1 <= admission['deadline_seconds'] <= 3600 and
                  hashlib.sha256(json_bytes(admission)).hexdigest() == expected_admission_sha and
                  all(type(admission[k]) is str and len(admission[k]) == 64 and all(x in '0123456789abcdef' for x in admission[k])
                      for k in ('source_sha','bindings_sha','review_sha','job_sha')), 'integrity')
        c.require(all(type(admission[k]) is int and 1 <= admission[k] <= 180 for k in ('integrity_seconds','collection_seconds')), 'integrity')
        system = admission['system']
        c.require(type(system) is dict and set(system) == {'psPin','attestation','writerPolicy'} and
                  system['writerPolicy'] == 'SerializedTrustedWritersV3', 'integrity')
        self.admission = admission
        self.buffers,self.bindings,self.identities = preflight(self.root,self.here,admission['source_sha'],admission['bindings_sha'],
            time.monotonic()+admission['integrity_seconds'],system)
        self.deadline_seconds = admission['deadline_seconds']
        vocab_raw,_,_ = read_regular(self.root/self.bindings['assets'][3]['resolvedPath'],10000)
        self.vocab = c.vocabulary(c.closed_json(vocab_raw))
        self.state = 'ready'

    def cancel_presentation(self):
        self.presentation_generation += 1
        self.cancel.set()

    def _read_response(self, envelope):
        raw,info,_ = read_regular(self.staging/'RESPONSE.json',200000,deadline=self.collection_deadline)
        self.contract.require(stat.S_IMODE(info.st_mode) == 0o600,'malformed_output')
        value = self.contract.response(self.contract.closed_json(raw),envelope,self.identities)
        self.contract.require(value['terminal_owner'] is False,'malformed_output')
        for name,identity in value['artifacts'].items():
            _,info,_ = read_regular(self.staging/name,self.contract.ARTIFACTS[name],identity,deadline=self.collection_deadline)
            self.contract.require(stat.S_IMODE(info.st_mode) == 0o600,'malformed_output')
        if value['kind'] == 'model_hypothesis':
            hypothesis,_,_ = read_regular(self.staging/'hypothesis.json',100000,deadline=self.collection_deadline)
            loading,_,_ = read_regular(self.staging/'loading.json',200000,deadline=self.collection_deadline)
            logits,_,_ = read_regular(self.staging/'logits.f32',self.contract.ARTIFACTS['logits.f32'],deadline=self.collection_deadline)
            normalized,_,_ = read_regular(self.staging/'normalized.f32',self.contract.ARTIFACTS['normalized.f32'],deadline=self.collection_deadline)
            for name,payload in (('logits.f32',logits),('normalized.f32',normalized),('hypothesis.json',hypothesis),('loading.json',loading)):
                self.contract.require(self.contract.pin(payload) == value['artifacts'][name],'malformed_output')
            collection = self.contract.collect(logits,normalized,self.contract.closed_json(hypothesis),
                self.contract.closed_json(loading),self.vocab,envelope['sample_count'],self.collection_deadline)
            exclusive(self.staging/'COLLECTION.json',json_bytes(dict(request=envelope,identities=self.identities,artifacts=value['artifacts'],verification=collection)))
        return value

    def _call_state(self, envelope):
        path = self.staging/'CALL-COMMITTED.json'
        if not os.path.lexists(path): return 'not_started'
        raw,info,_ = read_regular(path,10000)
        self.contract.require(stat.S_IMODE(info.st_mode) == 0o600,'malformed_output')
        self.contract.require(self.contract.closed_json(raw) == dict(request=envelope,model_call_state='invocation_committed'),'malformed_output')
        completed = self.staging/'CALL-COMPLETED.json'
        if os.path.lexists(completed):
            raw,info,_ = read_regular(completed,10000)
            self.contract.require(stat.S_IMODE(info.st_mode) == 0o600,'malformed_output')
            self.contract.require(self.contract.closed_json(raw) == dict(request=envelope,model_call_state='completed'),'malformed_output')
            return 'completed'
        return 'invocation_committed'

    def _phase(self):
        phase = 'unknown'
        for candidate in ('input','loading','extractor','forward','decode','persist'):
            path = self.staging/('PHASE-'+candidate+'.json')
            if os.path.lexists(path):
                raw,info,_ = read_regular(path,1000)
                self.contract.require(stat.S_IMODE(info.st_mode) == 0o600,'malformed_output')
                self.contract.require(self.contract.closed_json(raw) == {'phase':candidate},'malformed_output')
                phase = candidate
        return phase

    def _guard(self, deadline=None):
        admission = self.admission
        preflight(self.root,self.here,admission['source_sha'],admission['bindings_sha'],
                  min(deadline,time.monotonic()+admission['integrity_seconds']) if deadline is not None else time.monotonic()+admission['integrity_seconds'],admission['system'])

    def _delete_borrow(self, envelope):
        # ALL input/directory writers must honor this root-owned serialized
        # protocol. Worker never writes/renames input.wav or ancestors. External
        # uncooperative writers are outside the reviewed installed-system boundary.
        with self.writer_lock:
            verify_ancestors(self.borrow_chain)
            _,current,_ = read_regular(self.borrowed,self.contract.MAX_WAV,envelope['wav_identity'])
            self.contract.require(stat.S_IMODE(current.st_mode) == 0o600 and same_file(current,self.borrow_stat),'cleanup_unknown')
            fd = os.open(self.staging,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                self.contract.require((info.st_dev,info.st_ino) == self.borrow_chain[-1][1:],'cleanup_unknown')
                leaf = os.stat(self.borrowed.name,dir_fd=fd,follow_symlinks=False)
                self.contract.require(same_file(current,leaf),'cleanup_unknown')
                verify_ancestors(self.borrow_chain)
                os.unlink(self.borrowed.name,dir_fd=fd)
                os.fsync(fd)
                verify_ancestors(self.borrow_chain)
            finally:
                os.close(fd)
            self.borrowed = None

    def attempt(self, raw, envelope):
        c = self.contract
        # Invalid request has no trustworthy request identity to bind a normal result.
        try: c.request(envelope)
        except c.Rejected: return {'schema':'PhoneticReferenceEnvelopeRejectedV3','kind':'input_rejected','reason':'invalid_request','model_called':False}
        if self.state == 'inactive': return c.result('unavailable','preflight','inactive',envelope,{})
        c.require(self.lock.acquire(blocking=False),'cleanup_unknown')
        started = time.monotonic()
        try:
            if self.state == 'blocked': return c.result('cleanup_unconfirmed','cleanup','cleanup_unknown',envelope,self.identities,
                                                     None if self.call_state == 'unknown' else self.call_state != 'not_started',False,self.call_state)
            c.require(self.state == 'ready' and self.borrowed is None,'cleanup_unknown')
            if self.cancel.is_set(): return c.result('cancelled','preflight','cancelled',envelope,self.identities,False,True)
            try: c.wav_payload(raw,envelope)
            except c.Rejected as error: return c.result('input_rejected','input',error.code,envelope,self.identities,False,True)
            self._guard()
            self.staging.mkdir(mode=0o700,parents=False,exist_ok=False)
            c.require(not self.staging.is_symlink() and stat.S_IMODE(self.staging.stat().st_mode) == 0o700,'integrity')
            self.borrowed,self.state = self.staging/'input.wav','running'
            with self.writer_lock:
                self.borrow_stat = exclusive(self.borrowed,raw)
                self.borrow_chain = ancestors(self.borrowed)
            generation = self.presentation_generation
            settings = dict(request=envelope,identities=self.identities,staging=str(self.staging),snapshot=str(self.root/self.bindings['snapshot']),
                            site_packages=str(self.root/self.bindings['site_packages']),sources={},pins={},
                            root=str(self.root),here=str(self.here),admission=self.admission)
            for name in ('contract','owner','worker'):
                settings['sources'][name] = self.buffers[name+'.py'].decode('utf-8')
                settings['pins'][name] = c.pin(self.buffers[name+'.py'])
            exclusive(self.staging/'ATTEMPT.json',json_bytes(dict(request=envelope,identities=self.identities,state='running')))
            env = dict(PATH='/usr/bin:/bin',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                       HF_DATASETS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                       OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
            receipt = supervise([self.bindings['python'],'-I','-S','-B','-c',BOOTSTRAP],json_bytes(settings),
                                cwd=str(self.staging),env=env,timeout_seconds=self.deadline_seconds,cancellation_event=self.cancel,integrity_guard=self._guard)
            # A receipt is evidence; no response can override exact cleanup.
            self.ledger = receipt['tracked']
            exclusive(self.staging/'SUPERVISION.json',json_bytes(receipt))
            call_state = self._call_state(envelope)
            self.call_state = call_state
            response = None
            if receipt['cleanupConfirmed'] and receipt['workerExitCode'] == 0 and not receipt['supervisionFailed'] and not receipt['timedOut']:
                try:
                    self._guard()
                    self.collection_deadline = time.monotonic()+self.admission['collection_seconds']
                    candidate = self._read_response(envelope)
                    self._guard()
                    response = candidate
                    if response['model_call_state'] == 'completed': call_state = 'completed'; self.call_state = call_state
                except Exception: pass
            if response is None:
                response = c.result('unavailable',self._phase(),'expired' if receipt['timedOut'] else 'runtime_failure',
                                    envelope,self.identities,call_state != 'not_started',False,call_state)
            c.require(response['model_called'] is (call_state != 'not_started'),'malformed_output')
            if receipt['cleanupConfirmed']:
                try: self._delete_borrow(envelope)
                except Exception: receipt['cleanupConfirmed'] = False
            if not receipt['cleanupConfirmed']:
                self.state = 'blocked'
                response = c.result('cleanup_unconfirmed','cleanup','cleanup_unknown',envelope,self.identities,
                                    call_state != 'not_started',False,call_state)
            else:
                self.state = 'finished'
                if generation != self.presentation_generation or receipt['cancelled']:
                    response = c.result('cancelled','complete','cancelled',envelope,self.identities,
                                        call_state != 'not_started',True,call_state)
                response['terminal_owner'] = True
            response['timing_seconds']['cold'] = time.monotonic()-started
            response['timing_seconds']['cleanup'] = receipt['cleanupSeconds']
            exclusive(self.staging/'TERMINAL.json',json_bytes(response))
            return response
        except BaseException as error:
            receipt = getattr(error,'supervision_receipt',None)
            if receipt is not None:
                self.ledger = receipt['tracked']
                try: exclusive(self.staging/'SUPERVISION-INTERRUPTED.json',json_bytes(receipt))
                except BaseException: pass
            if self.borrowed is not None:
                self.state = 'blocked'
                # Conservative durable failure: never discard the borrow on an exception.
                try:
                    exclusive(self.staging/'BLOCKED.json',json_bytes(dict(request=envelope,state='blocked',cleanup_confirmed=False,
                        model_call_state='unknown',tracked=self.ledger,interrupted=isinstance(error,(KeyboardInterrupt,SystemExit)))))
                except BaseException:
                    pass
                self.call_state = 'unknown'
                if isinstance(error,(KeyboardInterrupt,SystemExit)): raise
                return c.result('cleanup_unconfirmed','cleanup','cleanup_unknown',envelope,self.identities,None,False,'unknown')
            if isinstance(error,(KeyboardInterrupt,SystemExit)): raise
            self.state = 'finished'
            return c.result('unavailable','preflight','integrity',envelope,self.identities or {},False,True)
        finally:
            self.lock.release()


# Rebound source; independent review must cover the modifications below.
_UNREAPED=[]
"""Bounded trusted-worker tree cleanup; no adversarial containment claim."""
import os
import select
import signal
import subprocess
import sys
import time


FAILURE_CODES = {'scan_timeout','scan_failed','scan_format_invalid','scan_limit','root_missing',
                 'root_identity_changed','tracking_limit','stop_timeout','kill_timeout','verify_timeout',
                 'signal_failed','stdin_failed','cleanup_unconfirmed'}


class CleanupUnconfirmed(ValueError):
    def __init__(self, code='cleanup_unconfirmed'):
        self.code = code if code in FAILURE_CODES else 'cleanup_unconfirmed'
        super().__init__(self.code)


def process_table(timeout_seconds=0.4):
    try:
        response=subprocess.run(['/bin/ps','-axo','pid=,ppid=,stat=,lstart='],stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout_seconds,check=True)
        if len(response.stdout)>2*1024*1024:raise CleanupUnconfirmed('scan_limit')
        records={}
        for line in response.stdout.decode('ascii').splitlines():
            parts=line.split(None,3)
            if len(parts)!=4:raise CleanupUnconfirmed('scan_format_invalid')
            pid,parent,state,started=parts
            records[int(pid)]={'pid':int(pid),'ppid':int(parent),'state':state,'started':started.strip()}
        return records
    except CleanupUnconfirmed:
        raise
    except subprocess.TimeoutExpired:
        raise CleanupUnconfirmed('scan_timeout') from None
    except (OSError,subprocess.SubprocessError):
        raise CleanupUnconfirmed('scan_failed') from None
    except ValueError:
        raise CleanupUnconfirmed('scan_format_invalid') from None


def _scan(deadline, metrics):
    """One transient retry within the existing budget; never reset ownership."""
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:raise CleanupUnconfirmed('scan_timeout')
        began = time.monotonic()
        try:
            table = process_table(timeout_seconds=min(0.4, remaining))
            metrics['_lastTable'] = table
            return table
        except CleanupUnconfirmed as error:
            if (attempt or error.code not in ('scan_timeout','scan_failed')
                    or time.monotonic() + 0.02 >= deadline):
                raise
            metrics['scanRetries'] += 1
            time.sleep(0.02)
        finally:
            elapsed = time.monotonic() - began
            metrics['scanCount'] += 1
            metrics['scanElapsedSeconds'] += elapsed
            metrics['scanMaximumSeconds'] = max(metrics['scanMaximumSeconds'], elapsed)


def _same(current,record):
    return bool(current and current['pid']==record['pid'] and current['started'].strip()==record['started'].strip())


def _track(table,tracked,root_pid):
    # Continuous snapshots retain evidence for children that later become orphans.
    found={root_pid}|set(tracked)
    changed=True
    while changed:
        changed=False
        for pid,record in table.items():
            if pid not in found and record['ppid'] in found:
                parent=table.get(record['ppid']);known=tracked.get(record['ppid'])
                if known and not _same(parent,known):continue
                if len(tracked)>=128:raise CleanupUnconfirmed('tracking_limit')
                tracked[pid]=dict(record);found.add(pid);changed=True


def _owned(current,record,table,tracked):
    if not _same(current,record):return False
    if current['ppid']==record['ppid']:return True
    parent=tracked.get(record['ppid'])
    old=table.get(record['ppid'])
    return bool(current['ppid']==1 and parent and (old is None or (_same(old,parent) and old['state'].startswith('Z'))))


def _depth(record,tracked):
    depth=0;seen=set();parent=record['ppid']
    while parent in tracked and parent not in seen:
        seen.add(parent);depth+=1;parent=tracked[parent]['ppid']
    return depth


def _signal(record,which,table,tracked):
    current=table.get(record['pid'])
    if not _owned(current,record,table,tracked) or current['state'].startswith('Z'):return False
    try:os.kill(record['pid'],which);return True
    except ProcessLookupError:return False


def _cleanup(root_pid,tracked,metrics):
    deadline=time.monotonic()+2
    root=tracked.get(root_pid)
    if root is None:raise CleanupUnconfirmed('root_missing')
    def scan():
        table=_scan(deadline,metrics)
        # The direct Popen child stays unreaped until cleanup finishes. A
        # missing/changed root cannot be interpreted as confirmed cleanup.
        current=table.get(root_pid)
        if current is None:raise CleanupUnconfirmed('root_missing')
        if not _same(current,root):raise CleanupUnconfirmed('root_identity_changed')
        return table
    table=scan();_signal(root,signal.SIGSTOP,table,tracked)
    stable=None
    while time.monotonic()<deadline:
        table=scan();_track(table,tracked,root_pid)
        for record in list(tracked.values()):
            if time.monotonic()>=deadline:raise CleanupUnconfirmed('stop_timeout')
            _signal(record,signal.SIGSTOP,table,tracked)
        identity={(pid,record['started']) for pid,record in tracked.items()}
        stopped=all(not _owned(table.get(pid),record,table,tracked) or table[pid]['state'].startswith(('T','Z')) for pid,record in tracked.items())
        if identity==stable and stopped:break
        stable=identity;time.sleep(0.02)
    else:raise CleanupUnconfirmed('stop_timeout')
    terminated=0
    for record in sorted(tracked.values(),key=lambda r:_depth(r,tracked),reverse=True):
        if time.monotonic()>=deadline:raise CleanupUnconfirmed('kill_timeout')
        table=scan()
        if _signal(record,signal.SIGKILL,table,tracked) and record['pid']!=root_pid:terminated+=1
    while time.monotonic()<deadline:
        table=scan()
        if all(not _owned(table.get(pid),record,table,tracked) or table[pid]['state'].startswith('Z') for pid,record in tracked.items()):
            return terminated
        time.sleep(0.02)
    raise CleanupUnconfirmed('verify_timeout')


def supervise(command,raw,*,cwd,env,timeout_seconds,cancellation_event=None,integrity_guard=None):
    """One finalization path; retain the process AND tracked ledger on uncertainty."""
    started=time.monotonic()
    # Private bounded FD diagnostics: child writes max 2MiB via file limit in
    # bootstrap; no framework text is loaded into public receipts.
    diagnostics_fd=os.open(Path(cwd)/'DIAGNOSTICS.private',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    process=None; diagnostic_close_error=None
    try:
        process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                                 stderr=diagnostics_fd,start_new_session=True)
        retained={'process':process,'tracked':{},'failureCodes':[]}
        _UNREAPED.append(retained)
    finally:
        try: os.close(diagnostics_fd)
        except BaseException as error:
            if process is None: raise
            diagnostic_close_error=error
    tracked=retained['tracked']; remaining=memoryview(raw); input_open=True
    timed_out=False; cancelled=False; confirmed=False; terminated=0; usage=None
    metrics={'scanCount':0,'scanElapsedSeconds':0.0,'scanMaximumSeconds':0.0,'scanRetries':0}
    failure_phase=None; failure_code=None; phase='monitor'; interrupt=None
    cleanup_started=None; next_guard=started
    def failure(where, error):
        nonlocal failure_phase,failure_code
        failure_phase=where
        failure_code=error.code if isinstance(error,CleanupUnconfirmed) else 'cleanup_unconfirmed'
        retained['failureCodes'].append({'phase':where,'code':failure_code})
    try:
        if diagnostic_close_error is not None: raise diagnostic_close_error
        os.set_blocking(process.stdin.fileno(),False)
        while True:
            now=time.monotonic()
            if now>=started+timeout_seconds: timed_out=True; break
            table=_scan(started+timeout_seconds,metrics)
            if process.pid not in tracked:
                root=table.get(process.pid)
                if root is None: raise CleanupUnconfirmed('root_missing')
                tracked[process.pid]=dict(root)
            _track(table,tracked,process.pid)
            root=table.get(process.pid)
            if not _same(root,tracked[process.pid]): raise CleanupUnconfirmed('root_identity_changed')
            if integrity_guard is not None and now>=next_guard:
                phase='integrity';integrity_guard(started+timeout_seconds);phase='monitor'
                next_guard=time.monotonic()+1.0
            if time.monotonic()>=started+timeout_seconds: timed_out=True; break
            if root['state'].startswith('Z'): break
            if cancellation_event is not None and cancellation_event.is_set(): cancelled=True; break
            if input_open:
                try:
                    if select.select([], [process.stdin], [], 0.02)[1]:
                        count=os.write(process.stdin.fileno(),remaining);remaining=remaining[count:]
                        if not remaining: process.stdin.close();input_open=False
                except BrokenPipeError:
                    process.stdin.close();input_open=False
            else: time.sleep(0.02)
    except BaseException as error:
        failure(phase,error)
        timed_out=time.monotonic()>=started+timeout_seconds
        if isinstance(error,(KeyboardInterrupt,SystemExit)): interrupt=error
    finally:
        cleanup_started=time.monotonic()
        # Each operation has independent containment. A failure in one never
        # skips descendant cleanup, exact-child kill, or bounded wait4.
        try:
            if input_open: process.stdin.close()
        except BaseException as error:
            failure('stdin_close',error)
            if isinstance(error,(KeyboardInterrupt,SystemExit)): interrupt=error
        try:
            terminated=_cleanup(process.pid,tracked,metrics)
            confirmed=True
        except BaseException as error:
            failure('cleanup',error)
            if isinstance(error,(KeyboardInterrupt,SystemExit)): interrupt=error
        try:
            os.kill(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        except BaseException as error:
            confirmed=False; failure('signal',error)
            if isinstance(error,(KeyboardInterrupt,SystemExit)): interrupt=error
        joined=False; join_deadline=time.monotonic()+2
        try:
            while time.monotonic()<join_deadline:
                pid,status,usage=os.wait4(process.pid,os.WNOHANG)
                if pid==process.pid:
                    process.returncode=os.waitstatus_to_exitcode(status); joined=True; break
                if pid not in (0,process.pid): raise CleanupUnconfirmed()
                time.sleep(0.02)
        except BaseException as error:
            failure('join',error)
            if isinstance(error,(KeyboardInterrupt,SystemExit)): interrupt=error
        if not joined:
            confirmed=False; failure('join',CleanupUnconfirmed())
        # A successful descendant cleanup does not erase another finalizer failure.
        if any(x['phase'] in {'stdin_close','signal','join','cleanup'} for x in retained['failureCodes']): confirmed=False
        if confirmed and joined: _UNREAPED.remove(retained)
    last_table=metrics.pop('_lastTable',{})
    receipt={'elapsedSeconds':time.monotonic()-started,
             'peakRssKiB':None if usage is None else usage.ru_maxrss/1024 if sys.platform=='darwin' else usage.ru_maxrss,
             'cleanupSeconds':time.monotonic()-cleanup_started,'workerExitCode':process.returncode,
             'timedOut':timed_out,'acousticCalls':None,'cancelled':cancelled,'cleanupConfirmed':confirmed,
             'descendantsTerminated':terminated,'tracked':list(tracked.values()),
             'cleanupFailurePhase':failure_phase,'cleanupFailureCode':failure_code,
             'supervisionFailed':failure_phase is not None,'interrupted':interrupt is not None,
             'lastObserved':[dict(last_table[pid]) for pid in sorted(tracked) if pid in last_table],**metrics}
    # Deliver ledger and cleanup facts to the owner before propagating interrupt.
    if interrupt is not None:
        interrupt.supervision_receipt=receipt
        raise interrupt
    return receipt


def root_entrypoint(contract,root,here,staging,admission,admission_sha,envelope,input_path):
    """Explicit root-only entrypoint; caller first byte-verifies this owner module."""
    owner = Owner(contract,root,here,staging)
    owner.activate(admission,admission_sha)
    contract.request(envelope)
    raw,_,identity = read_regular(Path(input_path),contract.MAX_WAV)
    contract.require(identity == envelope['wav_identity'],'identity_mismatch')
    return owner.attempt(raw,envelope)
