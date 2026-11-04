"""M66 offline read-only Pi master MP4 integrity check.

Operator provides an owner-approved SHA256 and the local transferred MP4.
No network, OAuth, journal writes, upload, or public release is performed.
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

from .youtube_private_upload import MAX_BYTES

SHA = re.compile(r"^[0-9a-f]{64}$")


def verify_master(path: Path, expected_sha256: str) -> dict:
    if not isinstance(expected_sha256, str) or not SHA.fullmatch(expected_sha256):
        raise ValueError("Expected approved lowercase SHA256 digest")
    if not path.is_absolute() or path.is_symlink() or path.suffix.lower() != ".mp4":
        raise ValueError("Expected absolute non-symlink MP4")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or not 1000 <= before.st_size <= MAX_BYTES:
        raise ValueError("Unsafe or missing MP4")
    with path.open('rb') as source:
        digest_state = hashlib.sha256()
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest_state.update(block)
        opened = os.fstat(source.fileno())
    digest = digest_state.hexdigest()
    if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
        raise ValueError('MP4 replaced before hashing')
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise ValueError("MP4 changed during verification")
    match = digest == expected_sha256
    return {
        "status": "M66_PI_MASTER_SHA256_MATCH" if match else "M66_PI_MASTER_SHA256_MISMATCH",
        "pass": match,
        "expected_sha256": expected_sha256,
        "actual_sha256": digest,
        "size_bytes": after.st_size,
        "network_used": False,
        "upload_performed": False,
        "public_release_authorized": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kidsstudio-m66-master-check")
    parser.add_argument("--mp4", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_master(args.mp4, args.expected_sha256)
    except (OSError, ValueError):
        print("M66_PI_MASTER_CHECK_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
