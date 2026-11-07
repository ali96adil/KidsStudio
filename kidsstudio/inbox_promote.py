"""Explicit local promotion of verified staged files to private Pi inbox.

No network, queue, YouTube, automatic discovery, or overwrites.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .transfer_verify import verify_staged_file

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")


def promote_verified_file(*, source_root: str | Path, relative_path: str,
                          destination_root: str | Path, expected_sha256: str,
                          destination_name: str, max_bytes: int = 20 * 1024**3) -> dict:
    if not isinstance(destination_name, str) or not _NAME.fullmatch(destination_name):
        raise ValueError("unsafe destination name")
    if destination_name in {".", ".."}:
        raise ValueError("unsafe destination name")
    source_base = Path(source_root).expanduser().resolve(strict=True)
    destination_base = Path(destination_root).expanduser().resolve(strict=True)
    if not destination_base.is_dir() or source_base == destination_base:
        raise ValueError("separate existing private directories required")
    if any((p / ".git").exists() for p in (destination_base, *destination_base.parents)):
        raise ValueError("destination must be outside Git")
    if os.name == "posix" and destination_base.stat().st_mode & 0o077:
        raise ValueError("destination directory must be private")
    report = verify_staged_file(root=source_base, relative_path=relative_path,
                                expected_sha256=expected_sha256, max_bytes=max_bytes)
    if report["status"] != "VERIFIED":
        raise ValueError("staged SHA256 mismatch")
    source = (source_base / relative_path).resolve(strict=True)
    if not stat.S_ISREG(source.stat().st_mode):
        raise ValueError("source is not a regular file")
    destination = destination_base / destination_name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("destination already exists")
    temp = destination_base / (".incoming-" + uuid.uuid4().hex)
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    copied = 0
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as inp:
            while chunk := inp.read(1024 * 1024):
                copied += len(chunk)
                if copied > max_bytes:
                    raise ValueError("source grew during copy")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if copied != report["bytes"] or digest.hexdigest() != expected_sha256.lower():
            raise ValueError("source changed during copy")
        # Atomic, exclusive promotion on the same filesystem: no replace.
        os.link(temp, destination, follow_symlinks=False)
        directory_fd = os.open(destination_base, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)
    return {
        "status": "PROMOTED_PRIVATE",
        "sha256": digest.hexdigest(),
        "bytes": copied,
        "network_transfer_performed": False,
        "upload_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit verified local inbox promotion")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--destination-root", required=True)
    parser.add_argument("--destination-name", required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = promote_verified_file(
            source_root=args.source_root, relative_path=args.relative_path,
            destination_root=args.destination_root, destination_name=args.destination_name,
            expected_sha256=args.expected_sha256,
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "PROMOTION_REJECTED",
                          "upload_approved": False, "publication_approved": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
