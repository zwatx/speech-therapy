"""Closed private descriptor-relative filesystem operations."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat

from .models import VaultError


class Files:
    def __init__(self, root, auth):
        self.root = Path(os.path.abspath(root))
        if self.root != auth.root:
            raise VaultError('auth_root_mismatch')
        with self.directory() as fd:
            info = os.fstat(fd)
            self.identity = (info.st_dev, info.st_ino)

    @contextmanager
    def directory(self, child=None):
        try:
            root = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            raise VaultError('unsafe_vault_directory') from None
        fd = root
        try:
            info = os.fstat(root)
            self._directory_info(info)
            if hasattr(self, 'identity') and (info.st_dev, info.st_ino) != self.identity:
                raise VaultError('unsafe_vault_directory')
            if child is not None:
                try:
                    fd = os.open(child, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
                except OSError:
                    raise VaultError('unsafe_vault_directory') from None
                self._directory_info(os.fstat(fd))
            yield fd
        finally:
            if fd != root:
                os.close(fd)
            os.close(root)

    @staticmethod
    def _directory_info(info):
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise VaultError('unsafe_vault_directory')

    @contextmanager
    def file(self, child, name, flags, links=(1,)):
        with self.directory(child) as directory:
            try:
                fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
            except FileExistsError:
                raise VaultError('vault_exists') from None
            except OSError:
                raise VaultError('unsafe_vault_file') from None
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink not in links):
                    raise VaultError('unsafe_vault_file')
                yield fd
            finally:
                os.close(fd)

    @staticmethod
    def read(fd, maximum):
        before = os.fstat(fd)
        if before.st_size > maximum:
            raise VaultError('unsafe_vault_file')
        chunks, remaining = [], maximum + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        attributes = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink')
        if len(raw) > maximum or any(getattr(before, field) != getattr(after, field) for field in attributes):
            raise VaultError('unsafe_vault_file')
        return raw

    @staticmethod
    def write(fd, raw):
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError('private_write_failed')
            view = view[count:]
        os.fsync(fd)

    def create_directory(self, name):
        with self.directory() as fd:
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
            except FileExistsError:
                raise VaultError('vault_exists') from None
            os.fsync(fd)

    def names(self, child):
        with self.directory(child) as fd:
            names = os.listdir(fd)
            if len(names) > 512:
                raise VaultError('vault_quarantined')
            return set(names)

    def unlink(self, child, name, missing_ok=False, links=(1,)):
        with self.directory(child) as directory:
            try:
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                if missing_ok:
                    return
                raise VaultError('vault_quarantined') from None
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink not in links):
                raise VaultError('unsafe_vault_file')
            os.unlink(name, dir_fd=directory)
            os.fsync(directory)

    def promote(self, stage, final):
        with self.directory('staging') as source, self.directory('recordings') as target:
            try:
                os.link(stage, final, src_dir_fd=source, dst_dir_fd=target, follow_symlinks=False)
            except FileExistsError:
                raise VaultError('vault_quarantined') from None
            os.fsync(target)
        self.unlink('staging', stage, links=(2,))
