"""Cooperative, local-only cross-worker compute reservation.

Use one private_root for Studio stages and assembly to share the same gate.
It cannot control unrelated third-party processes outside this codebase.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from typing import Iterator

from .episode_assembly import _ensure_private


class ResourceGateError(ValueError):
    pass


@contextmanager
def cooperative_compute_lock(private_root: str | Path) -> Iterator[None]:
    root = _ensure_private(Path(private_root))
    if not root.is_dir():
        raise ResourceGateError("Shared local resource root must already exist.")
    lock = root / ".kidsstudio_compute.lock"
    if lock.is_symlink():
        raise ResourceGateError("Resource lock cannot be a symlink.")
    fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        # Blocking acquisition: different real KidsStudio jobs with SAME
        # private_root serialize instead of simultaneously exhausting RAM.
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
