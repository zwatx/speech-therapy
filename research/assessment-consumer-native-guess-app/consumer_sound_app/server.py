"""API-only sound handler over the isolated word-guess executor."""
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from journey.catalog import read_owned
from consumer_app.server import Handler as WordHandler,Server as WordServer
from . import contract as c
from .service import SoundService
class Handler(WordHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path!='/api/sound-declaration':return super().do_GET()
        try:self._guard()
        except (ValueError,TypeError):return self._reply(403,{'error':'invalid_request'})
        return self._reply(200,self.server.sound.declaration())
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
    def __init__(self,executor,catalog,worker,observer,sound_source_check,port=8795,**word_options):
        sound=SoundService(executor,catalog,worker,observer,sound_source_check,csrf_token=secrets.token_hex(32))
        super().__init__(executor,catalog,port,**word_options)
        sound.csrf_token=self.csrf_token
        self.sound=sound
        self.RequestHandlerClass=Handler
