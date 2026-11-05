"""Read-only aggregate dashboard snapshot from the existing StudioQueue SQLite DB.

Uses SQLite mode=ro, PRAGMA query_only and only aggregate SELECTs.
Never exposes job payloads, paths, tokens, or episode identities.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .studio_queue import KINDS, STATES


def queue_dashboard_snapshot(database: str | Path) -> dict:
    path = Path(database).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix not in {".sqlite", ".db"}:
        raise ValueError("invalid queue database")
    if any((p / ".git").exists() for p in (path.parent, *path.parents)):
        raise ValueError("queue database must be outside Git")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"jobs", "settings"}.issubset(tables):
            raise ValueError("unsupported queue schema")
        groups = connection.execute(
            "SELECT kind, state, COUNT(*) FROM jobs GROUP BY kind, state"
        ).fetchall()
        paused = connection.execute(
            "SELECT paused FROM settings WHERE slot=1"
        ).fetchone()
        if paused is None:
            raise ValueError("missing queue settings")
        counts = {kind: {state: 0 for state in sorted(STATES)}
                  for kind in sorted(KINDS)}
        for kind, state, count in groups:
            if kind not in KINDS or state not in STATES or count < 0:
                raise ValueError("unsupported job state")
            counts[kind][state] = count
        return {
            "schema_version": 1,
            "status": "READ_ONLY_QUEUE_SNAPSHOT",
            "queue_paused": bool(paused[0]),
            "total_jobs": sum(sum(v.values()) for v in counts.values()),
            "jobs_by_kind_and_state": counts,
            "episode_lifecycle_inferred": False,
            "queue_mutated": False,
            "publication_approved": False,
        }
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only queue dashboard counts")
    parser.add_argument("--db", required=True)
    args = parser.parse_args(argv)
    try:
        report = queue_dashboard_snapshot(args.db)
    except (OSError, ValueError, sqlite3.Error):
        print(json.dumps({"status": "SNAPSHOT_UNAVAILABLE",
                          "queue_mutated": False, "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
