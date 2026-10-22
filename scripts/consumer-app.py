#!/usr/bin/env python3
"""Launch the local practice app using its existing, pinned offline dependencies."""
import argparse
import errno
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    'assessment-consumer-app', 'assessment-mobile-admission', 'assessment-admission',
    'assessment-desktop-journey', 'assessment-reference-assets', 'assessment-recording-access',
    'assessment-review-service', 'assessment-workbench', 'audio-head',
)

def main():
    parser = argparse.ArgumentParser(description='Start the local speech recording and practice app.')
    parser.add_argument('--port', type=int, default=8782, help='Local port (default: 8782).')
    parser.add_argument('--check', action='store_true', help='Check the installed setup without starting a server or models.')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    sys.path[:0] = [str(ROOT / 'research' / name) for name in MODULES]
    try:
        from admission.models import readiness
        from consumer_app.catalog import Catalog
        from consumer_app.feedback import FeedbackExecutor, source_snapshot
        from consumer_app.server import Server
        from mobile_admission.service import PYTHON
        source_snapshot()
        catalog = Catalog()
        if not PYTHON.is_file():
            print('The offline speech runtime is missing. See the local setup guide.', file=sys.stderr)
            return 1
        models_ready = readiness()['ready']
        if args.check:
            print('App sources and word catalog verified.')
            print('Pinned offline speech models ready.' if models_ready else 'Speech models unavailable; recording and mirror still work.')
            return 0 if models_ready else 1
        executor = FeedbackExecutor()
        try:
            with Server(executor, catalog, args.port) as server:
                print(f'Speech practice: {server.origin}/', flush=True)
                if not models_ready:
                    print('Word checking is unavailable. Recording and mirror are available.', flush=True)
                print('Microphone and camera stay off until you choose them. Press Control-C to stop.', flush=True)
                try:
                    server.serve_forever(poll_interval=0.25)
                except KeyboardInterrupt:
                    pass
        finally:
            executor.close()
    except ImportError:
        print('An app dependency is missing. See the local setup guide.', file=sys.stderr)
        return 1
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            print(f'Port {args.port} is already in use. Open the running app or choose another port.', file=sys.stderr)
        elif error.errno in (errno.EAGAIN, errno.EACCES):
            print('Another app owns the local runtime, or its files need owner review.', file=sys.stderr)
        else:
            print('The local app could not start. Its saved verification evidence remains intact.', file=sys.stderr)
        return 1
    except ValueError:
        print('The app setup could not be verified. Its saved evidence has been preserved.', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
