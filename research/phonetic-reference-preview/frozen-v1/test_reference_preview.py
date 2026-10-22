"""Pure stdlib checks: no WAV generation/access, frameworks, tensors or model calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def source(name):
    # Tests use verified source-buffer loader, not bytecode cache imports.
    raw = (HERE/(name+'.py')).read_bytes()
    import hashlib
    scope = {'__name__':name}
    exec(compile(raw,str(HERE/(name+'.py')),'exec',dont_inherit=True),scope)
    return type('Source',(),scope)

contract, owner = source('contract'), source('owner')
ENVELOPE = dict(operation_id='op',request_id='req',sample_count=1600,
                wav_identity=dict(bytes=3244,sha256='0'*64))
IDENTITIES = {'source':'test-only', 'model':contract.REVISION,'runtime':'mock','vocabulary':'mock'}

class Supervisor:
    identity = 'pure-mock'
    cold_exact_worker = True
    def __init__(self, cleanup=True):
        self.cleanup = cleanup
        self.calls = 0
    def run_one(self,*args):
        self.calls += 1
        return contract.result('unavailable','loading','loadingRejected',ENVELOPE,IDENTITIES)
    def finish_and_observe_cleanup(self):
        return self.cleanup
    def cancel_exact_worker(self):
        pass

class Tests(unittest.TestCase):
    def test_frames(self):
        self.assertEqual([contract.frames(x) for x in (1600,16000,64000)],[4,49,199])
        for bad in (True,1599,64001,1600.0):
            with self.assertRaises(contract.Rejected): contract.frames(bad)
    def test_blank_recurs(self):
        self.assertEqual(contract.collapse([1,1,0,1,2,2,0]),[1,1,2])
        for bad in ([392],[-1],[True]):
            with self.assertRaises(contract.Rejected): contract.collapse(bad)
    def test_closed_request(self):
        contract.request(ENVELOPE)
        for key in ('expectedWord','expectedPhones','language','age','target'):
            with self.assertRaises(contract.Rejected): contract.request({**ENVELOPE,key:'forbidden'})
    def test_malformed_before_model(self):
        with self.assertRaises(contract.Rejected): contract.wav_payload(b'',ENVELOPE)
    def test_inert(self):
        worker = source('worker')
        with self.assertRaises(NameError): worker.run(b'',ENVELOPE,None,IDENTITIES)  # unbootstrapped module
        o = owner.Owner(contract,'unused',IDENTITIES)
        self.assertEqual(o.attempt(b'',ENVELOPE)['reason'],'inactive')
    def test_source_buffer(self):
        raw = b'answer = 42\n'
        m = owner.verified_module('mock',raw,contract.pin(raw))
        self.assertEqual(m.answer,42)
        with self.assertRaises(ValueError): owner.verified_module('mock',raw+b'x',contract.pin(raw))
    def exercise(self, cleanup):
        with tempfile.TemporaryDirectory() as directory:
            o = owner.Owner(contract,Path(directory)/'private',IDENTITIES)
            s = Supervisor(cleanup)
            o.activate(dict(active=True,identities=IDENTITIES,supervisor_identity=s.identity),s)
            # Mock metadata admission and private-file writer; never create/read a waveform.
            with patch.object(contract,'wav_payload',return_value=None), patch.object(owner,'exclusive',return_value=None):
                r = o.attempt(b'',ENVELOPE)
            self.assertEqual(s.calls,1)
            self.assertEqual(o.state,'finished' if cleanup else 'blocked')
            self.assertEqual(r['terminal_owner'],cleanup)
            self.assertEqual(o.borrowed is None,cleanup)
            with self.assertRaises(contract.Rejected): o.attempt(b'',ENVELOPE)
    def test_confirmed_cleanup(self): self.exercise(True)
    def test_unknown_cleanup_latches(self): self.exercise(False)

if __name__ == '__main__': unittest.main()
