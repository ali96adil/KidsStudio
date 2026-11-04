"""M66 offline transfer integrity acceptance checks. No network, no owner media."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

CHUNK = 1024 * 1024

def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular non-symlink file required")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()

def verify(source: Path, received: Path) -> dict:
    expected = digest(source)
    actual = digest(received)
    if source.stat().st_size != received.stat().st_size or expected != actual:
        raise ValueError("transfer bytes mismatch")
    return {"status": "PASS", "sha256": actual, "bytes": received.stat().st_size}

def main() -> None:
    p = argparse.ArgumentParser(description="M66 offline SHA-256 transfer check; does not upload")
    p.add_argument("source", type=Path)
    p.add_argument("received", type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(verify(args.source, args.received), sort_keys=True))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
