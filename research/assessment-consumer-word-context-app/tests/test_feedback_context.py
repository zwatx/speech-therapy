"""Generated schema2 context, source-path and route-boundary tests; no models/sensors."""
import base64
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from consumer_app import feedback, feedback_contract, feedback_worker, server
from mobile_admission import contract
from admission import adapter, policy
from consumer_assessment import bridge
import test_feedback as fixtures
request_bytes=fixtures.request_bytes
wav_bytes=fixtures.wav_bytes
evidence_for=fixtures.evidence_for
snapshot=fixtures.snapshot


class ContextContractTests(unittest.TestCase):
    def setUp(self):
        self.audio=wav_bytes([8192]*3200)
        self.request=contract.strict_json(request_bytes(self.audio,{'kind':'adult'}))
    def test_exact_adult_and_child_boundaries_decode_without_age_imputation(self):
        for context in ({'kind':'adult'},{'kind':'child','ageYears':6},{'kind':'child','ageYears':12}):
            raw=request_bytes(self.audio,context);request,audio=feedback_contract.prepare(raw)
            self.assertEqual(request['practiceContext'],context);self.assertEqual(audio,self.audio)
            self.assertNotIn('ageYears',request)
        self.assertEqual(self.request['practiceContext'],{'kind':'adult'})
    def test_closed_contexts_refuse_missing_extra_unknown_and_false_numeric_ages(self):
        invalid=[None,True,[],{},'adult',{'kind':'unknown'},{'kind':'adult','ageYears':18},
                 {'kind':'adult','extra':False},{'kind':'child'},
                 *({'kind':'child','ageYears':age} for age in (None,True,False,5,13,18,9.0,'9'))]
        for context in invalid:
            request={**self.request,'practiceContext':context}
            with self.subTest(context=context),self.assertRaises(ValueError):feedback_contract.prepare(contract.canonical(request))
    def test_missing_context_old_version_extra_age_and_bad_uuid_refused(self):
        for change in ('missing','legacy','version','extra','uuid'):
            request=deepcopy(self.request)
            if change=='missing':request.pop('practiceContext')
            if change=='legacy':request.update(schemaVersion=1,ageYears=9);request.pop('practiceContext')
            if change=='version':request['schemaVersion']=True
            if change=='extra':request['ageYears']=9
            if change=='uuid':request['attemptId']='not-a-uuid'
            with self.subTest(change=change),self.assertRaises(ValueError):feedback_contract.prepare(contract.canonical(request))
    def test_duplicate_nonfinite_nonbyte_and_oversize_requests_refused(self):
        for raw in (b'{"schemaVersion":2,"schemaVersion":2}',b'{"practiceContext":{"ageYears":NaN}}',
                    request_bytes(self.audio).decode(),b'x'*200001):
            with self.assertRaises((ValueError,TypeError)):feedback_contract.prepare(raw)
    def test_audio_and_prompt_bounds_stay_closed(self):
        for value in ('!',base64.b64encode(b'').decode(),'a'*176129,base64.b64encode(bytes(contract.MAX_AUDIO+1)).decode()):
            with self.assertRaises(ValueError):feedback_contract.prepare(contract.canonical({**self.request,'audioBase64':value}))
        bad=deepcopy(self.request);bad['prompt']['transcript']='different'
        with self.assertRaises(bridge.Unavailable):feedback_contract.prepare(contract.canonical(bad))
    def test_legacy_assessment_still_rejects_adult_and_schema2_child(self):
        for context in ({'kind':'adult'},{'kind':'child','ageYears':9}):
            with self.assertRaises(ValueError):contract.prepare(request_bytes(self.audio,context))
        for age in (True,5,13,18,None):
            legacy={k:v for k,v in self.request.items() if k!='practiceContext'};legacy.update(schemaVersion=1,ageYears=age)
            with self.assertRaises(ValueError):contract.prepare(contract.canonical(legacy))
    def test_context_changes_request_hash_and_prevent_cross_context_response(self):
        adult=request_bytes(self.audio,{'kind':'adult'});child=request_bytes(self.audio,{'kind':'child','ageYears':9})
        result=feedback.project_feedback(adult,None,None,snapshot(),reason='busy')
        self.assertNotEqual(contract.sha(adult),contract.sha(child))
        with self.assertRaises(ValueError):feedback.validate_response(result,child,snapshot())
        self.assertEqual(result['claimLimits'],feedback.CLAIMS);self.assertEqual(len(result['claimLimits']),11)
    def test_policy_binds_request_version_and_closed_context_semantics(self):
        self.assertEqual(feedback.FEEDBACK_POLICY['id'],'consumer-recording-feedback-v2')
        self.assertEqual(feedback.FEEDBACK_POLICY['requestSchemaVersion'],2)
        self.assertEqual(feedback.FEEDBACK_POLICY['practiceContexts'],feedback_contract.PRACTICE_CONTEXTS)
        old={k:v for k,v in feedback.FEEDBACK_POLICY.items() if k not in ('requestSchemaVersion','practiceContexts','contextMeaning')};old['id']='consumer-recording-feedback-v1'
        self.assertNotEqual(contract.sha(contract.canonical(old)),feedback.FEEDBACK_POLICY_SHA)


