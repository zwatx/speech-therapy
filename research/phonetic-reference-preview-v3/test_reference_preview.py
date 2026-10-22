"""Pure source/metadata mocks only: no audio, arrays, frameworks or real subprocess."""
from pathlib import Path
import tempfile
import struct
import types
import unittest
import os
import math
import time
import json
import ast
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
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o = owner.Owner(contract,HERE,HERE,Path(directory)/'private')
            with patch.object(owner.subprocess,'Popen',side_effect=AssertionError('must remain inert')):
                self.assertEqual(o.attempt(b'',ENVELOPE)['reason'],'inactive')
                self.assertEqual(o.attempt(b'',{})['kind'],'input_rejected')
    def exercise(self, cleaned=True, stale=False, cancelled=False, committed=False, replaced=False):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o = owner.Owner(contract,HERE,HERE,Path(directory)/'private')
            o.state,o.identities = 'ready',IDENTITIES
            o.deadline_seconds = 1
            o.admission = {'collection_seconds':1}
            o.bindings = dict(python='/mock/python',snapshot='mock',site_packages='mock')
            o.buffers = {name+'.py':b'# pure source fixture\n' for name in ('contract','owner','worker')}
            response = contract.result('unavailable','loading','loadingRejected',ENVELOPE,IDENTITIES,
                                       committed,False,'invocation_committed' if committed else 'not_started')
            if stale: response['request'] = {**ENVELOPE,'request_id':'stale'}
            receipt = dict(timedOut=False,tracked=[],cleanupConfirmed=cleaned,workerExitCode=0,supervisionFailed=False,cancelled=cancelled,cleanupSeconds=0.01)
            def delete(_):
                if replaced: raise ValueError('changed borrowed identity')
                o.borrowed = None
            def read(_): return contract.response(response,ENVELOPE,IDENTITIES)
            with patch.object(contract,'wav_payload',return_value=None),patch.object(owner,'exclusive',return_value=Mock()),\
                 patch.object(o,'_guard'),patch.object(owner,'supervise',return_value=receipt) as run,patch.object(o,'_read_response',side_effect=read),\
                 patch.object(o,'_call_state',return_value='invocation_committed' if committed else 'not_started'),\
                 patch.object(o,'_delete_borrow',side_effect=delete):
                value = o.attempt(b'',ENVELOPE)
            self.assertEqual(run.call_count,1)
            self.assertEqual(value['model_called'],committed)
            self.assertEqual(o.state,'finished' if cleaned and not replaced else 'blocked')
            self.assertEqual(value['terminal_owner'],cleaned and not replaced)
            self.assertEqual(o.borrowed is None,cleaned and not replaced)
            if cleaned and not replaced:
                self.assertEqual(o.attempt(b'',ENVELOPE)['kind'],'unavailable')
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
             patch.object(owner.os,'open',return_value=10),patch.object(owner.os,'close'),patch.object(owner.os,'kill'),patch.object(owner.os,'wait4',return_value=(42,0,usage)):
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
        with self.assertRaises(contract.Rejected): contract.private_metadata({'ids':[1],'symbols':[]},{},{1:'x'},4)
    def test_admission_is_inactive_by_default(self):
        o = owner.Owner(contract,HERE,HERE,HERE/'unused')
        with self.assertRaises(contract.Rejected): o.activate({},'0'*64)




