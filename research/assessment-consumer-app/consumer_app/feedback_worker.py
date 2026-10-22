"""One prompt-blind recognition call; no research-head or public private evidence."""
import os
from pathlib import Path
import sys
from mobile_admission import contract
from .feedback import source_snapshot


def main():
    stage=Path(sys.argv[1]);raw=sys.stdin.buffer.read(contract.MAX_BODY+1)
    request,audio=contract.prepare(raw)
    binding=source_snapshot()
    from admission import adapter,policy
    adapter.WORK=stage
    evidence=adapter.recognize(audio)
    decision=policy.decide(evidence,request['prompt']['transcript'])
    payload=contract.canonical({'schemaVersion':1,'binding':binding,'evidence':evidence,'decision':decision})
    if len(payload)>100000:raise ValueError('invalid_evidence')
    fd=os.open(stage/'feedback.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(payload);output.flush();os.fsync(output.fileno())


if __name__=='__main__':main()
