"""Source-bound browser resources over the isolated word-guess executor."""
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from journey.catalog import read_owned
from consumer_app.server import Handler as WordHandler,Server as WordServer
from . import contract as c
from .service import SoundService
UI=Path(__file__).resolve().parents[1]/'ui'
STATIC={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),
    '/styles.css':('styles.css','text/css; charset=utf-8'),'/audio-capture.js':('audio-capture.js','text/javascript; charset=utf-8'),
    '/visual-worker.js':('visual-worker.js','text/javascript; charset=utf-8'),
    '/visual-runtime.js':('visual-runtime.js','text/javascript; charset=utf-8')}
class Handler(WordHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path not in STATIC and path!='/api/sound-declaration':return super().do_GET()
        try:self._guard()
        except (ValueError,TypeError):return self._reply(403,{'error':'invalid_request'})
        if path=='/api/sound-declaration':return self._reply(200,self.server.sound.declaration())
        name,kind=STATIC[path]
        try:raw=self._resource_value(lambda:read_owned(UI/name,1024*1024))
        except (OSError,ValueError,TypeError):return self._reply(503,{'error':'resource_unavailable'})
        return self._reply(200,raw,kind)
    def do_POST(self):
        path=urlsplit(self.path).path
        if path not in ('/api/sound-observation','/api/sound-reset','/api/sound-cancel'):return super().do_POST()
        try:self._guard(post=True)
        except (ValueError,TypeError):return self._reply(403,{'error':'invalid_request'})
        try:
            length=self._one('Content-Length')
            c.need(type(length) is str and length.isdigit() and 0<int(length)<=c.MAX_BODY)
            c.need(self._one('Content-Type')=='application/json')
            raw=self.rfile.read(int(length));c.need(len(raw)==int(length))
            self.deadline.cancel()
            value=(self.server.sound.execute(raw) if path.endswith('observation') else
                self.server.sound.reset(raw) if path.endswith('reset') else self.server.sound.cancel(raw))
        except (OSError,ValueError,TypeError,KeyError):return self._reply(400,{'error':'invalid_request'})
        try:self._reply(200,value)
        except (BrokenPipeError,ConnectionResetError,OSError):
            # The job has already cleaned before a reply is released. No result is retained publicly.
            return
class Server(WordServer):
    def __init__(self,executor,catalog,worker,observer,sound_source_check,port=8797,**word_options):
        sound=SoundService(executor,catalog,worker,observer,sound_source_check,csrf_token=secrets.token_hex(32))
        super().__init__(executor,catalog,port,resource_source_check=sound_source_check,**word_options)
        sound.csrf_token=self.csrf_token
        self.sound=sound
        self.RequestHandlerClass=Handler