class V3Tests(unittest.TestCase):
    def setUp(self):
        owner._UNREAPED.clear()

    def loading(self):
        migrations = [
            {'from':'wav2vec2.encoder.pos_conv_embed.conv.weight_g','to':'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0'},
            {'from':'wav2vec2.encoder.pos_conv_embed.conv.weight_v','to':'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original1'}]
        return dict(schema='NativePhoneticLoadingV1',missingKeys=0,unexpectedKeys=0,mismatchedKeys=0,errorMessages=0,
            stateTensorCount=2,parameterElementCount=2,allStateFP32Finite=True,
            migrationPolicy='OnlyPinnedHFPositionalWeightNormNamesV1',migrations=migrations,
            checkpointMapping=[dict(checkpointKey=x['from'],modelKey=x['to'],shape=[1],dtype='torch.float32') for x in migrations])

    def numeric_fixture(self):
        # Invented constant numeric structures; never audio/model arrays.
        vocab = {i:str(i) for i in range(392)}
        rows=[]
        for token in (1,1,0,1):
            row=[0.0]*392; row[token]=1.0; rows.append(struct.pack('<392f',*row))
        logits=b''.join(rows)+struct.pack('<f',0.0)*(195*392)
        normal=struct.pack('<f',0.0)*64000
        hypothesis=dict(ids=[1,1],symbols=contract.symbols([1,1],vocab))
        return logits,normal,hypothesis,self.loading(),vocab

    def collect(self, fixture=None, seconds=1):
        return contract.collect(*(fixture or self.numeric_fixture()),1600,time.monotonic()+seconds)

    def test_independent_raw_collector(self):
        self.assertEqual(self.collect()['tokenCount'],2)

    def test_collector_shape_nonfinite_tail_and_ctc(self):
        base=self.numeric_fixture()
        for index,replacement in ((0,base[0][:-4]),(1,base[1][:-4]),
            (0,struct.pack('<f',float('nan'))+base[0][4:]),
            (0,base[0][:-4]+struct.pack('<f',float('inf'))),
            (1,base[1][:1600*4]+struct.pack('<f',1)+base[1][1601*4:]),
            (1,struct.pack('<f',float('nan'))+base[1][4:]),
            (2,dict(ids=[2],symbols=contract.symbols([2],base[4])))):
            with self.subTest(index=index),self.assertRaises(contract.Rejected):
                fixture=list(base);fixture[index]=replacement;self.collect(fixture)

    def test_collector_metadata_bounds_mapping_counts_and_deadline(self):
        base=self.numeric_fixture()
        for loading in ({**base[3],'parameterElementCount':3},
            {**base[3],'checkpointMapping':[{**x,'shape':[2000000000,2000000000]} for x in base[3]['checkpointMapping']]},
            {**base[3],'stateTensorCount':3}):
            with self.assertRaises(contract.Rejected): self.collect([*base[:3],loading,base[4]])
        hypothesis=dict(ids=[1]*5,symbols=contract.symbols([1]*5,base[4]))
        with self.assertRaises(contract.Rejected): self.collect([base[0],base[1],hypothesis,*base[3:]])
        with self.assertRaises(contract.Rejected): self.collect(seconds=-1)

    def test_argmax_ties_use_lowest_index(self):
        base=list(self.numeric_fixture());base[0]=struct.pack('<f',0.0)*(199*392)
        base[2]={'ids':[],'symbols':[]}
        self.assertEqual(self.collect(base)['tokenCount'],0)

    def owned_file(self,directory):
        staging=Path(directory)/'private';staging.mkdir(mode=0o700)
        o=owner.Owner(contract,HERE,HERE,staging)
        o.borrowed=staging/'input.wav';raw=b'invented structural bytes'
        o.borrow_stat=owner.exclusive(o.borrowed,raw);o.borrow_chain=owner.ancestors(o.borrowed)
        return o,{'wav_identity':contract.pin(raw)},raw

    def test_actual_tiny_leaf_replacement_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o,envelope,raw=self.owned_file(directory)
            saved=o.borrowed.with_name('retained');o.borrowed.rename(saved)
            replacement=b'replacement structural bytes';owner.exclusive(o.borrowed,replacement)
            with self.assertRaises((ValueError,contract.Rejected)):o._delete_borrow(envelope)
            self.assertEqual(o.borrowed.read_bytes(),replacement);self.assertEqual(saved.read_bytes(),raw)
            self.assertIsNotNone(o.borrowed)

    def test_actual_tiny_ancestor_replacement_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o,envelope,raw=self.owned_file(directory)
            saved=o.staging.with_name('retained');o.staging.rename(saved);o.staging.mkdir(mode=0o700)
            owner.exclusive(o.borrowed,b'replacement')
            with self.assertRaises(ValueError):o._delete_borrow(envelope)
            self.assertEqual(o.borrowed.read_bytes(),b'replacement');self.assertEqual((saved/'input.wav').read_bytes(),raw)

    def test_tiny_descriptor_final_leaf_race(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o,_,raw=self.owned_file(directory);original_fstat=os.fstat;calls=0
            def swapped(fd):
                nonlocal calls
                result=original_fstat(fd);calls+=1
                if calls==2:
                    o.borrowed.rename(o.borrowed.with_name('retained'))
                    owner.exclusive(o.borrowed,b'replacement')
                return result
            with patch.object(owner.os,'fstat',side_effect=swapped),self.assertRaises(ValueError):
                owner.read_regular(o.borrowed,1000)
            self.assertEqual(o.borrowed.read_bytes(),b'replacement')

    def test_tiny_descriptor_ancestor_race(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o,_,_=self.owned_file(directory);original_fstat=os.fstat;calls=0
            def swapped(fd):
                nonlocal calls
                result=original_fstat(fd);calls+=1
                if calls==2:
                    o.staging.rename(o.staging.with_name('retained'));o.staging.mkdir(mode=0o700)
                    owner.exclusive(o.borrowed,b'replacement')
                return result
            with patch.object(owner.os,'fstat',side_effect=swapped),self.assertRaises(ValueError):owner.read_regular(o.borrowed,1000)

    def test_tiny_owned_deletion_is_directory_relative(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            o,envelope,_=self.owned_file(directory);leaf=o.borrowed
            o._delete_borrow(envelope)
            self.assertIsNone(o.borrowed);self.assertFalse(leaf.exists())

    def supervisor(self, scan_error=None, close_error=None, cleanup_error=None, signal_error=None, wait_error=None, guard=None):
        p=Mock(pid=42,returncode=None);p.stdin.fileno.return_value=9
        p.stdin.close.side_effect=close_error
        root=dict(pid=42,ppid=1,state='R' if scan_error else 'Z',started='root')
        child=dict(pid=43,ppid=42,state='R',started='child')
        table={42:root,43:child}
        cancellation=Mock();cancellation.is_set.side_effect=scan_error
        with patch.object(owner.subprocess,'Popen',return_value=p),patch.object(owner.os,'open',return_value=10),             patch.object(owner.os,'close'),patch.object(owner.os,'set_blocking'),patch.object(owner,'_scan',return_value=table),             patch.object(owner,'_cleanup',side_effect=cleanup_error,return_value=1) as cleanup,             patch.object(owner.os,'kill',side_effect=signal_error) as kill,             patch.object(owner.os,'wait4',side_effect=wait_error,return_value=(42,0,types.SimpleNamespace(ru_maxrss=1024))) as wait:
            try: value=owner.supervise(['/mock'],b'',cwd='/mock',env={},timeout_seconds=1,cancellation_event=cancellation,integrity_guard=guard)
            except BaseException as error:value=error.supervision_receipt
        return value,cleanup,kill,wait

    def test_interrupt_still_cleans_tracked_descendant_and_joins(self):
        for error in (KeyboardInterrupt(),SystemExit(),RuntimeError()):
            value,cleanup,kill,wait=self.supervisor(scan_error=error)
            self.assertEqual(cleanup.call_count,1);self.assertEqual(wait.call_count,1)
            self.assertEqual({x['pid'] for x in value['tracked']},{42,43})
            self.assertTrue(value['supervisionFailed']);self.assertTrue(value['cleanupConfirmed'])

    def test_finalization_failures_preserve_ledger_and_do_not_skip(self):
        for keyword,error in (('close_error',OSError()),('cleanup_error',KeyboardInterrupt()),
            ('signal_error',OSError()),('wait_error',SystemExit())):
            value,cleanup,kill,wait=self.supervisor(**{keyword:error})
            self.assertFalse(value['cleanupConfirmed']);self.assertEqual(cleanup.call_count,1)
            self.assertEqual(kill.call_count,1);self.assertEqual(wait.call_count,1)
            self.assertEqual(set(owner._UNREAPED[-1]['tracked']),{42,43})

    def test_periodic_integrity_failure_cleans_owned_tree(self):
        guard=Mock(side_effect=ValueError('invented source drift'))
        value,cleanup,_,wait=self.supervisor(guard=guard)
        self.assertTrue(value['supervisionFailed']);self.assertEqual(value['cleanupFailurePhase'],'integrity')
        self.assertEqual(cleanup.call_count,1);self.assertEqual(wait.call_count,1)

    def attempt_mock(self,directory, receipt=None, guard=None, supervisor_error=None):
        o=owner.Owner(contract,HERE,HERE,Path(directory)/'private')
        o.state,o.identities='ready',IDENTITIES;o.deadline_seconds=1
        o.admission={'collection_seconds':1};o.bindings=dict(python='/mock',snapshot='mock',site_packages='mock')
        o.buffers={name+'.py':b'# invented source' for name in ('contract','owner','worker')}
        receipt=receipt or dict(cleanupConfirmed=True,workerExitCode=0,supervisionFailed=False,timedOut=False,cancelled=False,cleanupSeconds=0,tracked=[])
        response=contract.result('model_hypothesis','complete','complete',ENVELOPE,IDENTITIES,True,False,'completed')
        def delete(_):o.borrowed=None
        with patch.object(contract,'wav_payload'),patch.object(o,'_guard',side_effect=guard) as guarding,             patch.object(owner,'supervise',return_value=receipt,side_effect=supervisor_error) as run,             patch.object(o,'_call_state',return_value='completed'),patch.object(o,'_read_response',return_value=response) as read,             patch.object(o,'_delete_borrow',side_effect=delete):
            try:value=o.attempt(b'invented structural bytes',ENVELOPE)
            except BaseException:value=None
        return o,value,run,read,guarding

    def test_deadline_exit_zero_never_publishes_hypothesis(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            receipt=dict(cleanupConfirmed=True,workerExitCode=0,supervisionFailed=False,timedOut=True,cancelled=False,cleanupSeconds=0,tracked=[])
            _,value,_,read,_=self.attempt_mock(directory,receipt)
            self.assertEqual(value['reason'],'expired');self.assertEqual(value['model_call_state'],'completed')
            read.assert_not_called();self.assertTrue(value['terminal_owner'])

    def test_attempt_initial_and_final_source_drift_withhold_success(self):
        for guard in ([ValueError('drift')],[None,ValueError('drift')],[None,None,ValueError('drift')]):
            with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
                _,value,run,_,_=self.attempt_mock(directory,guard=guard)
                self.assertEqual(value['kind'],'unavailable')
                if len(guard)==1:run.assert_not_called()

    def test_owner_interrupt_durable_block_retains_borrow(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            error=KeyboardInterrupt();error.supervision_receipt=dict(tracked=[{'pid':43}],cleanupConfirmed=False)
            o,value,_,_,_=self.attempt_mock(directory,supervisor_error=error)
            self.assertIsNone(value);self.assertEqual(o.state,'blocked');self.assertIsNotNone(o.borrowed)
            blocked=json.loads((o.staging/'BLOCKED.json').read_bytes())
            self.assertEqual(blocked['tracked'],[{'pid':43}]);self.assertTrue(blocked['interrupted'])
            self.assertEqual(blocked['model_call_state'],'unknown');self.assertFalse(o.lock.locked())

    def test_guard_has_complete_closed_source_runtime_assets_and_system_checks(self):
        text=(HERE/'owner.py').read_text()
        for text_fragment in ("for row in runtime['files']",'snapshotNamespace',"Path('/bin/ps')",'interpreterStartupAndStdlib','dynamicLibraries'):
            self.assertIn(text_fragment,text)
        worker=(HERE/'worker.py').read_text();ast.parse(worker)
        self.assertLess(worker.index('forward_started ='),worker.index('logits = model('))
        self.assertLess(worker.index('forward_ended ='),worker.index("output('PHASE-decode"))
        self.assertNotIn('forward=time.monotonic()-extracted',worker)
        self.assertIn('guard()  # immediately before',worker)

class SnapshotTests(unittest.TestCase):
    def test_closed_mapping_mutation_before_load_and_after_activation(self):
        with tempfile.TemporaryDirectory(dir=HERE/'work') as directory:
            root=Path(directory);snapshot=root/'snapshot';snapshot.mkdir()
            blobs=root/'blobs';blobs.mkdir();assets=[]
            for i in range(5):
                leaf='asset'+str(i);(blobs/leaf).write_bytes(b'invented tiny metadata')
                (snapshot/leaf).symlink_to('../blobs/'+leaf)
                assets.append(dict(path='snapshot/'+leaf,resolvedPath='blobs/'+leaf,linkTarget='../blobs/'+leaf))
            bindings={'snapshot':'snapshot','assets':assets}
            owner.snapshot_mappings(root,bindings)
            (snapshot/'extra.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):owner.snapshot_mappings(root,bindings)
            (snapshot/'extra.json').unlink()
            (snapshot/'asset0').unlink();(snapshot/'asset0').symlink_to('../blobs/asset1')
            with self.assertRaises(ValueError):owner.snapshot_mappings(root,bindings)

    def test_unjoined_child_retains_exact_ledger(self):
        p=Mock(pid=42,returncode=None);p.stdin.fileno.return_value=9
        table={42:dict(pid=42,ppid=1,state='Z',started='root'),43:dict(pid=43,ppid=42,state='R',started='child')}
        times=iter([0,0,0,0,3,3,3])
        with patch.object(owner.time,'monotonic',side_effect=lambda:next(times,10)),             patch.object(owner.subprocess,'Popen',return_value=p),patch.object(owner.os,'open',return_value=10),             patch.object(owner.os,'close'),patch.object(owner.os,'set_blocking'),patch.object(owner,'_scan',return_value=table),             patch.object(owner,'_cleanup',return_value=1),patch.object(owner.os,'kill'),             patch.object(owner.os,'wait4',return_value=(0,0,None)),patch.object(owner.time,'sleep'):
            value=owner.supervise(['/mock'],b'',cwd='/mock',env={},timeout_seconds=1)
        self.assertFalse(value['cleanupConfirmed']);self.assertEqual(value['cleanupFailurePhase'],'join')
        self.assertIs(owner._UNREAPED[-1]['process'],p)
        self.assertEqual(set(owner._UNREAPED[-1]['tracked']),{42,43})

if __name__ == '__main__': unittest.main()
