"""M66 local resumable .part staging simulation, with atomic finalization.

No SSH, rsync, Pi, Google or owner media. The production transfer must be
qualified separately on both devices.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

BLOCK = 1024 * 1024


def _regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(BLOCK), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(source: Path, destination: Path, *, interrupt_after: int | None = None) -> str:
    """Copy/resume into destination.part; verify before atomic rename.

    Returns COMPLETE or INTERRUPTED. Existing final files must match the
    source; an invalid partial file is rejected, not silently overwritten.
    Only use inside a private trusted directory (not a concurrent writer).
    """
    if not _regular(source) or source.resolve() == destination.resolve():
        raise ValueError("invalid source")
    if destination.is_symlink() or destination.is_dir():
        raise ValueError("invalid destination")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("invalid destination directory")
    part = destination.with_name(destination.name + ".part")
    if part.is_symlink() or part.is_dir():
        raise ValueError("invalid partial file")
    expected_size = source.stat().st_size
    expected_sha = _hash(source)
    if destination.exists():
        if not _regular(destination) or destination.stat().st_size != expected_size or _hash(destination) != expected_sha:
            raise ValueError("existing final differs")
        return "COMPLETE"
    offset = part.stat().st_size if part.exists() else 0
    if offset > expected_size:
        raise ValueError("partial longer than source")
    # Rehash the entire existing prefix rather than trusting its filename.
    with source.open("rb") as src:
        prefix = hashlib.sha256()
        remaining = offset
        while remaining:
            data = src.read(min(BLOCK, remaining))
            if not data:
                raise ValueError("source changed")
            prefix.update(data)
            remaining -= len(data)
    if part.exists():
        pfx = hashlib.sha256()
        with part.open("rb") as stream:
            for data in iter(lambda: stream.read(BLOCK), b""):
                pfx.update(data)
        if prefix.digest() != pfx.digest():
            raise ValueError("partial prefix differs")
    written = 0
    with source.open("rb") as src, part.open("ab") as out:
        src.seek(offset)
        while True:
            if interrupt_after is not None and written >= interrupt_after:
                break
            limit = BLOCK if interrupt_after is None else min(BLOCK, interrupt_after - written)
            chunk = src.read(limit)
            if not chunk:
                break
            out.write(chunk)
            written += len(chunk)
        out.flush()
        os.fsync(out.fileno())
    if part.stat().st_size < expected_size:
        return "INTERRUPTED"
    if part.stat().st_size != expected_size or _hash(part) != expected_sha or _hash(source) != expected_sha:
        raise ValueError("full transfer verification failed")
    os.replace(part, destination)
    return "COMPLETE"
