"""Fixed stdin envelope used only by the owner-launched offline adapter."""
import base64
import json
import os
from pathlib import Path
import sys
import admission

def main():
    raw=sys.stdin.buffer.read(200001)
    if len(raw)>200000:raise ValueError('bounded_request')
    request=json.loads(raw.decode('utf-8'))
    if type(request) is not dict or set(request)!=set(('audioBase64','prompt','ageYears')):raise ValueError('bounded_request')
    from admission import adapter
    stage=Path(sys.argv[1]).resolve()
    if not stage.is_dir() or stage.stat().st_uid != os.getuid() or stage.stat().st_mode & 0o777 != 0o700:raise ValueError('private_stage')
    adapter.WORK=stage
    result=admission.assess(base64.b64decode(request['audioBase64'],validate=True),request['prompt'],age_years=request['ageYears'])
    raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False,ensure_ascii=False).encode('utf-8')
    if len(raw)>65536:raise ValueError('bounded_result')
    fd=os.open(Path(sys.argv[1])/'result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        remaining=memoryview(raw)
        while remaining:
            count=os.write(fd,remaining);remaining=remaining[count:]
        os.fsync(fd)
    finally:os.close(fd)
if __name__=='__main__':main()
