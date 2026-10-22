"""Bounded full admission in the existing offline model environment."""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from .models import JourneyError
from .catalog import ROOT, read_owned

WORK = ROOT / 'work/roadmap-completion-20261004/journey'
TIMEOUT = 110

class OfflineAdapter:
    def __init__(self, root=None):
        self.root = Path(root).resolve() if root is not None else WORK
        self._cancel = threading.Event()
        self._memory_blocked = False
    def prepare(self): self._cancel.clear()
    def cancel(self): self._cancel.set()
    def assert_cleanup(self):
        if self._memory_blocked:raise JourneyError('process_cleanup_unconfirmed')
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(directory)
            if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise JourneyError('process_cleanup_unconfirmed')
            for name in ('process-cleanup-blocked.json','process-cleanup-required.json'):
                try:os.stat(name,dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError:continue
                raise JourneyError('process_cleanup_unconfirmed')
        finally:os.close(directory)
    def _write_marker(self,name,value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(directory)
            if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise JourneyError('process_cleanup_unconfirmed')
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:
                remaining=memoryview(raw)
                while remaining:
                    count=os.write(fd,remaining);remaining=remaining[count:]
                os.fsync(fd)
            finally:os.close(fd)
            os.fsync(directory)
        finally:os.close(directory)
    def _block(self,runtime):
        self._memory_blocked = True
        self._write_marker('process-cleanup-blocked.json',{'schemaVersion':1,'reason':'process_cleanup_unconfirmed','tracked':runtime['tracked']})
    def _intent(self):
        self._write_marker('process-cleanup-required.json',{'schemaVersion':1,'cleanupRequired':True})
    def _complete(self):
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            os.unlink('process-cleanup-required.json',dir_fd=directory);os.fsync(directory)
        except OSError:
            self._memory_blocked = True
            raise
        finally:os.close(directory)
    def declaration(self):
        import admission
        sources={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('adapter.py','worker.py','process.py')}
        return {**admission.declaration(),'journeyAdapterSha256':hashlib.sha256(json.dumps(sources,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    def assess(self,wav_bytes,prompt,age_years=9):
        from .process import supervise
        self.assert_cleanup()
        if type(wav_bytes) is not bytes or len(wav_bytes)>132096:raise JourneyError('invalid_response')
        info=os.stat(WORK,follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise JourneyError('assessment_unavailable')
        self._intent()
        failure = None; result = None; confirmed = False
        with tempfile.TemporaryDirectory(prefix='runtime-',dir=WORK) as directory:
            stage=Path(directory)
            env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
                 'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','TMPDIR':str(stage),
                 'PYTHONPATH':os.pathsep.join(str(ROOT/'research'/name) for name in ('assessment-desktop-journey','assessment-admission','audio-head'))}
            raw=json.dumps({'audioBase64':base64.b64encode(wav_bytes).decode(),'prompt':prompt,'ageYears':age_years},sort_keys=True,separators=(',',':')).encode()
            try:
                runtime=supervise([str(ROOT/'research/audio-head/.venv/bin/python'),'-m','journey.worker',str(stage)],raw,cwd=ROOT,env=env,timeout_seconds=TIMEOUT,cancellation_event=self._cancel)
                confirmed = runtime['cleanupConfirmed']
                if not confirmed:
                    self._block(runtime)
                    raise JourneyError('process_cleanup_unconfirmed')
                if runtime.get('cancelled') or runtime['timedOut'] or runtime['workerExitCode']!=0:raise JourneyError('assessment_unavailable')
                result=json.loads(read_owned(stage/'result.json',65536).decode('utf-8'))
            except Exception as error:
                failure = error
        # Reaching this point also confirms removal of this job's private stage.
        if confirmed:self._complete()
        if failure:raise failure
        return result
