"""Inert owner; root separately admits exact worker, runtime, assets and supervisor."""
import hashlib
import os
from pathlib import Path
import stat
import types


def verified_module(name, raw, expected, injected=None):
    """Execute precisely the verified buffer; never import a cache/path afterward."""
    if type(raw) is not bytes or len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
        raise ValueError('sourceChanged')
    module = types.ModuleType(name)
    if injected:
        module.__dict__.update(injected)
    exec(compile(raw, '<verified:'+name+'>', 'exec', dont_inherit=True), module.__dict__)
    return module


def exclusive(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise ValueError('privatePermissions')
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


class Owner:
    """One borrowed file, one cold worker; unknown cleanup permanently latches."""
    def __init__(self, contract, staging, identities):
        self.contract, self.staging, self.identities = contract, Path(staging), identities
        self.state = 'inactive'
        self.borrowed = None
        self.presentation_generation = 0
        self.supervisor = None

    def activate(self, admission, supervisor):
        # Root review binds this exact owner and supervisor. No permissive defaults.
        self.contract.require(self.state == 'inactive' and type(admission) is dict and
                              set(admission) == {'active','identities','supervisor_identity'} and
                              admission['active'] is True and admission['identities'] == self.identities and
                              admission['supervisor_identity'] == supervisor.identity and
                              supervisor.cold_exact_worker is True, 'integrity')
        self.supervisor = supervisor
        self.state = 'ready'

    def cancel_presentation(self):
        self.presentation_generation += 1
        if self.state == 'running':
            self.supervisor.cancel_exact_worker()

    def attempt(self, raw, envelope):
        c = self.contract
        c.request(envelope)
        if self.state == 'inactive':
            return c.result('unavailable','preflight','inactive',envelope,self.identities)
        c.require(self.state == 'ready' and self.borrowed is None, 'cleanup_unknown')
        try:
            c.wav_payload(raw,envelope)
        except c.Rejected as error:
            return c.result('input_rejected','input',error.code,envelope,self.identities,False,True)
        # Exclusive one-attempt directory. Caller supplies a new root for each owner.
        self.staging.mkdir(mode=0o700, parents=False, exist_ok=False)
        c.require(not self.staging.is_symlink() and stat.S_IMODE(self.staging.stat().st_mode) == 0o700, 'integrity')
        self.borrowed = self.staging/'input.wav'
        self.state = 'running'
        generation = self.presentation_generation
        response = None
        model_called = False
        try:
            exclusive(self.borrowed, raw)
            # Supervisor contract: fixed argv/environment, pinned byte-bootstrap, bounded
            # private FDs, exact identity/group lifecycle; never shell/path discovery.
            response = self.supervisor.run_one(self.borrowed, envelope, self.identities)
            c.require(type(response) is dict, 'malformed_output')
            model_called = response.get('model_called') is True
            c.require(type(response) is dict and response.get('schema') == 'PhoneticReferencePreviewV1' and
                      response.get('request') == envelope and response.get('identities') == self.identities and
                      response.get('gates') == c.FALSE_GATES and response.get('kind') in c.KINDS and
                      response.get('phase') in c.PHASES and response.get('reason') in c.REASONS and
                      type(response.get('model_called')) is bool and response.get('terminal_owner') is False and
                      response.get('valid_frames') == c.frames(envelope['sample_count']) and
                      response.get('duration_seconds') == envelope['sample_count']/16000, 'malformed_output')
        except Exception:
            response = c.result('unavailable','forward','runtime_failure',envelope,self.identities,model_called)
        finally:
            # This must observe exact worker and descendant exit even after startup errors.
            try:
                cleaned = self.supervisor.finish_and_observe_cleanup() is True
            except Exception:
                cleaned = False
            if cleaned:
                if self.borrowed.exists():
                    self.borrowed.unlink()
                self.borrowed = None
                self.state = 'finished'  # one request only, no warm reuse
            else:
                self.state = 'blocked'
        if self.state == 'blocked':
            return c.result('cleanup_unconfirmed','cleanup','cleanup_unknown',envelope,self.identities,model_called,False)
        if generation != self.presentation_generation:
            return c.result('cancelled','complete','cancelled',envelope,self.identities,model_called,True)
        response['terminal_owner'] = True
        return response
