"""Local preparation commands. No media or participant import operations."""

import argparse
import json
import sys

from .evidence import check_evidence, evidence_template, import_preparation_export
from .packet import PacketError, compile_packet, strict_json
from .private_io import FileError, create_root, read_private, write_private
from .validation import validation_draft


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def fixed_packet():
    # The compiler owns the only fixed source path, including its byte pin.
    from .packet import load_pack_bytes
    return compile_packet(load_pack_bytes())


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise FileError('invalid_arguments')


def main(argv=None):
    parser = SafeParser(prog='content_review', description='Public content preparation; no qualified approval')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='Create a new private packet directory')
    build.add_argument('new_root')
    check = sub.add_parser('check', help='Check declarations, without verifying their claims')
    check.add_argument('packet')
    check.add_argument('declarations')
    inspect = sub.add_parser('inspect-export', help='Replay an engineering preparation export')
    inspect.add_argument('export')
    inspect.add_argument('new_output')
    try:
        args = parser.parse_args(argv)
        if args.command == 'build':
            from .render import render_packet
            packet = fixed_packet()
            declarations = evidence_template(packet)
            files = {
                'packet.json': encode(packet),
                'declarations.json': encode(declarations),
                'validation-draft.json': encode(validation_draft(packet)),
                'readiness.json': encode(check_evidence(packet, declarations)),
                'review-packet.html': render_packet(packet).encode('utf-8'),
            }
            root = create_root(args.new_root)
            for name, raw in files.items():
                write_private(str(root / name), raw)
            summary = {'status': 'preparation_packet_created', 'counts': packet['counts'],
                       'qualifiedApprovalEstablished': False}
        elif args.command == 'check':
            packet = strict_json(read_private(args.packet))
            declarations = strict_json(read_private(args.declarations))
            result = check_evidence(packet, declarations)
            summary = {k: result[k] for k in ('status', 'counts', 'claimLimits')}
        else:
            bundle = strict_json(read_private(args.export))
            result = import_preparation_export(fixed_packet(), bundle)
            write_private(args.new_output, encode(result))
            summary = {'status': 'preparation_history_replayed', 'sourceRevision': result['sourceRevision'],
                       'records': len(result['records']), 'replayVerified': True,
                       'authenticationEstablished': False, 'qualifiedApprovalEstablished': False}
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (PacketError, FileError) as error:
        print(json.dumps({'error': error.code}), file=sys.stderr)
        return 2
    except (OSError, ValueError, UnicodeError, RecursionError):
        print(json.dumps({'error': 'preparation_failed'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
