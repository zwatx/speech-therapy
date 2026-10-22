"""Small shared integrity helpers; no model or framework imports."""
import hashlib
import json
from pathlib import Path

HEAD = Path(__file__).resolve().parents[1]
ROOT = HEAD.parents[1]
BASE = HEAD/'outputs/multiphone-20260927'
OUTPUT = BASE/'yamnet-speech-v1'
PROTOCOL = ROOT/'docs/model/yamnet-speech-protocol.md'
FLAGS = dict(trainingPerformed=False, authorTestRead=False, clinicalUseEligible=False,
             learnerFeedbackEligible=False, promotionEligible=False, researchOnly=True)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    return dict(path=str(Path(path).resolve()), sha256=sha(path))


def guard(binding):
    require(sha(binding['path']) == binding['sha256'], 'Changed input: '+binding['path'])


def read(binding):
    guard(binding)
    return json.loads(Path(binding['path']).read_text())


def write(path, value):
    import os
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
