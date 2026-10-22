import base64
import builtins
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import wave
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from mobile_admission import contract
from consumer_app.server import Server, validate_audio, validate_public_result
from consumer_app import server
from consumer_app.catalog import Catalog
from mobile_admission.service import Executor


def audio(seconds=1):
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        wav.writeframes(b'\0\0'*int(16000*seconds))
    return output.getvalue()


PROMPT={'schemaVersion':2,'language':'en','transcript':'baby',
        'words':[{'text':'baby','phones':['B','EY1','B','IY0']}],
        'targets':[{'id':'b-beginning-baby','wordIndex':0,'phoneIndex':0,'targetPhone':'B'}]}


def body(prompt=None,wav=None):
    return contract.canonical({'schemaVersion':1,'attemptId':str(uuid.uuid4()),'ageYears':9,
                              'prompt':deepcopy(prompt or PROMPT),
                              'audioBase64':base64.b64encode(wav or audio()).decode('ascii')})


class ExampleCatalog:
    def projection(self):return {'schemaVersion':1,'prompts':[{'id':'b-beginning-baby','prompt':deepcopy(PROMPT)}]}
    def accepts(self,prompt):return contract.canonical(prompt)==contract.canonical(PROMPT)
    def reference(self,word):
        if word!='baby':raise ValueError('not_found')
        return audio()
    def illustration(self,word):
        if word!='baby':raise ValueError('not_found')
        return b'<svg xmlns="http://www.w3.org/2000/svg"/>'


class ExampleExecutor:
    blocked=False
    calls=0
    def is_blocked(self):return self.blocked
    def execute(self,raw):
        self.calls+=1;request,wav=contract.prepare(raw)
        return contract.response(raw,request,wav,reason='silence')


