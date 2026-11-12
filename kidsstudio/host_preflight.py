"""Offline, read-only host preflight for supervised Mac/Pi qualification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys


def inspect_host(*, artifact_root: str | None = None,
                 queue_db: str | None = None,
                 minimum_free_gib: float = 2.0) -> dict:
    if minimum_free_gib < 0:
        raise ValueError("minimum_free_gib must not be negative")
    checks: dict[str, bool] = {}
    details: dict[str, object] = {
        "python": ".".join(map(str, sys.version_info[:3])),
        "platform": platform.system(),
        "machine": platform.machine(),
    }
    checks["python_supported"] = sys.version_info >= (3, 11)
    checks["git_available"] = shutil.which("git") is not None
    details["godot_present"] = any(
        shutil.which(name) is not None for name in ("godot", "godot4", "Godot")
    )
    details["ffmpeg_present"] = shutil.which("ffmpeg") is not None
    if artifact_root is not None:
        root = Path(artifact_root).expanduser().resolve()
        checks["artifact_root_exists"] = root.is_dir()
        checks["artifact_outside_git"] = not any(
            (parent / ".git").exists() for parent in (root, *root.parents)
        )
        if root.is_dir():
            details["artifact_free_gib"] = round(
                shutil.disk_usage(root).free / (1024 ** 3), 2)
            checks["artifact_free_space"] = (
                shutil.disk_usage(root).free >= minimum_free_gib * 1024 ** 3
            )
            checks["artifact_private_permissions"] = (
                os.name != "posix" or root.stat().st_mode & 0o077 == 0
            )
        else:
            checks["artifact_free_space"] = False
            checks["artifact_private_permissions"] = False
    if queue_db is not None:
        db = Path(queue_db).expanduser().resolve()
        checks["queue_exists"] = db.is_file()
        checks["queue_nonempty"] = db.is_file() and db.stat().st_size > 0
    return {
        "schema_version": 1,
        "status": "PREFLIGHT_PASS" if all(checks.values()) else "PREFLIGHT_ACTION_REQUIRED",
        "checks": checks,
        "details": details,
        "read_only": True,
        "production_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline read-only KidsStudio host preflight")
    parser.add_argument("--artifact-root")
    parser.add_argument("--queue-db")
    parser.add_argument("--minimum-free-gib", type=float, default=2.0)
    args = parser.parse_args(argv)
    try:
        report = inspect_host(
            artifact_root=args.artifact_root, queue_db=args.queue_db,
            minimum_free_gib=args.minimum_free_gib,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "PREFLIGHT_ERROR",
                          "read_only": True, "production_approved": False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PREFLIGHT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
