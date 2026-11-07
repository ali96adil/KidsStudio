"""Explicit, read-only environment preflight for supervised G4 qualification.

Does not connect to providers, mutate queue state, launch workers or publish.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys


def inspect_environment(*, artifact_root: str | Path, db_path: str | Path) -> dict:
    root = Path(artifact_root).expanduser().resolve()
    database = Path(db_path).expanduser().resolve()
    checks: dict[str, bool] = {}
    checks["python_supported"] = sys.version_info >= (3, 11)
    checks["artifact_root_exists"] = root.is_dir()
    checks["artifact_root_outside_git"] = not any(
        (p / ".git").exists() for p in (root, *root.parents))
    checks["artifact_root_not_symlink"] = not Path(artifact_root).expanduser().is_symlink()
    checks["database_exists"] = database.is_file()
    checks["database_not_symlink"] = not Path(db_path).expanduser().is_symlink()
    checks["database_outside_git"] = not any(
        (p / ".git").exists() for p in (database.parent, *database.parents))
    checks["distinct_artifact_and_db_paths"] = root != database and not root.is_relative_to(database)
    checks["free_space_at_least_1_gib"] = (
        shutil.disk_usage(root).free >= 1024 ** 3 if root.is_dir() else False)
    # SQLite URI mode=ro prevents database creation; immutable avoids WAL side effects.
    if checks["database_exists"] and checks["database_not_symlink"]:
        try:
            connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                checks["sqlite_integrity"] = connection.execute(
                    "PRAGMA quick_check").fetchone()[0] == "ok"
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                checks["expected_queue_tables"] = {"jobs", "events", "settings"}.issubset(tables)
            finally:
                connection.close()
        except (sqlite3.Error, OSError):
            checks["sqlite_integrity"] = False
            checks["expected_queue_tables"] = False
    else:
        checks["sqlite_integrity"] = False
        checks["expected_queue_tables"] = False
    return {
        "schema_version": 1,
        "host_os": platform.system(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "checks": checks,
        "status": "PREFLIGHT_PASS_NOT_LIVE_QUALIFIED" if all(checks.values())
                  else "PREFLIGHT_BLOCKED",
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only KidsStudio G4 preflight")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--db", required=True)
    args = parser.parse_args(argv)
    try:
        report = inspect_environment(artifact_root=args.artifact_root, db_path=args.db)
    except (OSError, ValueError):
        report = {"status": "PREFLIGHT_BLOCKED", "publication_approved": False}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PREFLIGHT_PASS_NOT_LIVE_QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
