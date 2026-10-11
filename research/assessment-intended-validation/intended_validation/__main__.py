"""Trusted-owner private preparation/report CLI; no media or network access."""
import argparse
import json
from pathlib import Path
from content_review.packet import strict_json
from content_review.private_io import read_private, write_private, create_root
from . import ProtocolError, make_protocol_v2, blank_bundle, build_report
from workbench.domain import semantic_digest

def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()

class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ProtocolError('invalid_command')

def main():
    parser = SafeParser(prog='intended-validation')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('prepare')
    init.add_argument('destination'); init.add_argument('model_manifest_sha256'); init.add_argument('admission_policy_sha256')
    report = sub.add_parser('report')
    report.add_argument('protocol'); report.add_argument('bundle'); report.add_argument('destination')
    try:
        args = parser.parse_args()
        if args.command == 'prepare':
            protocol = make_protocol(args.model_manifest_sha256, args.admission_policy_sha256, semantic_digest([]), semantic_digest([]))
            root = Path(args.destination)
            create_root(str(root))
            write_private(str(root / 'protocol.json'), encode(protocol))
            write_private(str(root / 'observations.json'), encode(blank_bundle(protocol)))
            write_private(str(root / 'preparation-report.json'), encode(build_report(protocol, blank_bundle(protocol))))
            print(json.dumps({'prepared': True, 'collectedParticipants': 0, 'engineeringCriteriaMet': False}))
        else:
            result = build_report(strict_json(read_private(args.protocol)), strict_json(read_private(args.bundle)))
            write_private(args.destination, encode(result))
            print(json.dumps({'reported': True, 'attempts': result['allAttemptDenominators']['attempts'], 'engineeringCriteriaMet': result['engineeringCriteriaMet']}))
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as error:
        code = str(error) if isinstance(error, ProtocolError) else 'private_input_or_output_unavailable'
        print(json.dumps({'error': code})); return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
