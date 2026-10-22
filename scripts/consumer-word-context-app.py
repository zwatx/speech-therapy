#!/usr/bin/env python3
"""Launch only the staged declared-context word app; checks never read model weights."""
import argparse
import errno
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'research/assessment-consumer-word-context-app'
MODULES = (
    'assessment-mobile-admission', 'assessment-admission', 'assessment-desktop-journey',
    'assessment-reference-assets', 'assessment-recording-access', 'assessment-review-service',
    'assessment-workbench', 'audio-head',
)
DEFAULT_RUNTIME = ROOT / 'work/consumer-feedback-20261007/adult-word-context/runtime'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run the declared-context word practice successor.')
    parser.add_argument('--port', type=int, default=8791)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--check', action='store_true', help='Verify source/catalog metadata without models or a listener.')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or args.port in (8782, 8788, 8789):
        parser.error('Choose a separate successor port; existing app ports are reserved.')
    sys.path[:0] = [str(PACKAGE), *(str(ROOT / 'research' / name) for name in MODULES)]
    try:
        import consumer_app
        from consumer_app.catalog import Catalog
        from consumer_app.feedback import FeedbackExecutor, source_snapshot
        from consumer_app.server import Server
        from mobile_admission.service import PYTHON
        if Path(consumer_app.__file__).resolve().parent != PACKAGE / 'consumer_app':
            raise ValueError('wrong_consumer_package')
        source_snapshot()
        if not PYTHON.is_file():
            raise ValueError('dependency_unavailable')
        if args.check:
            print('Successor package and source/context bindings verified. No model or runtime started.')
            return 0
        catalog = Catalog()
        executor = FeedbackExecutor(args.runtime)
        try:
            with Server(executor, catalog, args.port) as server:
                print(f'Declared-context word practice: {server.origin}/', flush=True)
                try:
                    server.serve_forever(poll_interval=0.25)
                except KeyboardInterrupt:
                    pass
        finally:
            executor.close()
    except ImportError:
        print('A reviewed dependency is unavailable.', file=sys.stderr)
        return 1
    except OSError as error:
        message = 'The successor port is already in use.' if error.errno == errno.EADDRINUSE else 'The successor could not open its owned resources.'
        print(message, file=sys.stderr)
        return 1
    except ValueError:
        print('The successor source or dependency binding could not be verified.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
