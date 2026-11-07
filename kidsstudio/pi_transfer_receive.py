"""Pi-side SSH stdin receiver: private, atomic, SHA256 verified, no overwrite.

The remote user must already have a trusted 0700 inbox. No HTTP, YouTube,
auth setup, shell execution, background worker or automatic publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import BinaryIO

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,158}\.mp4\Z")
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")
_MAX = 20 * 1024**3


class PiReceiveError(ValueError):
    """Private incoming video failed safety or integrity checks."""


def _private_root(root: str | Path) -> Path:
    base = Path(os.path.abspath(os.path.expanduser(str(root))))
    if any(p.is_symlink() for p in (base, *base.parents)):
        raise PiReceiveError("Symlink in private inbox path.")
    if not base.is_dir():
        raise PiReceiveError("Existing Pi inbox directory required.")
    if any((p / ".git").exists() for p in (base, *base.parents)):
        raise PiReceiveError("Inbox must be outside Git.")
    info = base.stat()
    if (info.st_mode & 0o077
            or (os.name == "posix" and info.st_uid != os.getuid())):
        raise PiReceiveError("Inbox must be owner-only (0700).")
    return base


def _verify_existing(path: Path, expected_sha256: str, expected_size: int) -> bool:
    if path.is_symlink():
        raise PiReceiveError("Existing inbox item is a symlink.")
    if not path.exists():
        return False
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
            or (os.name == "posix" and info.st_uid != os.getuid())
            or info.st_size != expected_size):
        raise PiReceiveError("Existing inbox item is unsafe or differs.")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256.lower():
        raise PiReceiveError("Existing inbox item has different content.")
    return True


def receive_private_video(*, destination_root: str | Path,
                          destination_name: str, expected_sha256: str,
                          expected_bytes: int, source: BinaryIO) -> dict:
    if not isinstance(destination_name, str) or not _NAME.fullmatch(destination_name):
        raise PiReceiveError("Only simple .mp4 destination names are allowed.")
    if not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256):
        raise PiReceiveError("Invalid expected SHA256.")
    if type(expected_bytes) is not int or not 1 <= expected_bytes <= _MAX:
        raise PiReceiveError("Invalid expected byte count.")
    base = _private_root(destination_root)
    destination = base / destination_name
    # An existing item never gets replaced; a matching item may be reported
    # as already present for idempotent local receiver checks.
    if _verify_existing(destination, expected_sha256, expected_bytes):
        return _receipt("PI_INBOX_ALREADY_VERIFIED", destination_name,
                        expected_sha256.lower(), expected_bytes)
    fd, temp_name = tempfile.mkstemp(prefix=".incoming-", dir=base)
    checksum = hashlib.sha256()
    received = 0
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            while received < expected_bytes:
                chunk = source.read(min(1024 * 1024, expected_bytes - received))
                if not chunk:
                    raise PiReceiveError("SSH media stream ended prematurely.")
                received += len(chunk)
                checksum.update(chunk)
                output.write(chunk)
            if source.read(1):
                raise PiReceiveError("SSH media stream exceeds declared byte count.")
            output.flush()
            os.fsync(output.fileno())
        if checksum.hexdigest() != expected_sha256.lower():
            raise PiReceiveError("Incoming video SHA256 mismatch.")
        try:
            # Atomic no-replace on same filesystem. Destination never becomes
            # visible until the entire video has been checked and synced.
            os.link(temp_name, destination, follow_symlinks=False)
        except FileExistsError:
            if _verify_existing(destination, expected_sha256, expected_bytes):
                return _receipt("PI_INBOX_ALREADY_VERIFIED", destination_name,
                                expected_sha256.lower(), expected_bytes)
            raise
        dir_fd = os.open(base, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        Path(temp_name).unlink(missing_ok=True)
    return _receipt("PI_INBOX_RECEIVED_PRIVATE", destination_name,
                    expected_sha256.lower(), received)


def _receipt(status: str, name: str, sha: str, size: int) -> dict:
    return {
        "schema_version": 1,
        "status": status,
        "destination_name": name,
        "sha256": sha,
        "bytes": size,
        "private_inbox_verified_at_receive": True,
        "upload_submitted": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strict stdin receiver for Mac→Pi video")
    parser.add_argument("--destination-name", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    # No arbitrary --root: SSH receiver is bound to one private home inbox.
    args = parser.parse_args(argv)
    try:
        report = receive_private_video(
            destination_root=Path.home() / "kidsstudio-private" / "inbox",
            destination_name=args.destination_name,
            expected_sha256=args.expected_sha256,
            expected_bytes=args.expected_bytes, source=sys.stdin.buffer)
    except (OSError, PiReceiveError, ValueError):
        print(json.dumps({"status": "PI_INBOX_TRANSFER_REJECTED",
                          "upload_submitted": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
