"""M66 read-only Pi upload station preflight. Never initializes, uploads or changes files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat


def inspect(*, db: Path, inbox: Path, journal: Path,
            fixture: Path | None = None, expected_sha256: str | None = None) -> dict:
    checks: dict[str, dict] = {}

    def check_path(label: str, path: Path, *, directory: bool = False) -> None:
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("symlink rejected")
            if directory and not stat.S_ISDIR(info.st_mode):
                raise ValueError("not a directory")
            if not directory and not stat.S_ISREG(info.st_mode):
                raise ValueError("not a regular file")
            checks[label] = {"ok": True, "mode": oct(stat.S_IMODE(info.st_mode))}
        except (OSError, ValueError) as exc:
            checks[label] = {"ok": False, "reason": str(exc)}

    check_path("database", db)
    check_path("inbox", inbox, directory=True)
    # Journal is optional before the first upload; no creation occurs here.
    if journal.exists() or journal.is_symlink():
        check_path("journal", journal)
    else:
        checks["journal"] = {"ok": True, "status": "not_created_yet"}

    if checks["database"]["ok"]:
        try:
            uri = db.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as conn:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            checks["sqlite_readonly"] = {"ok": True, "table_count": len(tables)}
        except (OSError, sqlite3.Error) as exc:
            checks["sqlite_readonly"] = {"ok": False, "reason": str(exc)}

    if fixture is not None:
        check_path("fixture", fixture)
        if checks["fixture"]["ok"]:
            h = hashlib.sha256()
            with fixture.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    h.update(block)
            actual = h.hexdigest()
            checks["fixture_sha256"] = {
                "ok": expected_sha256 is None or actual == expected_sha256.lower(),
                "actual": actual,
                "expected_supplied": expected_sha256 is not None,
            }

    return {
        "stage": "M66_READ_ONLY_PREFLIGHT",
        "passed": all(c["ok"] for c in checks.values()),
        "checks": checks,
        "google_network_used": False,
        "upload_attempted": False,
        "files_modified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--inbox-root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    if args.expected_sha256 and (len(args.expected_sha256) != 64 or
        any(c not in "0123456789abcdefABCDEF" for c in args.expected_sha256)):
        parser.error("--expected-sha256 must be 64 hexadecimal characters")
    if args.expected_sha256 and args.fixture is None:
        parser.error("--expected-sha256 requires --fixture")
    result = inspect(db=args.db, inbox=args.inbox_root, journal=args.journal,
                     fixture=args.fixture, expected_sha256=args.expected_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
