"""M66 Pi local master-to-journal acceptance check, strictly read-only.

Checks that a received final MP4 matches the SHA reserved in the actual
SQLite upload journal. Does not create reservations or upload anything.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys

from .m66_master_check import verify_master

JOB = re.compile(r"^[0-9a-f]{32}$")


def verify_reserved_master(journal: Path, job: str, mp4: Path) -> dict:
    if not JOB.fullmatch(job):
        raise ValueError("Invalid render job")
    if journal.is_symlink() or not journal.is_file() or journal.suffix != ".sqlite":
        raise ValueError("Existing SQLite journal required")
    with sqlite3.connect(f"{journal.resolve().as_uri()}?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT master_sha256, state FROM attempts WHERE render_job_id=?",
            (job,),
        ).fetchall()
    if len(rows) != 1 or rows[0][1] not in (
        "STARTED", "UPLOADED_UNVERIFIED", "PRIVATE_VERIFIED"
    ):
        raise ValueError("No valid reserved upload journal entry")
    check = verify_master(mp4, rows[0][0])
    # Reject a stale acceptance if the reserved state changes during hashing.
    with sqlite3.connect(f"{journal.resolve().as_uri()}?mode=ro", uri=True) as db:
        current = db.execute(
            "SELECT master_sha256, state FROM attempts WHERE render_job_id=?",
            (job,),
        ).fetchall()
    if current != rows:
        raise ValueError("Upload journal changed during media verification")
    return {
        "status": "M66_RESERVED_PI_MASTER_MATCH" if check["pass"]
                  else "M66_RESERVED_PI_MASTER_MISMATCH",
        "pass": check["pass"],
        "render_job_id": job,
        "journal_state": rows[0][1],
        "size_bytes": check["size_bytes"],
        "network_used": False,
        "upload_performed": False,
        "public_release_authorized": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kidsstudio-m66-reserved-master-check")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--mp4", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_reserved_master(args.journal, args.job, args.mp4)
    except (ValueError, OSError, sqlite3.Error):
        print("M66_RESERVED_MASTER_CHECK_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
