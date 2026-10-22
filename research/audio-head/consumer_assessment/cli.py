"""Engineering-only supplied prompt/audio bridge, with deliberate artifact export."""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
import shutil
import sys
import uuid
from consumer_assessment.bridge import assess, canonical_bytes, strict_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav',type=Path,required=True)
    parser.add_argument('--prompt',type=Path,required=True)
    parser.add_argument('--age-years',type=int,required=True)
    parser.add_argument('--attempt-id',default=None)
    parser.add_argument('--output',type=Path,help='Fresh directory for deliberate local research artifacts; never implicit overwrite')
    args=parser.parse_args()
    try:
        # Bound file reads before loading caller data.
        if args.wav.stat().st_size > 132096 or args.prompt.stat().st_size > 40000: raise ValueError('input size')
        request={'schemaVersion':1,'attemptId':args.attempt_id or str(uuid.uuid4()),'ageYears':args.age_years,
                 'prompt':strict_json(args.prompt.read_bytes()),'audioBase64':base64.b64encode(args.wav.read_bytes()).decode()}
        data=canonical_bytes(request)
        stage=None
        if args.output:
            stage=args.output.with_name(args.output.name+'.partial')
            if args.output.exists() or stage.exists(): raise ValueError('output exists')
            stage.mkdir(parents=True,mode=0o700)
        try:
            result=assess(data,artifacts=stage)
            if stage is not None:
                (stage/'request.json').write_bytes(data); (stage/'request.json').chmod(0o600)
                (stage/'response.json').write_bytes(canonical_bytes(result)); (stage/'response.json').chmod(0o600)
                stage.rename(args.output)
            print(json.dumps(result,allow_nan=False,indent=2))
        finally:
            if stage is not None and stage.exists(): shutil.rmtree(stage)
        return 0 if result['outcome']=='processed' else 2
    except Exception:
        print('Engineering input or output unavailable; no model result.',file=sys.stderr)
        return 2


if __name__ == '__main__': sys.exit(main())
