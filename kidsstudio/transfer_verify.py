"""Read-only SHA256 verification for a locally staged Mac-to-Pi transfer.

Does not copy files, connect to a host, or approve an upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
_MAX_BYTES = 20 * 1024**3


def verify_staged_file(*, root: str | Path, relative_path: str,
                       expected_sha256: str, max_bytes: int = _MAX_BYTES) -> dict:
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("invalid expected SHA256")
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("invalid relative path")
    path_part = Path(relative_path)
    if path_part.is_absolute() or ".." in path_part.parts:
        raise ValueError("unsafe relative path")
    if not isinstance(max_bytes, int) or not 0 < max_bytes <= _MAX_BYTES:
        raise ValueError("invalid maximum size")
    base = Path(root).expanduser().resolve(strict=True)
    candidate = base.joinpath(path_part).resolve(strict=True)
    if not base.is_dir() or not candidate.is_relative_to(base) or not candidate.is_file():
        raise ValueError("file outside staged root")
    size = candidate.stat().st_size
    if size > max_bytes:
        raise ValueError("file exceeds limit")
    digest = hashlib.sha256()
    with candidate.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    # Re-check size to detect ordinary concurrent changes (not a full TOCTOU guarantee).
    if candidate.stat().st_size != size:
        raise ValueError("file changed during verification")
    actual = digest.hexdigest()
    matched = actual == expected_sha256.lower()
    return {
        "schema_version": 1,
        "status": "VERIFIED" if matched else "HASH_MISMATCH",
        "sha256": actual,
        "bytes": size,
        "transfer_performed": False,
        "upload_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only staged file SHA256 check")
    parser.add_argument("--root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--max-bytes", type=int, default=_MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        report = verify_staged_file(
            root=args.root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256, max_bytes=args.max_bytes,
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "VERIFICATION_ERROR",
                          "transfer_performed": False,
                          "upload_approved": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
