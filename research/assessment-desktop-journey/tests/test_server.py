"""Real loopback transport, sessions, filesystem; injected result only in unit seam."""
import http.client
import json
import threading
import unittest
import test_engine
from journey.server import Server

class PublicCatalogUnit:
    def projection(self):return {'schemaVersion':1,'prompts':[],'claimLimits':{'clinicalUseEligible':False}}
    def reference(self,word):
        if word!='rabbit':raise ValueError('missing')
        return b'unit-public-audio'
    def illustration(self,word):return b'<svg xmlns="http://www.w3.org/2000/svg"/>'

class TransportTests(unittest.TestCase):
    # Inherit real private root setup only, without rerunning engine tests.
    def setUp(self):
        test_engine.JourneyTests.setUp(self);self.server=Server(self.engine,PublicCatalogUnit(),port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(lambda:self.thread.join(2));self.addCleanup(self.server.shutdown)
        self.cookie=None;self.web_csrf=None
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        try:
            supplied={'Host':self.server.origin.removeprefix('http://')}
            if self.cookie:supplied['Cookie']=self.cookie
            if method=='POST':supplied.update({'Origin':self.server.origin,'Content-Type':'application/json','X-Journey-CSRF':self.web_csrf or ''})
            supplied.update(headers or {})
            raw=json.dumps(body).encode() if body is not None else None
            connection.request(method,path,raw,supplied);response=connection.getresponse();data=response.read()
            cookie=response.getheader('Set-Cookie')
            if cookie:self.cookie=cookie.split(';')[0]
            return response.status,response.getheader('Content-Type'),json.loads(data) if response.getheader('Content-Type','').startswith('application/json') else data
        finally:connection.close()
    def test_anonymous_catalog_reference_and_protected_history(self):
        self.assertEqual(self.request('GET','/api/catalog')[0],200)
        self.assertEqual(self.request('GET','/api/public-references/rabbit')[2],b'unit-public-audio')
        self.assertEqual(self.request('GET','/api/state')[0],401)
    def test_login_private_start_poll_practice_clear_logout(self):
        status,_,public=self.request('GET','/api/session');self.assertEqual(status,200);self.web_csrf=public['csrfToken']
        status,_,public=self.request('POST','/api/login',{'accountId':'operator','password':self.password});self.assertEqual(status,200);self.web_csrf=public['csrfToken']
        status,_,started=self.request('POST','/api/assessments',{'idempotencyKey':'web-a','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None});self.assertEqual(status,202)
        self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(self.request('GET','/api/attempts/'+started['attemptId'])[2]['status'],'available')
        self.assertEqual(self.request('POST','/api/practice',{'idempotencyKey':'web-practice','promptId':'rabbit-r','attemptId':started['attemptId']})[0],200)
        self.assertEqual(self.request('POST','/api/history/clear',{'idempotencyKey':'web-clear'})[0],200)
        self.assertEqual(self.request('GET','/api/export')[2]['history'][0]['status'],'forgotten')
        self.assertEqual(self.request('POST','/api/logout',{})[0],200)
        self.assertEqual(self.request('GET','/api/history')[0],401)
    def test_cross_origin_csrf_path_and_range_are_rejected(self):
        _,_,public=self.request('GET','/api/session');self.web_csrf=public['csrfToken']
        self.assertEqual(self.request('POST','/api/login',{'accountId':'operator','password':self.password},{'Origin':'http://evil.example'})[0],400)
        self.assertEqual(self.request('POST','/api/login',{'accountId':'operator','password':self.password},{'X-Journey-CSRF':'x'})[0],403)
        self.assertEqual(self.request('GET','/api/public-references/rabbit',headers={'Range':'bytes=0-1'})[0],400)
        self.assertEqual(self.request('GET','/api/public-references/%2e%2e')[0],400)


    def test_private_full_audio_requires_current_session_and_csrf(self):
        _,_,public=self.request('GET','/api/session');self.web_csrf=public['csrfToken']
        _,_,public=self.request('POST','/api/login',{'accountId':'operator','password':self.password});self.web_csrf=public['csrfToken']
        route='/api/references/'+'a'*24
        self.assertEqual(self.request('GET',route)[0],403)
        status,media,raw=self.request('GET',route,headers={'X-Journey-CSRF':self.web_csrf})
        self.assertEqual(status,200);self.assertEqual(media,'audio/wav');self.assertEqual(raw,self.raw)
        self.vault.withdraw_subject(self.token,self.csrf,'invented-source','owner_withdrawal')
        self.assertEqual(self.request('GET',route,headers={'X-Journey-CSRF':self.web_csrf})[0],404)
        self.assertEqual(self.request('GET','/api/public-references/rabbit')[2],b'unit-public-audio')