class ContextExecutorTests(unittest.TestCase):
    setUp=fixtures.ExecutorTests.setUp
    tearDown=fixtures.ExecutorTests.tearDown
    completed=fixtures.ExecutorTests.completed
    def test_invalid_context_never_reaches_supervisor_or_attempt_directory(self):
        request=contract.strict_json(self.raw);request['practiceContext']={'kind':'adult','ageYears':9}
        with patch.object(feedback,'supervise') as worker,self.assertRaises(ValueError):
            self.executor.execute_feedback(contract.canonical(request))
        worker.assert_not_called();self.assertEqual(list(self.executor.runtime.glob('attempt-*')),[])
    def test_worker_recognizes_both_contexts_once_and_never_calls_age_research(self):
        for index,context in enumerate(({'kind':'adult'},{'kind':'child','ageYears':9})):
            raw=request_bytes(self.audio,context);stage=Path(self.directory.name)/str(index);stage.mkdir(mode=0o700)
            evidence=evidence_for(self.audio)
            with patch.object(sys,'argv',['worker',str(stage)]),patch.object(sys,'stdin',io.TextIOWrapper(io.BytesIO(raw))),patch.object(adapter,'WORK',stage),patch.object(adapter,'recognize',return_value=evidence) as recognition,patch.object(policy,'decide',wraps=policy.decide) as decision,patch.object(adapter,'assess') as assess,patch.object(bridge,'assess') as head:
                feedback_worker.main();recognition.assert_called_once_with(self.audio);decision.assert_called_once_with(evidence,'baby');assess.assert_not_called();head.assert_not_called()
            payload=contract.strict_json((stage/'feedback.json').read_bytes());self.assertEqual(payload['requestSha256'],contract.sha(raw));self.assertEqual(payload['binding'],self.executor.declared_snapshot)
    def test_supervised_child_environment_imports_exact_successor_worker_in_fresh_process(self):
        def complete(command,raw,**kwargs):
            env=kwargs['env'];expected=feedback.MODULE.parent
            self.assertEqual(Path(env['PYTHONPATH'].split(':')[0]),expected)
            code='import json;from pathlib import Path;import consumer_app,consumer_app.feedback_worker as w;print(json.dumps([str(Path(consumer_app.__file__).resolve()),str(Path(w.__file__).resolve())]))'
            result=subprocess.run([sys.executable,'-c',code],cwd=server.ROOT,env=env,capture_output=True,timeout=5,check=True)
            self.assertEqual(json.loads(result.stdout),[str(expected/'consumer_app/__init__.py'),str(expected/'consumer_app/feedback_worker.py')])
            return self.completed(command,raw,**kwargs)
        with patch.object(feedback,'supervise',side_effect=complete):result=self.executor.execute_feedback(request_bytes(self.audio,{'kind':'adult'}))
        self.assertEqual(result['stages']['word']['state'],'model_matched')
    def test_private_result_from_other_context_is_refused_after_cleanup(self):
        def changed(command,raw,**kwargs):
            result=self.completed(command,raw,**kwargs);p=Path(command[-1])/'feedback.json';payload=contract.strict_json(p.read_bytes());payload['requestSha256']=contract.sha(request_bytes(self.audio,{'kind':'adult'}));p.write_bytes(contract.canonical(payload));return result
        with patch.object(feedback,'supervise',side_effect=changed):result=self.executor.execute_feedback(self.raw)
        self.assertEqual(result['reason'],'assessment_failed');self.assertEqual(result['stages']['word']['state'],'unavailable');self.assertFalse(list(self.executor.runtime.glob('attempt-*')))
    def test_successor_defaults_and_check_do_not_create_runtime_or_read_model_weights(self):
        self.assertEqual(server.PORT,8791)
        self.assertEqual(feedback.FeedbackExecutor.__init__.__defaults__[0],server.ROOT/'work/consumer-feedback-20261007/adult-word-context/runtime')
        path=server.ROOT/'scripts/consumer-word-context-app.py';spec=importlib.util.spec_from_file_location('successor_launcher',path);launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        fresh=Path(self.directory.name)/'check-runtime'
        with patch.object(adapter,'recognize',side_effect=AssertionError('no model')),patch('admission.models.readiness',side_effect=AssertionError('no weights')),patch('consumer_app.catalog.Catalog',side_effect=AssertionError('no media')),patch('consumer_app.server.Server',side_effect=AssertionError('no listener')):
            self.assertEqual(launcher.main(['--check','--runtime',str(fresh)]),0)
        self.assertFalse(fresh.exists())


class ContextHTTPTests(unittest.TestCase):
    setUp=fixtures.FeedbackHTTPTests.setUp
    tearDown=fixtures.FeedbackHTTPTests.tearDown
    send=fixtures.FeedbackHTTPTests.send
    completed=fixtures.ExecutorTests.completed
    def test_both_contexts_settle_only_feedback_and_old_schema_is_refused(self):
        with patch.object(feedback,'supervise',side_effect=self.completed) as worker:
            for context in ({'kind':'adult'},{'kind':'child','ageYears':9}):
                raw=request_bytes(self.audio,context);status,payload,_=self.send(raw=raw)
                self.assertEqual(status,200);self.assertEqual(contract.strict_json(payload)['binding']['requestSha256'],contract.sha(raw))
                self.assertEqual(self.send('/api/assessment',raw=raw)[0],400)
            legacy=contract.strict_json(self.raw);legacy.update(schemaVersion=1,ageYears=9);legacy.pop('practiceContext')
            self.assertEqual(self.send(raw=contract.canonical(legacy))[0],400);self.assertEqual(worker.call_count,2)
    def test_invalid_context_HTTP_is_400_and_never_processes(self):
        request=contract.strict_json(self.raw);request['practiceContext']={'kind':'adult','extra':False}
        with patch.object(feedback,'supervise') as worker:
            self.assertEqual(self.send(raw=contract.canonical(request))[0],400);worker.assert_not_called()
