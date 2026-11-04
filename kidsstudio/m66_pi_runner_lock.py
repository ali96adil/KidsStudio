"""M66 exclusive Pi uploader process lock.

Keep the single uploader loop from running twice against the same SQLite
journal. Linux/macOS advisory flock releases on process exit/crash.
This is defense in depth; SQLite's one-shot journal remains authoritative.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path


class UploaderAlreadyRunning(RuntimeError):
    pass


class ExclusiveUploaderLock:
    def __init__(self, journal: Path):
        self.path = Path(str(journal) + ".runner.lock")
        self.fd: int | None = None

    def __enter__(self):
        if self.path.is_symlink():
            raise UploaderAlreadyRunning("Unsafe uploader lock symlink")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        try:
            if not os.path.isfile(self.path):
                raise UploaderAlreadyRunning("Uploader lock is not a regular file")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, UploaderAlreadyRunning) as exc:
            os.close(fd)
            raise UploaderAlreadyRunning("Pi uploader already running or lock unsafe") from exc
        self.fd = fd
        return self

    def __exit__(self, *_):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
