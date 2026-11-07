"""Strict local evidence paths for optional alpha-tool qualifications.

Read-only. Not a sandbox against malicious concurrent filesystem mutation.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

MAX_EVIDENCE_FILE = 64 * 1024


class ToolEvidenceError(ValueError):
    """Unsafe or malformed private evaluation evidence."""


def private_evidence_file(root: str | Path, relative_path: str, *, max_bytes: int) -> Path:
    if (not isinstance(relative_path, str) or not relative_path
            or "\x00" in relative_path):
        raise ToolEvidenceError("Invalid relative file path.")
    piece = Path(relative_path)
    if piece.is_absolute() or ".." in piece.parts or piece.parts == (".",):
        raise ToolEvidenceError("Evidence path must be relative and contained.")
    if type(max_bytes) is not int or not 1 <= max_bytes <= 20 * 1024**3:
        raise ToolEvidenceError("Invalid bounded evidence file size.")
    base = Path(os.path.abspath(os.path.expanduser(str(root))))
    target = base / piece
    if any(node.is_symlink() for node in (target, *target.parents)):
        raise ToolEvidenceError("Symlink evidence paths are forbidden.")
    if any((node / ".git").exists() for node in (base, *base.parents)):
        raise ToolEvidenceError("Private evidence must remain outside Git.")
    if not base.is_dir() or base.stat().st_mode & 0o077:
        raise ToolEvidenceError("A private evidence root with mode 0700 is required.")
    if os.name == "posix" and base.stat().st_uid != os.getuid():
        raise ToolEvidenceError("Evidence directory must be owned by current user.")
    if not target.is_file():
        raise ToolEvidenceError("Evidence file not found.")
    # Check every nested directory between private root and target.
    for directory in (target.parent, *target.parents):
        if directory == base:
            break
        if not directory.is_relative_to(base) or not directory.is_dir():
            raise ToolEvidenceError("Evidence path escapes private root.")
        info = directory.stat()
        if info.st_mode & 0o077 or (
            os.name == "posix" and info.st_uid != os.getuid()
        ):
            raise ToolEvidenceError("Nested evidence directory is not private.")
    info = target.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
            or info.st_size > max_bytes or (
                os.name == "posix" and info.st_uid != os.getuid()
            )):
        raise ToolEvidenceError("Evidence must be an owner-only regular bounded file.")
    return target


def read_private_json(root: str | Path, relative_path: str) -> dict:
    import json
    target = private_evidence_file(root, relative_path, max_bytes=MAX_EVIDENCE_FILE)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or info.st_size > MAX_EVIDENCE_FILE or (
                    os.name == "posix" and info.st_uid != os.getuid()
                )):
            raise ToolEvidenceError("Private manifest changed or is unsafe.")
        raw = stream.read(MAX_EVIDENCE_FILE + 1)
    if len(raw) > MAX_EVIDENCE_FILE:
        raise ToolEvidenceError("Private manifest too large.")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ToolEvidenceError("Manifest must be a JSON object.")
    return obj
