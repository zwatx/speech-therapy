import argparse
import json
import sys

from content_review.private_io import FileError, read_private, write_private
from content_review.packet import strict_json
from workbench.domain import semantic_digest
from .runner import RunError, prepare_plan, run_plan


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RunError('invalid_arguments')


def main(argv=None):
    parser = Parser(prog='reference_validation')
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('registry')
    prepare.add_argument('new_plan')
    run = sub.add_parser('run')
    run.add_argument('registry')
    run.add_argument('plan')
    run.add_argument('expected_sha256')
    run.add_argument('new_root')
    try:
        args = parser.parse_args(argv)
        registry = strict_json(read_private(args.registry))
        if args.command == 'prepare':
            plan = prepare_plan(registry)
            write_private(args.new_plan, (json.dumps(plan, indent=2) + '\n').encode())
            print(json.dumps({'attempts': plan['expectedAttempts'], 'planSha256': semantic_digest(plan)}))
        else:
            plan = strict_json(read_private(args.plan))
            result = run_plan(plan, registry, args.expected_sha256, args.new_root)
            print(json.dumps({k: result[k] for k in ('allAttemptDenominator', 'outcomes', 'claimLimits')}))
        return 0
    except (RunError, FileError) as error:
        print(json.dumps({'error': error.code}), file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        print(json.dumps({'error': 'validation_unavailable'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
