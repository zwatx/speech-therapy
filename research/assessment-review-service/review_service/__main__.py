"""Trusted OS-operator commands for the closed invented review service.

These commands run as the private service directory's owner. Export attribution
uses the current fixed fixture coordinator assignment; it does not assert a
browser password login or qualified human identity. Passwords use hidden input.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import warnings

from workbench.domain import ValidationError
from workbench.store import verify_export

from .auth import AuthStore
from .engine import Service, create_fixture_service


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error includes rejected arguments, possibly secrets.
        raise ValidationError('command_arguments')

def _parser():
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
    create = commands.add_parser('create-fixture', help='Create the closed invented service in a fresh directory')
    create.add_argument('root')
    verify = commands.add_parser('verify-service', help='Reconcile both source histories and report safe counts')
    verify.add_argument('root')
    export = commands.add_parser('export', help='Trusted operator export through the current fixture coordinator')
    export.add_argument('root')
    export.add_argument('project')
    export.add_argument('output')
    audit = commands.add_parser('audit-export', help='Export the separate validated private attribution journal')
    audit.add_argument('root')
    audit.add_argument('output')
    serve = commands.add_parser('serve', help='Start the authenticated fixture browser on loopback only')
    serve.add_argument('root')
    serve.add_argument('--port', type=int, default=8772)
    for name in ('reset-password', 'revoke-account', 'deactivate-assignment'):
        command = commands.add_parser(name, help='Trusted operator credential/assignment administration')
        command.add_argument('root')
        command.add_argument('account')
        if name == 'deactivate-assignment':
            command.add_argument('project')
    return parser

def _emit(value):
    print(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False), flush=True)


def _write_private(output, payload):
    path = Path(os.path.abspath(output))
    try:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValidationError('unsafe_output_directory') from error
    try:
        info = os.fstat(directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValidationError('unsafe_output_directory')
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2).encode('utf-8') + b'\n'
        try:
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                         0o600, dir_fd=directory)
        except FileExistsError as error:
            raise ValidationError('private_output_exists') from error
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ValidationError('unsafe_output_file')
            remaining = memoryview(encoded)
            while remaining:
                count = os.write(fd, remaining)
                if count <= 0:
                    raise OSError('private_write_failed')
                remaining = remaining[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(directory)

def _operator_actor(service):
    # The OS owner command deliberately uses the closed fixture coordinator slot.
    # Only its current active generation leaves private registry implementation state.
    registry, _, _ = service.auth._read()
    account = registry['accounts'].get('fixture-coordinator')
    if not account or not account['active']:
        raise ValidationError('authorization_required')
    return {'accountId': 'fixture-coordinator', 'generation': account['generation']}

def _verify(service):
    with service.auth.lock():
        receipt = service._reconcile()
        projects = []
        for project, store in sorted(service.stores.items()):
            manifest = store.manifest
            projects.append({'id': project, 'revision': store.revision,
                             'attempts': len(manifest['attempts']), 'participants': len(manifest['participants']),
                             'prompts': len(manifest['prompts'])})
        return {**receipt, 'trustedOperator': True, 'projects': projects}


def _new_password():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('New password: ')
            confirmation = getpass.getpass('Confirm password: ')
    except getpass.GetPassWarning as error:
        raise ValidationError('hidden_password_input_required') from error
    try:
        confirmed = secrets.compare_digest(password.encode('utf-8'), confirmation.encode('utf-8'))
    except UnicodeError as error:
        raise ValidationError('invalid_password') from error
    if not confirmed:
        raise ValidationError('password_confirmation_mismatch')
    return password

def main(argv=None):
    try:
        arguments = _parser().parse_args(argv)
        if arguments.command == 'create-fixture':
            create_fixture_service(arguments.root)
            _emit({'created': True, 'projects': 2, 'syntheticOnly': True, 'credentialsPrinted': False})
        elif arguments.command == 'verify-service':
            _emit(_verify(Service.open(arguments.root)))
        elif arguments.command == 'export':
            service = Service.open(arguments.root)
            with service.auth.lock():
                bundle = service.export(_operator_actor(service), arguments.project)
                receipt = verify_export(bundle)
                _write_private(arguments.output, bundle)
            _emit({**receipt, 'written': True, 'trustedOperator': True})
        elif arguments.command == 'audit-export':
            service = Service.open(arguments.root)
            with service.auth.lock():
                service._reconcile()
                payload = {'schemaVersion': 1, 'trustedOperator': True, 'authenticityEstablished': False,
                           'records': service.audit.records()}
                _write_private(arguments.output, payload)
            _emit({'written': True, 'records': len(payload['records']), 'trustedOperator': True})
        elif arguments.command == 'serve':
            if not 0 <= arguments.port <= 65535:
                raise ValidationError('command_arguments')
            from .server import make_server
            with make_server(Service.open(arguments.root), port=arguments.port) as server:
                _emit({'url': 'http://127.0.0.1:' + str(server.server_address[1]),
                       'syntheticOnly': True, 'authenticatedAccountsRequired': True})
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        else:
            auth = AuthStore.open(arguments.root)
            password = _new_password() if arguments.command == 'reset-password' else None
            with auth.lock():
                if arguments.command == 'reset-password':
                    auth.reset_password(arguments.account, password)
                elif arguments.command == 'revoke-account':
                    auth.revoke_account(arguments.account)
                else:
                    auth.deactivate_assignment(arguments.account, arguments.project)
            _emit({'updated': True, 'trustedOperator': True})
        return 0
    except ValidationError as error:
        print(error.code, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('operator_input_cancelled', file=sys.stderr)
        return 130
    except EOFError:
        print('operator_input_cancelled', file=sys.stderr)
        return 1
    except OSError:
        print('operator_io_error', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
