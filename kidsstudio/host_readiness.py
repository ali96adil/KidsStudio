"""Offline, read-only host readiness probe for supervised G4 qualification.

No queue connection, network call, model inference, uploads or writes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys


def inspect_host(*, artifact_root: str | Path, database: str | Path | None = None,
                 min_free_gib: float = 2.0) -> dict:
    if not 0 <= min_free_gib <= 1024:
        raise ValueError("invalid free-space threshold")
    root = Path(artifact_root).expanduser().resolve()
    db = Path(database).expanduser().resolve() if database else None
    checks: dict[str, bool] = {
        "python_3_11_plus": sys.version_info >= (3, 11),
        "artifact_root_exists": root.is_dir(),
        "artifact_root_outside_git": not any(
            (p / ".git").exists() for p in (root, *root.parents)),
        "artifact_root_not_symlink": not Path(artifact_root).expanduser().is_symlink(),
    }
    if root.is_dir():
        checks["artifact_root_private"] = (
            os.name != "posix" or root.stat().st_mode & 0o077 == 0
        )
        checks["free_space_threshold"] = (
            shutil.disk_usage(root).free >= min_free_gib * (1024 ** 3)
        )
    else:
        checks["artifact_root_private"] = False
        checks["free_space_threshold"] = False
    if db is not None:
        checks["database_exists"] = db.is_file()
        checks["database_outside_git"] = not any(
            (p / ".git").exists() for p in (db.parent, *db.parents)
        )
    return {
        "schema_version": 1,
        "host_system": platform.system(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "checks": checks,
        "ready_for_supervised_tests": all(checks.values()),
        "production_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline G4 host readiness probe")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--db")
    parser.add_argument("--min-free-gib", type=float, default=2.0)
    args = parser.parse_args(argv)
    try:
        result = inspect_host(
            artifact_root=args.artifact_root, database=args.db,
            min_free_gib=args.min_free_gib,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "PROBE_ERROR",
                          "production_approved": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ready_for_supervised_tests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
