"""Pure source/metadata mocks only: no audio, arrays, frameworks or real subprocess."""
from pathlib import Path
import tempfile
import struct
import types
import unittest
from unittest.mock import Mock,patch

HERE = Path(__file__).resolve().parent

def source(name):
    m = types.ModuleType(name)
    raw = (HERE/(name+'.py')).read_bytes()
    exec(compile(raw,str(HERE/(name+'.py')),'exec',dont_inherit=True),m.__dict__)
    return m

contract,owner = source('contract'),source('owner')
ENVELOPE = dict(operation_id='op',request_id='req',sample_count=1600,wav_identity=dict(bytes=3244,sha256='0'*64))
IDENTITIES = dict(source='pure-test-only',runtime='mock',model=contract.REVISION,vocabulary='mock')

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
        for key in ('expectedWord','expectedPhones','language','age','target'):
            with self.assertRaises(contract.Rejected): contract.request({**ENVELOPE,key:'forbidden'})
        with self.assertRaises(contract.Rejected): contract.wav_payload(b'',ENVELOPE)
    def test_duplicate_json(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}'):
            with self.assertRaises(contract.Rejected): contract.closed_json(raw)
    def test_closed_response(self):
        valid = contract.result('unavailable','loading','loadingRejected',ENVELOPE,IDENTITIES)
        for key,value in [('extra',1),('request',{**ENVELOPE,'request_id':'stale'}),('gates',{}),
                          ('model_called',True),('valid_frames',True),('kind','cleanup_unconfirmed'),
                          ('timing_seconds',dict.fromkeys(contract.TIMINGS,float('nan')))]:
            with self.assertRaises(contract.Rejected): contract.response({**valid,key:value},ENVELOPE,IDENTITIES)
    def test_source_cache_regression(self):
        raw = b'answer = 42\n'
        module = owner.verified_module('pure',raw,contract.pin(raw))
        self.assertEqual(module.answer,42)
        with self.assertRaises(ValueError): owner.verified_module('pure',raw+b'x',contract.pin(raw))
        self.assertIn("compile(raw",owner.BOOTSTRAP)
        self.assertNotIn('spec_from_file_location',owner.BOOTSTRAP)
    def test_inert_and_invalid_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            o = owner.Owner(contract,HERE,HERE,Path(directory)/'private')
            with patch.object(owner.subprocess,'Popen',side_effect=AssertionError('must remain inert')):
                self.assertEqual(o.attempt(b'',ENVELOPE)['reason'],'inactive')
                self.assertEqual(o.attempt(b'',{})['kind'],'input_rejected')
    def exercise(self, cleaned=True, stale=False, cancelled=False, committed=False, replaced=False):
        with tempfile.TemporaryDirectory() as directory:
            o = owner.Owner(contract,HERE,HERE,Path(directory)/'private')
            o.state,o.identities = 'ready',IDENTITIES
            o.deadline_seconds = 1
            o.bindings = dict(python='/mock/python',snapshot='mock',site_packages='mock')
            o.buffers = {name+'.py':b'# pure source fixture\n' for name in ('contract','worker')}
            response = contract.result('unavailable','loading','loadingRejected',ENVELOPE,IDENTITIES,
                                       committed,False,'invocation_committed' if committed else 'not_started')
            if stale: response['request'] = {**ENVELOPE,'request_id':'stale'}
            receipt = dict(cleanupConfirmed=cleaned,workerExitCode=0,supervisionFailed=False,cancelled=cancelled,cleanupSeconds=0.01)
            def delete(_):
                if replaced: raise ValueError('changed borrowed identity')
                o.borrowed = None
            def read(_): return contract.response(response,ENVELOPE,IDENTITIES)
            with patch.object(contract,'wav_payload',return_value=None),patch.object(owner,'exclusive',return_value=Mock()),\
                 patch.object(owner,'supervise',return_value=receipt) as run,patch.object(o,'_read_response',side_effect=read),\
                 patch.object(o,'_call_state',return_value='invocation_committed' if committed else 'not_started'),\
                 patch.object(o,'_delete_borrow',side_effect=delete):
                value = o.attempt(b'',ENVELOPE)
            self.assertEqual(run.call_count,1)
            self.assertEqual(value['model_called'],committed)
            self.assertEqual(o.state,'finished' if cleaned and not replaced else 'blocked')
            self.assertEqual(value['terminal_owner'],cleaned and not replaced)
            self.assertEqual(o.borrowed is None,cleaned and not replaced)
            if cleaned and not replaced:
                with self.assertRaises(contract.Rejected): o.attempt(b'',ENVELOPE)
            else:
                self.assertEqual(o.attempt(b'',ENVELOPE)['kind'],'cleanup_unconfirmed')
            return value
    def test_confirmed_cleanup(self): self.exercise()
    def test_unknown_cleanup(self): self.assertEqual(self.exercise(False)['kind'],'cleanup_unconfirmed')
    def test_replaced_borrow(self): self.assertEqual(self.exercise(replaced=True)['kind'],'cleanup_unconfirmed')
    def test_stale_response(self): self.assertEqual(self.exercise(stale=True)['reason'],'runtime_failure')
    def test_forward_failure_marker(self): self.assertTrue(self.exercise(committed=True)['model_called'])
    def test_cancel_still_joins(self): self.assertEqual(self.exercise(cancelled=True)['kind'],'cancelled')
    def test_cancel_before_launch(self):
        o = owner.Owner(contract,HERE,HERE,HERE/'unused');o.state,o.identities = 'ready',IDENTITIES
        o.cancel_presentation()
        with patch.object(owner,'supervise',side_effect=AssertionError('no launch')):
            self.assertEqual(o.attempt(b'',ENVELOPE)['kind'],'cancelled')
    def test_exact_process_mock(self):
        p = Mock(pid=42,returncode=None)
        p.stdin.fileno.return_value = 9
        table = {42:dict(pid=42,ppid=1,state='Z',started='mock-identity')}
        usage = types.SimpleNamespace(ru_maxrss=1024)
        with patch.object(owner.subprocess,'Popen',return_value=p) as launch,patch.object(owner.os,'set_blocking'),\
             patch.object(owner,'_scan',return_value=table),patch.object(owner,'_cleanup',return_value=0),\
             patch.object(owner.os,'kill'),patch.object(owner.os,'wait4',return_value=(42,0,usage)):
            value = owner.supervise(['/mock/python'],b'{}',cwd='/mock',env={},timeout_seconds=1)
        self.assertTrue(value['cleanupConfirmed'])
        self.assertEqual(value['workerExitCode'],0)
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
    def test_malformed_riff_structural_headers(self):
        # Header-only structural fixtures, never a waveform or decoded samples.
        for rate,size in ((8000,3200),(16000,3201),(16000,0)):
            header = b'RIFF'+struct.pack('<I',36)+b'WAVEfmt '+struct.pack('<IHHIIHH',16,1,1,rate,rate*2,2,16)+b'data'+struct.pack('<I',size)
            envelope = {**ENVELOPE,'wav_identity':contract.pin(header)}
            with self.assertRaises(contract.Rejected): contract.wav_payload(header,envelope)
    def test_unknown_call_accounting(self):
        value = contract.result('cleanup_unconfirmed','cleanup','cleanup_unknown',ENVELOPE,IDENTITIES,None,False,'unknown')
        self.assertIsNone(contract.response(value,ENVELOPE,IDENTITIES)['model_called'])
    def test_invalid_loading_metadata(self):
        with self.assertRaises(contract.Rejected): contract.private_metadata({'ids':[1],'symbols':[]},{},{1:'x'})
    def test_admission_is_inactive_by_default(self):
        o = owner.Owner(contract,HERE,HERE,HERE/'unused')
        with self.assertRaises(contract.Rejected): o.activate({},'0'*64)

if __name__ == '__main__': unittest.main()
