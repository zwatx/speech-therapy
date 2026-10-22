"""Trusted local worker; writes only the bounded public projection."""
import os
import sys
from pathlib import Path
from .contract import MAX_BODY, canonical, prepare, project, verify_sources


def main():
    verify_sources()
    raw = sys.stdin.buffer.read(MAX_BODY + 1)
    request, audio = prepare(raw)
    from admission import adapter
    # Runtime-only staging overlay inside this isolated process. Frozen source and
    # admission/model policy are unchanged; all nested private files belong here.
    adapter.WORK = Path(sys.argv[1])
    result = project(adapter.assess(audio, request['prompt'], request['ageYears']), raw, request, audio)
    fd = os.open(Path(sys.argv[1]) / 'result.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output: output.write(canonical(result))


if __name__ == '__main__': main()
