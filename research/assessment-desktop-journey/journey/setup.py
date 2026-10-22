"""Owner-created private accounts and controlled registered examples only."""
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import secrets
import struct
import time
import wave
from review_service.auth import AuthStore, SessionManager
from recording_access import Vault
from recording_access.files import Files
from .catalog import Catalog
from .adapter import OfflineAdapter
from .engine import Journey
from .models import JourneyError, identifier

PROJECT = 'desktop-journey'


def fixture_wave():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setparams((1,2,16000,0,'NONE','not compressed'))
        output.writeframes(b''.join(struct.pack('<h', int(2500 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
    return stream.getvalue()


def declaration(raw, name, asset, now):
    sha = hashlib.sha256(raw).hexdigest(); public = asset is not None
    evidence = asset['sourceEvidenceSha256'] if public else sha
    rights = {'status':'granted','expiresAt':now+86400,'evidenceSha256':evidence,
              'declaration': asset['attribution'] if public else 'Owner generated nonspeech engineering fixture; no participant data'}
    consent = {'status':'not_applicable_public_reference' if public else 'granted','expiresAt':now+86400,
               'evidenceSha256':evidence,'declaration':'Public license source only; no participant identity or consent established' if public else 'Invented nonspeech; no actual participant'}
    return {'schemaVersion':1,'expectedSha256':sha,
            'source':{'kind':'public_reference' if public else 'invented_fixture','description':asset['attribution'] if public else 'Generated sine nonspeech',
                      'originalSha256':asset['originalSha256'] if public else sha,'provenanceEvidenceSha256':evidence},
            'subject':{'id':name,'kind':'public_reference' if public else 'invented','ageYears':None,
                       'identityDeclaration':None,'identityEvidenceSha256':None,'consentAuthorityDeclaration':None,'consentAuthorityEvidenceSha256':None},
            'permissions':{purpose:{'rights':deepcopy(rights),'consent':deepcopy(consent)} for purpose in ('storage','review','research','inference','redistribution')},
            'retainUntil':now+86400}


def initialize(root, account_id, password, *, fixture=False, adapter=None):
    identifier(account_id)
    root = Path(root)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    auth = AuthStore.create(root); auth.add_account(account_id,password); auth.assign(account_id,PROJECT,'coordinator')
    sessions = SessionManager(auth); vault = Vault.create(root,sessions,PROJECT)
    catalog = Catalog(); inventory=[]; now=int(time.time())
    for word, asset in sorted(catalog.assets.items()):
        raw=catalog.reference(word); record=vault.import_recording(raw,declaration(raw,'public-'+word,asset,now))
        inventory.append({'id':secrets.token_hex(12),'recordingId':record['recordingId'],'sha256':record['sha256'],
                          'label':asset['word']+' — licensed public example','kind':'public_reference','sourceWord':word,'ageKnown':False})
    raw=fixture_wave(); record=vault.import_recording(raw,declaration(raw,'generated-nonspeech',None,now))
    inventory.append({'id':secrets.token_hex(12),'recordingId':record['recordingId'],'sha256':record['sha256'],
                      'label':'Generated nonspeech engineering fixture','kind':'invented_fixture','sourceWord':None,'ageKnown':False})
    engine=Journey.create(root,sessions,vault,catalog.prompts,inventory,adapter or OfflineAdapter(root),content_sha256=catalog.content_sha256)
    if fixture:
        reviewer_password=secrets.token_urlsafe(32)
        auth.add_account('reviewer',reviewer_password); auth.assign('reviewer',PROJECT,'reviewer-a')
        secret={'schemaVersion':1,'projectId':PROJECT,'coordinator':{'accountId':account_id,'password':password},
                'reviewer':{'accountId':'reviewer','password':reviewer_password},'operationalFixtureOnly':True}
        with auth.lock():
            with Files(root,auth).file(None,'fixture-credentials.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL) as fd:
                Files.write(fd,json.dumps(secret,sort_keys=True).encode('utf-8')+b'\n')
    return engine,catalog


def reopen(root):
    auth=AuthStore(root); sessions=SessionManager(auth); vault=Vault.open(root,sessions)
    catalog=Catalog(); engine=Journey.open(root,sessions,vault,OfflineAdapter(root))
    if engine.header['contentSha256'] != catalog.content_sha256: raise JourneyError('catalog_unavailable')
    return engine,catalog
