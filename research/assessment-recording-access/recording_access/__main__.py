"""Explicit trusted local operator setup; protected operations use real sessions."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import stat
import sys

from review_service.auth import AuthStore, SessionManager
from workbench.domain import ValidationError
from . import Vault, VaultError, inspect_wav
from .models import MAX_JSON_BYTES, MAX_WAV_BYTES, strict_json, identifier


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise VaultError('invalid_command')


def private_directory(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise VaultError('unsafe_operator_directory') from None
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise VaultError('unsafe_operator_directory')
    return fd


def operator_read(path, maximum):
    path = Path(os.path.abspath(path))
    directory = private_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > maximum):
                raise VaultError('unsafe_operator_file')
            from .files import Files
            return Files.read(fd, maximum)
        finally:
            os.close(fd)
    except OSError:
        raise VaultError('unsafe_operator_file') from None
    finally:
        os.close(directory)


def operator_write(path, value):
    path = Path(os.path.abspath(path))
    directory = private_directory(path.parent)
    try:
        raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode('utf-8') + b'\n'
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
        try:
            from .files import Files
            Files.write(fd, raw)
        finally:
            os.close(fd)
        os.fsync(directory)
    except OSError:
        raise VaultError('operator_output_unavailable') from None
    finally:
        os.close(directory)


def parser():
    result = Parser(description='Private recording access: trusted local operator, no HTTP service')
    sub = result.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('root')
    init.add_argument('project')
    imp = sub.add_parser('import')
    imp.add_argument('root')
    imp.add_argument('wav')
    imp.add_argument('declaration')
    for name in ('reconcile',):
        sub.add_parser(name).add_argument('root')
    for name in ('purge-report', 'orphan-report'):
        command = sub.add_parser(name)
        command.add_argument('root')
        command.add_argument('output')
    for name in ('purge', 'purge-orphans'):
        command = sub.add_parser(name)
        command.add_argument('root')
        command.add_argument('plan')
    for name in ('read-check', 'export-metadata', 'restrict', 'withdraw'):
        command = sub.add_parser(name)
        command.add_argument('root')
        command.add_argument('account')
        if name == 'export-metadata':
            command.add_argument('output')
        else:
            command.add_argument('recording' if name != 'withdraw' else 'subject')
            if name != 'withdraw':
                command.add_argument('purpose', choices=('storage', 'review', 'research', 'inference', 'redistribution'))
            if name != 'read-check':
                command.add_argument('reason')
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        if args.command == 'init':
            identifier(args.project)
            root = Path(os.path.abspath(args.root))
            directory = private_directory(root.parent)
            try:
                os.mkdir(root.name, 0o700, dir_fd=directory)
                os.fsync(directory)
            finally:
                os.close(directory)
            auth = AuthStore.create(root)
            accounts = []
            for role in ('coordinator', 'reviewer-a', 'reviewer-b', 'adjudicator'):
                account = 'invented-' + role
                password = secrets.token_urlsafe(32)
                auth.add_account(account, password)
                auth.assign(account, args.project, role)
                accounts.append({'accountId': account, 'password': password, 'role': role})
            operator_write(root / 'fixture-credentials.json', {'schemaVersion': 1, 'inventedAccountsOnly': True, 'accounts': accounts})
            Vault.create(root, SessionManager(auth), args.project)
            outcome = {'created': True, 'inventedAccounts': 4, 'recordings': 0}
        else:
            auth = AuthStore.open(args.root)
            sessions = SessionManager(auth)
            maintenance = args.command in ('purge-report', 'purge', 'orphan-report', 'purge-orphans', 'restrict', 'withdraw')
            vault = (Vault.open_maintenance if maintenance else Vault.open)(args.root, sessions)
            if args.command == 'import':
                outcome = vault.import_recording(operator_read(args.wav, MAX_WAV_BYTES), strict_json(operator_read(args.declaration, MAX_JSON_BYTES)))
            elif args.command == 'reconcile':
                outcome = vault.reconcile()
            elif args.command in ('purge-report', 'orphan-report'):
                plan = vault.purge_report() if args.command == 'purge-report' else vault.orphan_report()
                operator_write(args.output, plan)
                outcome = {'dryRun': True, 'eligibleCopies': len(plan['eligible']), 'planSha256': plan['planSha256']}
            elif args.command in ('purge', 'purge-orphans'):
                plan = strict_json(operator_read(args.plan, MAX_JSON_BYTES))
                outcome = vault.purge(plan) if args.command == 'purge' else vault.purge_orphans(plan)
            else:
                password = getpass.getpass('Local account password: ')
                token, _ = sessions.bootstrap()
                token, public = sessions.login(token, args.account, password)
                del password
                csrf = public['csrfToken']
                try:
                    if args.command == 'read-check':
                        outcome = inspect_wav(vault.read_recording(token, csrf, args.recording, args.purpose))
                    elif args.command == 'export-metadata':
                        exported = vault.export_metadata(token, csrf)
                        operator_write(args.output, exported)
                        outcome = {'exported': True, 'revision': exported['revision'], 'counts': exported['counts']}
                    elif args.command == 'restrict':
                        outcome = vault.restrict(token, csrf, args.recording, args.purpose, args.reason)
                    else:
                        outcome = vault.withdraw_subject(token, csrf, args.subject, args.reason)
                finally:
                    sessions.logout(token)
        print(json.dumps(outcome, sort_keys=True, allow_nan=False))
        return 0
    except ValidationError as error:
        print(error.code, file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print('operator_operation_unavailable', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
