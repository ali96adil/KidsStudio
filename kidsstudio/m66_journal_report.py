"""M66 read-only Pi uploader acceptance report.

Inspects the real M25/M65 SQLite upload journal without opening Google,
claiming jobs, modifying the database, or acquiring an uploader lock.
Use this before/after Pi reboot to compare durable states.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

VALID = {"STARTED", "UPLOADED_UNVERIFIED", "PRIVATE_VERIFIED"}


def inspect_journal(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.suffix != ".sqlite":
        raise ValueError("Expected existing non-symlink SQLite journal")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=3) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT render_job_id, master_sha256, plan_sha256, state, video_id, created_at, updated_at FROM attempts "
            "ORDER BY render_job_id"
        ).fetchall()
    counts = {state: 0 for state in sorted(VALID)}
    uncertain = []
    snapshot = hashlib.sha256()
    for row in rows:
        state = row["state"]
        if state not in VALID:
            raise ValueError("Unexpected journal state")
        counts[state] += 1
        snapshot.update(json.dumps(
            [row["render_job_id"], row["master_sha256"], row["plan_sha256"],
             state, row["video_id"], row["created_at"], row["updated_at"]],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("utf-8") + b"\\n")
        if state != "PRIVATE_VERIFIED":
            uncertain.append(row["render_job_id"])
    return {
        "status": "M66_READ_ONLY_JOURNAL_REPORT",
        "network_used": False,
        "database_modified": False,
        "public_release_authorized": False,
        "total": len(rows),
        "states": counts,
        "snapshot_sha256": snapshot.hexdigest(),
        "requires_manual_reconciliation": uncertain,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kidsstudio-m66-journal-report")
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_journal(args.journal)
    except (ValueError, OSError, sqlite3.Error):
        print("M66_JOURNAL_REPORT_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
