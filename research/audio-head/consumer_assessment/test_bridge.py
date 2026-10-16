import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
from consumer_assessment import bridge


def wav(value=1000, count=16000, channels=1):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(channels); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(int(value).to_bytes(2,'little',signed=True)*count*channels)
    return out.getvalue()


def request(value=1000):
    return {'schemaVersion':1,'attemptId':'00000000-0000-4000-8000-000000000001','ageYears':9,
            'audioBase64':base64.b64encode(wav(value)).decode(),
            'prompt':{'schemaVersion':2,'language':'en','transcript':'BOB',
                      'words':[{'text':'BOB','phones':['B','AA1','B']}],
                      'targets':[{'id':'end','wordIndex':0,'phoneIndex':2,'targetPhone':'B'},
                                 {'id':'start','wordIndex':0,'phoneIndex':0,'targetPhone':'B'}]}}


def raw(r): return json.dumps(r,allow_nan=False).encode()


class InputTests(unittest.TestCase):
    def test_repeat_and_caller_variant_order(self):
        p=bridge.prepare(raw(request()))
        self.assertEqual([t['id'] for t in p.request['prompt']['targets']],['end','start'])
        r=request(); r['prompt']['words'][0]['phones']=['B','AO0','B']
        self.assertEqual(bridge.prepare(raw(r)).request['prompt']['words'][0]['phones'][1],'AO0')

    def test_age_bounds_and_boolean(self):
        for age in (6,12):
            r=request(); r['ageYears']=age; bridge.prepare(raw(r))
        for age in (5,13,6.5,True):
            r=request(); r['ageYears']=age
            self.assertEqual(bridge.assess(raw(r))['reason'],'age_out_of_range')

    def test_unsupported_zh_er_targets(self):
        for phone in ('ZH','ER','ER0'):
            r=request(); r['prompt']['words'][0]['phones'][0]=phone
            r['prompt']['targets'][1]['targetPhone']=phone
            self.assertEqual(bridge.assess(raw(r))['reason'],'unsupported_target')

    def test_duplicate_identity_position_and_extra_fields(self):
        for change in ('id','position','extra'):
            r=request()
            if change=='id': r['prompt']['targets'][1]['id']='end'
            elif change=='position': r['prompt']['targets'][1]['phoneIndex']=2
            else: r['audioPath']='/etc/passwd'
            self.assertEqual(bridge.assess(raw(r))['reason'],'invalid_request')

    def test_audio_and_json_malformation(self):
        for audio in ('!!!!',base64.b64encode(b'bad').decode(),base64.b64encode(wav(channels=2)).decode()):
            r=request(); r['audioBase64']=audio
            self.assertEqual(bridge.assess(raw(r))['reason'],'invalid_audio')
        for data in (b'{',b'{"schemaVersion":NaN}',b'{"schemaVersion":1,"schemaVersion":1}'):
            self.assertEqual(bridge.assess(data)['reason'],'invalid_request')

    def test_capture_states_do_not_run_model(self):
        for value,reason in ((0,'silence'),(32767,'clipping')):
            with patch.object(bridge,'run_isolated',side_effect=AssertionError('must not run')):
                result=bridge.assess(raw(request(value)))
            self.assertEqual(result['reason'],reason); self.assertIsNotNone(result['captureMetrics'])
        r=request(); r['audioBase64']=base64.b64encode(wav(count=64001)).decode()
        self.assertEqual(bridge.assess(raw(r))['reason'],'audio_too_long')

    def test_response_binding_and_no_eligibility(self):
        data=raw(request(0)); response=bridge.assess(data)
        import hashlib
        self.assertEqual(response['binding']['requestSha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(response['binding']['attemptId'],request()['attemptId'])
        self.assertEqual(response['binding']['audioSha256'],hashlib.sha256(wav(0)).hexdigest())
        self.assertTrue(response['researchOnly'])
        for f in ('learnerFeedbackEligible','clinicalUseEligible','productionUseEligible'): self.assertIs(response[f],False)
        self.assertEqual(response['targets'],[]); self.assertEqual(response['promptMatch'],'unverified')

    def test_failure_cleanup_and_private_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(bridge,'TEMP_ROOT',Path(temp)), patch.object(bridge,'_launch_worker',side_effect=RuntimeError('/private/secret')):
                response=bridge.assess(raw(request()))
            self.assertEqual(list(Path(temp).iterdir()),[])
            self.assertEqual(response['reason'],'inference_failed')
            self.assertNotIn('/private',json.dumps(response))

    def test_nonfinite_model_output_rejected(self):
        payload={'targets':[{**target, 'subjectiveCorpusRatingProbabilities':[0.1,0.2,0.7]}
                            for target in request()['prompt']['targets']],
                 'model':{'id':'ages-6-12-research-mixture','manifestSha256':bridge.MANIFEST_SHA}}
        self.assertEqual(bridge.checked_result(payload, request()), payload)
        payload['targets'][0]['subjectiveCorpusRatingProbabilities']=[float('nan'),0,1]
        with patch.object(bridge,'run_isolated',return_value=payload):
            self.assertEqual(bridge.assess(raw(request()))['reason'],'inference_failed')


class NetworkTests(unittest.TestCase):
    def test_loopback_host_and_origin_boundaries(self):
        from consumer_assessment.service import acceptable_headers
        ok={'Host':'127.0.0.1:8765','Content-Type':'application/json','Content-Length':'42'}
        self.assertIsNone(acceptable_headers(ok,8765))
        for extra in ({'Origin':'null'},{'Host':'evil.example:8765'},{'Host':'127.0.0.1:80'},
                      {'Content-Type':'text/plain'},{'Content-Length':str(bridge.MAX_BODY+1)},
                      {'Transfer-Encoding':'chunked'}):
            self.assertIsNotNone(acceptable_headers({**ok,**extra},8765))


class LifecycleTests(unittest.TestCase):
    def test_timeout_kills_worker_group_and_cleans_artifacts(self):
        import subprocess
        real_popen=subprocess.Popen
        created=[]
        def sleeper(*args,**kwargs):
            import sys
            child=real_popen([sys.executable,'-c','import time; time.sleep(30)'],
                             start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            created.append(child); return child
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(bridge,'TEMP_ROOT',Path(temp)),patch.object(bridge,'TIMEOUT_SECONDS',0.05),patch.object(bridge,'_launch_worker',side_effect=sleeper):
                response=bridge.assess(raw(request()))
            self.assertEqual(response['reason'],'timeout')
            self.assertEqual(created[0].returncode,-9)
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_corrupt_bundle_fails_pinned_loader(self):
        import shutil
        from consumer_assessment.worker import BUNDLE
        from ages_6_12_bundle.inference import load_bundle
        with tempfile.TemporaryDirectory() as temp:
            bundle=Path(temp)/'bundle'; shutil.copytree(BUNDLE,bundle)
            (bundle/'scalar.pt').write_bytes(b'corrupt checkpoint')
            with self.assertRaises(ValueError): load_bundle(bundle,bridge.MANIFEST_SHA)

    def test_http_real_binding_private_headers_and_busy(self):
        import hashlib
        import http.client
        import threading
        from consumer_assessment.service import LocalServer
        with LocalServer(0) as server:
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.01}); thread.start()
            def send(data,extra=None):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
                headers={'Content-Type':'application/json',**(extra or {})}
                conn.request('POST','/v1/assessment',body=data,headers=headers)
                response=conn.getresponse(); body=json.loads(response.read()); hdr=dict(response.getheaders()); status=response.status
                conn.close(); return status,body,hdr
            try:
                data=raw(request(0)); status,body,headers=send(data)
                self.assertEqual(status,200); self.assertEqual(body['reason'],'silence')
                self.assertEqual(body['binding']['requestSha256'],hashlib.sha256(data).hexdigest())
                self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertNotIn('Access-Control-Allow-Origin',headers)
                for extra,code in (({'Origin':'null'},403),({'Host':'evil.example'},403),({'Content-Type':'text/plain'},415)):
                    self.assertEqual(send(data,extra)[0],code)
                server.inference_slot.acquire()
                try:
                    status,body,_=send(data)
                    self.assertEqual(status,429); self.assertEqual(body['binding']['attemptId'],request()['attemptId'])
                finally: server.inference_slot.release()
            finally:
                server.shutdown(); thread.join(timeout=2)


class ContainerTests(unittest.TestCase):
    def test_duplicate_data_and_inconsistent_byte_rate_are_invalid(self):
        import struct
        source=wav()
        bad_rate=bytearray(source);bad_rate[28:32]=struct.pack('<I',1)
        duplicate=bytearray(source+b'data'+struct.pack('<I',2)+b'\x00\x00')
        duplicate[4:8]=struct.pack('<I',len(duplicate)-8)
        for value in (bad_rate,duplicate):
            r=request();r['audioBase64']=base64.b64encode(value).decode()
            self.assertEqual(bridge.assess(raw(r))['reason'],'invalid_audio')

    def test_valid_response_targets_must_bind_original_order(self):
        r=request()
        good={'targets':[{**t,'subjectiveCorpusRatingProbabilities':[0.1,0.2,0.7]} for t in r['prompt']['targets']],
              'model':{'id':'ages-6-12-research-mixture','manifestSha256':bridge.MANIFEST_SHA}}
        with patch.object(bridge,'run_isolated',return_value=good):
            result=bridge.assess(raw(r));self.assertEqual(result['outcome'],'processed')
        good['targets'].reverse()
        with patch.object(bridge,'run_isolated',return_value=good):
            self.assertEqual(bridge.assess(raw(r))['reason'],'inference_failed')


class FixtureTests(unittest.TestCase):
    def test_checked_in_silence_fixture_binding_and_contract_fields(self):
        fixtures=Path(__file__).parent/'fixtures'
        data=(fixtures/'silence-request.json').read_bytes()
        expected=json.loads((fixtures/'silence-response.json').read_bytes())
        actual=bridge.assess(data);actual['timingMilliseconds']={'total':0,'inference':0}
        self.assertEqual(actual,expected)
        contract=json.loads((Path(__file__).parent/'contract.json').read_text())
        self.assertEqual(set(actual),set(contract['$defs']['response']['required']))
        self.assertEqual(set(bridge.prepare(data).request),set(contract['$defs']['request']['required']))