class ConsumerTests(unittest.TestCase):
    def test_documented_parent_environment_imports_in_a_fresh_process(self):
        readme=(server.UI.parent/'README.md').read_text()
        environment=readme.split('PYTHONPATH=',1)[1].split(' python3',1)[0]
        env={**os.environ,'PYTHONPATH':environment}
        completed=subprocess.run([sys.executable,'-c','from consumer_app.server import main; from admission.models import private_read'],
                                 cwd=server.ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertEqual(completed.returncode,0)
        env['PYTHONPATH']=':'.join(part for part in environment.split(':') if part!='research/assessment-admission')
        code='from consumer_app.server import main\ntry: main()\nexcept ValueError as error:\n assert str(error)=="dependency_unavailable"\nelse: raise AssertionError("startup accepted missing dependency")'
        refused=subprocess.run([sys.executable,'-c',code],cwd=server.ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertEqual(refused.returncode,0)

    def test_startup_missing_parent_admission_dependency_never_opens_runtime_or_listener(self):
        original=builtins.__import__
        def without_admission(name,*args,**kwargs):
            if name=='admission.models':raise ModuleNotFoundError('admission.models')
            return original(name,*args,**kwargs)
        with patch.object(builtins,'__import__',side_effect=without_admission),patch.object(server,'Catalog') as catalog,patch.object(server,'Executor') as executor,patch.object(server,'Server',side_effect=AssertionError('listener reached')):
            with self.assertRaisesRegex(ValueError,'dependency_unavailable'):server.main()
            catalog.assert_not_called();executor.assert_not_called()

    def test_real_public_catalog_has_fifteen_exact_canonical_prompts(self):
        catalog=Catalog();public=catalog.projection()
        self.assertEqual(len(public['prompts']),15)
        for item in public['prompts']:
            self.assertTrue(catalog.accepts(item['prompt']))
            self.assertEqual(item['prompt']['targets'][0]['phoneIndex'],item['selectedOccurrenceIndex'])
            self.assertEqual(item['prompt']['words'][0]['phones'],next(v['phones'] for v in item['variants'] if v['id']==item['selectedVariantId']))
        public['prompts'][0]['prompt']['transcript']='mutation'
        self.assertNotEqual(catalog.projection()['prompts'][0]['prompt']['transcript'],'mutation')

    def test_audio_four_second_pcm_limit_and_malformed_boundary(self):
        validate_audio(audio(4))
        for raw in (audio(4.001),b'not wave',audio(0)):
            with self.assertRaises(ValueError):validate_audio(raw)

    def test_response_refuses_extra_evidence_spoofed_claim_or_binding(self):
        raw=body();request,wav=contract.prepare(raw);result=contract.response(raw,request,wav,reason='silence')
        self.assertEqual(validate_public_result(result,raw,request,wav),result)
        for edit in (lambda r:r.update(transcript='private'),lambda r:r['claimLimits'].update(clinicalUseEligible=True),
                     lambda r:r['binding'].update(audioSha256='f'*64),lambda r:r.update(status='processed')):
            changed=deepcopy(result);edit(changed)
            with self.assertRaises(ValueError):validate_public_result(changed,raw,request,wav)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.executor=ExampleExecutor();self.server=Server(self.executor,ExampleCatalog(),port=0,source_check=lambda:contract.bindings())
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.02});self.thread.start()
        self.port=self.server.server_address[1];self.origin=f'http://127.0.0.1:{self.port}'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def send(self,path='/api/assessment',raw=None,headers=None,method='POST'):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        head={'Origin':self.origin,'X-Consumer-CSRF':self.server.csrf_token,'Content-Type':'application/json'}
        if headers:head.update(headers)
        conn.request(method,path,body=body() if raw is None and method=='POST' else raw,headers=head)
        response=conn.getresponse();value=response.read();status=response.status;response_headers=dict(response.getheaders());conn.close()
        return status,value,response_headers
    def test_exact_origin_and_csrf_required_before_execution(self):
        for edit in ({'Origin':'http://elsewhere.invalid'},{'X-Consumer-CSRF':'wrong'},{'Host':'localhost:'+str(self.port)}, {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.send(headers=edit)[0],403)
        self.assertEqual(self.executor.calls,0)
        status,raw,_=self.send();self.assertEqual(status,200);self.assertEqual(json.loads(raw)['reason'],'silence')
    def test_arbitrary_prompt_camera_and_oversize_requests_never_execute(self):
        changed=deepcopy(PROMPT);changed['targets'][0]['phoneIndex']=2
        self.assertEqual(self.send(raw=body(changed))[0],400)
        self.assertEqual(self.send(raw=b' ' *200001)[0],400)
        self.assertEqual(self.send(path='/api/camera',raw=b'{}')[0],404)
        self.assertEqual(self.executor.calls,0)
    def test_declaration_available_and_latch_reflected_without_capture(self):
        status,raw,headers=self.send('/api/declaration',method='GET')
        declaration=json.loads(raw);self.assertEqual(status,200)
        self.assertEqual(set(declaration),{'schemaVersion','csrfToken','pins','processingAvailable'})
        self.assertEqual(len(declaration['csrfToken']),64);self.assertTrue(declaration['processingAvailable'])
        self.assertNotIn('Access-Control-Allow-Origin',headers);self.assertEqual(headers['Cache-Control'],'no-store')
        self.executor.blocked=True
        self.assertFalse(json.loads(self.send('/api/declaration',method='GET')[1])['processingAvailable'])
        self.assertEqual(self.executor.calls,0)
    def test_public_full_wave_and_range_rejection(self):
        status,raw,headers=self.send('/api/public-references/baby',method='GET')
        self.assertEqual(status,200);self.assertEqual(raw,audio());self.assertEqual(headers['Content-Type'],'audio/wav')
        self.assertEqual(self.send('/api/public-references/baby',method='GET',headers={'Range':'bytes=0-10'})[0],403)

    def test_actual_audio_worklet_closed_route_and_mime(self):
        status,raw,headers=self.send('/audio-capture.js',method='GET')
        self.assertEqual(status,200)
        self.assertEqual(raw,(server.UI/'audio-capture.js').read_bytes())
        self.assertEqual(headers['Content-Type'],'text/javascript; charset=utf-8')
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(self.send('/arbitrary-worklet.js',method='GET')[0],404)
        self.assertEqual(self.executor.calls,0)

    def test_duplicate_host_and_missing_origin_do_not_execute(self):
        for duplicate in (True,False):
            conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3);raw=body()
            conn.putrequest('POST','/api/assessment',skip_host=True)
            conn.putheader('Host',f'127.0.0.1:{self.port}')
            if duplicate:
                conn.putheader('Host',f'127.0.0.1:{self.port}');conn.putheader('Origin',self.origin)
            conn.putheader('X-Consumer-CSRF',self.server.csrf_token)
            conn.putheader('Content-Type','application/json');conn.putheader('Content-Length',str(len(raw)))
            conn.endheaders(raw);response=conn.getresponse();response.read()
            self.assertEqual(response.status,403);conn.close()
        self.assertEqual(self.executor.calls,0)

    def test_invalid_utf16_extra_fields_and_private_history_routes_refused(self):
        raw=body()
        malformed=json.loads(raw);malformed['cameraFrames']=[]
        for value in (raw.decode().encode('utf-16'),contract.canonical(malformed),b'{"schemaVersion":1,"schemaVersion":1}'):
            self.assertEqual(self.send(raw=value)[0],400)
        for path in ('/api/history','/api/accounts','/api/export'):
            self.assertEqual(self.send(path,method='GET')[0],404)
        self.assertEqual(self.executor.calls,0)

    def test_real_executor_busy_is_bound_without_start_or_audio_files(self):
        with tempfile.TemporaryDirectory() as directory:
            executor=Executor(Path(directory)/'runtime');self.server.executor=executor
            executor.slot.acquire()
            try:
                status,raw,_=self.send();result=json.loads(raw)
                self.assertEqual(status,200);self.assertEqual(result['reason'],'busy')
                self.assertIsNotNone(result['binding']['audioSha256'])
                self.assertEqual([p.name for p in executor.runtime.iterdir()],['service.lock'])
            finally:executor.slot.release();executor.close();self.server.executor=self.executor

    def test_actual_unsupported_catalog_prompt_refuses_without_launch_or_stage(self):
        catalog=Catalog();treasure=next(row['prompt'] for row in catalog.projection()['prompts'] if row['sourceWord']=='treasure')
        with tempfile.TemporaryDirectory() as directory:
            executor=Executor(Path(directory)/'runtime');self.server.executor=executor;self.server.catalog=catalog
            try:
                with patch('mobile_admission.service.supervise') as worker:
                    status,raw,_=self.send(raw=body(treasure));worker.assert_not_called()
                self.assertEqual(status,200);self.assertEqual(json.loads(raw)['reason'],'unsupported_target')
                self.assertEqual([p.name for p in executor.runtime.iterdir()],['service.lock'])
            finally:executor.close();self.server.executor=self.executor

    def test_untrusted_extra_result_field_is_never_exposed_over_http(self):
        original=self.executor.execute
        def injected(raw):
            result=original(raw);result['transcript']='sentinel private transcript';return result
        self.executor.execute=injected
        status,raw,_=self.send()
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['reason'],'assessment_failed')
        self.assertNotIn(b'sentinel',raw)

    def test_source_failure_declaration_disables_processing(self):
        def failed():raise ValueError('source_binding_failed')
        self.server.source_check=failed
        declaration=json.loads(self.send('/api/declaration',method='GET')[1])
        self.assertFalse(declaration['processingAvailable']);self.assertEqual(self.executor.calls,0)

    def test_disconnect_does_not_skip_confirmed_executor_cleanup(self):
        # Injected worker output only; real HTTP connection + private executor files.
        with tempfile.TemporaryDirectory() as directory:
            executor=Executor(Path(directory)/'runtime');self.server.executor=executor
            entered=threading.Event();release=threading.Event()
            def finished(*args,**kwargs):
                entered.set();release.wait(2)
                return {'cleanupConfirmed':True,'timedOut':False,'workerExitCode':1}
            try:
                with patch('mobile_admission.service.verify_sources',return_value=contract.bindings()),patch('mobile_admission.service.supervise',side_effect=finished):
                    raw=body();connection=socket.create_connection(('127.0.0.1',self.port),timeout=3)
                    header=f'POST /api/assessment HTTP/1.0\r\nHost: 127.0.0.1:{self.port}\r\nOrigin: {self.origin}\r\nX-Consumer-CSRF: {self.server.csrf_token}\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\n\r\n'.encode()
                    connection.sendall(header+raw);self.assertTrue(entered.wait(2));connection.close();release.set()
                    deadline=time.monotonic()+2
                    while (executor.runtime/'cleanup-required').exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertFalse(list(executor.runtime.glob('attempt-*')))
                    self.assertFalse((executor.runtime/'cleanup-required').exists());self.assertFalse(executor.is_blocked())
                    self.assertNotIn('audio', (executor.runtime/'last-runtime.json').read_text())
            finally:release.set();executor.close();self.server.executor=self.executor


if __name__=='__main__':unittest.main()
