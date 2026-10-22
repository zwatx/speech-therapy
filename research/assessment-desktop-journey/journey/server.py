"""Loopback-only bounded transport for anonymous examples and private engineering flow."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from recording_access.models import strict_json
from workbench.domain import ValidationError
from .catalog import read_owned
from .models import JourneyError, exact

UI = Path(__file__).resolve().parents[1] / 'ui'
COOKIE = 'journey_session'
MAX_BODY = 32768


class Server(HTTPServer):
    def __init__(self, engine, catalog, port=8780):
        if type(port) is not int or not 0 <= port <= 65535: raise JourneyError('invalid_port')
        self.engine,self.catalog=engine,catalog
        super().__init__(('127.0.0.1',port),Handler)
        self.origin='http://127.0.0.1:'+str(self.server_address[1])


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    server_version='LocalJourney'
    sys_version=''
    def setup(self):
        super().setup(); self.connection.settimeout(5)
    def log_message(self,*args): pass
    def _one(self,name,optional=False):
        values=self.headers.get_all(name,[])
        if not values and optional: return None
        if len(values)!=1: raise JourneyError('invalid_request')
        return values[0]
    def _guard(self,post=False):
        if len(self.headers)>40 or self._one('Host') != self.server.origin.removeprefix('http://'):
            raise JourneyError('invalid_request')
        if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Range'):
            raise JourneyError('invalid_request')
        if self._one('Sec-Fetch-Site',True) not in (None,'same-origin','none'): raise JourneyError('invalid_request')
        origin=self._one('Origin',True)
        if origin is not None and origin != self.server.origin: raise JourneyError('invalid_request')
        if post and origin != self.server.origin: raise JourneyError('invalid_request')
        parsed=urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '%' in parsed.path or '\\' in parsed.path:
            raise JourneyError('invalid_request')
        return parsed.path
    def _token(self):
        raw=self._one('Cookie',True)
        if raw is None:return None
        fields=raw.split(';')
        values=[]
        for field in fields:
            key,separator,value=field.strip().partition('=')
            if not separator: raise JourneyError('invalid_request')
            if key==COOKIE: values.append(value)
        if len(values)>1: raise JourneyError('invalid_request')
        return values[0] if values else None
    def _reply(self,status,value,*,media='application/json; charset=utf-8',cookie=None):
        raw=value if type(value) is bytes else json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',media); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if cookie is not None:self.send_header('Set-Cookie',COOKIE+'='+cookie+'; HttpOnly; SameSite=Strict; Path=/'+('; Max-Age=0' if cookie=='' else ''))
        self.end_headers(); self.wfile.write(raw)
    def _error(self,error):
        code=error.code if isinstance(error,ValidationError) else 'journey_unavailable'
        status=401 if code in ('authentication_required','session_expired','invalid_credentials') else 403 if code in ('authorization_required','csrf_required','authorization_changed') else 404 if code in ('unknown_attempt','recording_unavailable','not_found') else 409 if code in ('idempotency_conflict','assessment_busy','attempt_finished','repeat_unavailable','pipeline_changed','journey_capacity') else 400
        self._reply(status,{'error':code})
    def do_GET(self):
        try:
            path=self._guard(); engine=self.server.engine; catalog=self.server.catalog
            if path=='/api/catalog':return self._reply(200,catalog.projection())
            match=re.fullmatch('/api/public-references/([a-z]+)',path)
            if match:return self._reply(200,catalog.reference(match[1]),media='audio/wav')
            match=re.fullmatch(r'/illustrations/([a-z]+)\.svg',path)
            if match:return self._reply(200,catalog.illustration(match[1]),media='image/svg+xml')
            if path in ('/','/app.js','/styles.css'):
                filename={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}[path]
                media={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/styles.css':'text/css; charset=utf-8'}[path]
                return self._reply(200,read_owned(UI/filename,1024*1024),media=media)
            with engine.auth.lock():
                token=self._token()
                if path=='/api/session':
                    token,public=engine.sessions.bootstrap(token); return self._reply(200,public,cookie=token)
                if path=='/api/state':return self._reply(200,engine.state(token))
                if path in ('/api/history','/api/export'):return self._reply(200,engine.export(token))
                match=re.fullmatch('/api/attempts/([0-9a-f]{32})',path)
                if match:return self._reply(200,engine.attempt(token,match[1]))
                match=re.fullmatch('/api/references/([0-9a-f]{24})',path)
                if match:return self._reply(200,engine.private_reference(token,self._one('X-Journey-CSRF',True),match[1]),media='audio/wav')
                raise JourneyError('not_found')
        except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
            self._error(error)
    def do_POST(self):
        try:
            path=self._guard(post=True)
            length=self._one('Content-Length')
            if re.fullmatch('[0-9]{1,5}',length) is None or not 1<=int(length)<=MAX_BODY:
                raise JourneyError('invalid_request')
            if self._one('Content-Type') not in ('application/json','application/json; charset=utf-8'):
                raise JourneyError('invalid_request')
            raw=self.rfile.read(int(length))
            if len(raw)!=int(length):raise JourneyError('invalid_request')
            body=strict_json(raw)
            engine=self.server.engine
            with engine.auth.lock():
                token=self._token();csrf=self._one('X-Journey-CSRF');engine.sessions.verify_csrf(token,csrf)
                if path=='/api/login':
                    exact(body,('accountId','password'));new,public=engine.sessions.login(token,body['accountId'],body['password'])
                    return self._reply(200,public,cookie=new)
                if path=='/api/logout':
                    exact(body,());engine.sessions.logout(token);return self._reply(200,{'ok':True},cookie='')
                if path=='/api/assessments':return self._reply(202,engine.start(token,csrf,body))
                if path=='/api/cancel':return self._reply(200,engine.cancel(token,csrf,body))
                if path=='/api/practice':return self._reply(200,engine.practice(token,csrf,body))
                if path=='/api/history/clear':return self._reply(200,engine.clear_history(token,csrf,body))
                raise JourneyError('not_found')
        except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
            self._error(error)
    def do_PUT(self):self._reply(405,{'error':'method_not_allowed'})
    do_DELETE=do_PUT;do_PATCH=do_PUT;do_OPTIONS=do_PUT;do_HEAD=do_PUT


def serve(engine,catalog,port=8780):
    with Server(engine,catalog,port) as server:
        print('Local journey: '+server.origin,flush=True)
        server.serve_forever(poll_interval=0.25)
