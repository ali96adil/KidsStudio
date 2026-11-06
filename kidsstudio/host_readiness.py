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
import stat
import sys


def _absolute_unresolved(path: str | Path) -> Path:
    # resolve() would hide symlink components before we can inspect them.
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _symlink_component(path: Path) -> bool:
    return any(p.is_symlink() for p in (path, *path.parents))


def _outside_git(path: Path) -> bool:
    # Check both the literal path and its resolved target, defensively.
    return all(
        not (p / ".git").exists()
        for candidate in (path, path.resolve())
        for p in (candidate, *candidate.parents)
    )


def _owned_by_user(path: Path) -> bool:
    return os.name != "posix" or path.stat().st_uid == os.getuid()


def _private_permissions(path: Path) -> bool:
    return os.name != "posix" or not (path.stat().st_mode & 0o077)


def inspect_host(*, artifact_root: str | Path, database: str | Path | None = None,
                 min_free_gib: float = 2.0) -> dict:
    if not 0 <= min_free_gib <= 1024:
        raise ValueError("invalid free-space threshold")
    root = _absolute_unresolved(artifact_root)
    db = _absolute_unresolved(database) if database else None
    checks: dict[str, bool] = {
        "python_3_11_plus": sys.version_info >= (3, 11),
        "artifact_root_exists": root.is_dir(),
        "artifact_root_outside_git": _outside_git(root),
        "artifact_root_not_symlink": not root.is_symlink(),
        "artifact_root_no_symlink_components": not _symlink_component(root),
        "artifact_root_owned_by_user": root.is_dir() and _owned_by_user(root),
    }
    if root.is_dir():
        checks["artifact_root_private"] = _private_permissions(root)
        checks["free_space_threshold"] = (
            shutil.disk_usage(root).free >= min_free_gib * (1024 ** 3)
        )
    else:
        checks["artifact_root_private"] = False
        checks["free_space_threshold"] = False
    if db is not None:
        checks["database_exists"] = db.is_file()
        checks["database_outside_git"] = _outside_git(db)
        checks["database_no_symlink_components"] = not _symlink_component(db)
        checks["database_parent_private"] = (
            db.parent.is_dir() and _private_permissions(db.parent))
        checks["database_parent_owned_by_user"] = (
            db.parent.is_dir() and _owned_by_user(db.parent))
        # lstat, rather than stat, rejects a symlink target masquerading as a DB.
        regular = db.exists() and stat.S_ISREG(db.lstat().st_mode)
        checks["database_regular_file"] = regular
        checks["database_private_permissions"] = (
            regular and _private_permissions(db))
        checks["database_owned_by_user"] = (
            regular and _owned_by_user(db))
    return {
        "schema_version": 2,
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
