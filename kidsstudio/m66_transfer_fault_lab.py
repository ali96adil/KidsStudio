"""M66.2 offline transfer interruption harness (NOT the production rsync path).

Simulates resumable chunks into a private .part file, verifies full SHA-256,
and atomically promotes to .ready. Never connects to Pi or Google.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


class TransferSimulationError(ValueError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def simulate(source: Path, destination: Path, *, interrupt_after: int = 0,
             chunk_size: int = 1024 * 1024) -> dict:
    if chunk_size <= 0 or interrupt_after < 0:
        raise TransferSimulationError("invalid simulation limits")
    source = Path(source)
    destination = Path(destination)
    if not source.is_file() or source.is_symlink():
        raise TransferSimulationError("regular source required")
    if not destination.is_dir() or destination.is_symlink():
        raise TransferSimulationError("regular destination directory required")
    part = destination / (source.name + ".part")
    ready = destination / (source.name + ".ready")
    for path in (part, ready):
        if path.is_symlink():
            raise TransferSimulationError("symlink destination rejected")
    expected = sha256(source)
    if ready.exists():
        if sha256(ready) != expected:
            raise TransferSimulationError("existing ready content differs")
        return {"status": "ALREADY_VERIFIED", "sha256": expected}
    offset = part.stat().st_size if part.exists() else 0
    if offset > source.stat().st_size:
        raise TransferSimulationError("oversized partial file")
    # This is a simulator: compare existing prefix to detect corruption.
    with source.open("rb") as src:
        if offset:
            with part.open("rb") as old:
                remaining = offset
                while remaining:
                    a = src.read(min(chunk_size, remaining))
                    b = old.read(len(a))
                    if a != b:
                        raise TransferSimulationError("partial prefix differs")
                    remaining -= len(a)
        mode = "ab" if offset else "xb"
        copied = 0
        with part.open(mode) as out:
            os.chmod(part, stat.S_IRUSR | stat.S_IWUSR)
            while True:
                if interrupt_after and copied >= interrupt_after:
                    break
                limit = chunk_size if not interrupt_after else min(
                    chunk_size, interrupt_after - copied)
                block = src.read(limit)
                if not block:
                    break
                out.write(block)
                copied += len(block)
            out.flush()
            os.fsync(out.fileno())
    if part.stat().st_size < source.stat().st_size:
        return {"status": "INTERRUPTED", "bytes_saved": part.stat().st_size,
                "ready_visible": False}
    if sha256(part) != expected:
        raise TransferSimulationError("complete transfer SHA mismatch")
    os.replace(part, ready)
    return {"status": "VERIFIED_READY", "sha256": expected,
            "bytes_saved": ready.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--interrupt-after", type=int, default=0)
    args = p.parse_args(argv)
    try:
        print(json.dumps(simulate(args.source, args.destination,
                                  interrupt_after=args.interrupt_after),
                         sort_keys=True))
        return 0
    except (TransferSimulationError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
