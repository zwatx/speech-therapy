"""Bounded local files with exclusive writes; never follow supplied links."""

import os
from pathlib import Path
import stat


MAX_BYTES = 8 * 1024 * 1024


class FileError(ValueError):
    def __init__(self, code='unsafe_file'):
        self.code = code
        super().__init__(code)


def _parts(path):
    if type(path) is not str or not path.startswith('/'):
        raise FileError()
    parts = path.split('/')[1:]
    if not parts or any(p in ('', '.', '..') for p in parts):
        raise FileError()
    return parts


def _directory(parts, private=False):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or (private and stat.S_IMODE(info.st_mode) != 0o700):
            raise FileError()
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_private(path):
    """Require an owned 0700 parent and 0600, single-link regular file."""
    fd = parent = None
    try:
        parts = _parts(path)
        parent = _directory(parts[:-1], private=True)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > MAX_BYTES):
            raise FileError()
        chunks = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        if (len(raw) > MAX_BYTES or after.st_size != len(raw)
                or after.st_mtime_ns != info.st_mtime_ns or after.st_ctime_ns != info.st_ctime_ns):
            raise FileError()
        return raw
    except (OSError, ValueError):
        raise FileError() from None
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)


def write_private(path, raw):
    fd = parent = None
    try:
        if type(raw) is not bytes or len(raw) > MAX_BYTES:
            raise FileError()
        parts = _parts(path)
        parent = _directory(parts[:-1], private=True)
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        os.fchmod(fd, 0o600)
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fsync(fd)
    except (OSError, ValueError):
        raise FileError('output_unavailable') from None
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)


def create_root(path):
    parent = None
    try:
        parts = _parts(path)
        parent = _directory(parts[:-1])
        os.mkdir(parts[-1], 0o700, dir_fd=parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            os.fchmod(fd, 0o700)
        finally:
            os.close(fd)
        return Path(path)
    except (OSError, ValueError):
        raise FileError('output_unavailable') from None
    finally:
        if parent is not None:
            os.close(parent)
