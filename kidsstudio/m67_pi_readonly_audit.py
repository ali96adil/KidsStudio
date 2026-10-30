"""M67 read-only Pi deployment audit: no OAuth or upload side effects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3

from .m66_upload_reconciliation import inspect_journal


def audit(*, db, inbox_root, journal, render_job_id):
    root = Path(inbox_root)
    checks = {
        "pi_root_exists": root.is_dir() and not root.is_symlink(),
        "pi_root_private": root.is_dir() and (root.stat().st_mode & 0o077) == 0,
        "sqlite_db_exists": Path(db).is_file() and not Path(db).is_symlink(),
        "journal_exists": Path(journal).is_file() and not Path(journal).is_symlink(),
        "ffmpeg_available": bool(shutil.which("ffmpeg")),
    }
    if checks["sqlite_db_exists"]:
        try:
            uri = Path(db).resolve().as_uri() + "?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as conn:
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            checks["m65_inbox_schema"] = "studio_pi_ordinary_media" in tables
            checks["owner_policy_schema"] = "studio_youtube_private_policies" in tables
        except sqlite3.Error:
            checks["m65_inbox_schema"] = False
            checks["owner_policy_schema"] = False
    else:
        checks["m65_inbox_schema"] = False
        checks["owner_policy_schema"] = False
    state = inspect_journal(Path(journal), render_job_id)
    checks["no_ambiguous_upload_attempt"] = state["status"] not in (
        "NEEDS_RECONCILIATION", "INVALID_JOURNAL", "UNKNOWN_STATE",
        "UNREADABLE_JOURNAL")
    return {"status": "PI_READONLY_READY" if all(checks.values())
            else "PI_READONLY_BLOCKED",
            "checks": checks, "journal": state,
            "youtube_uploaded": False, "network_used": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--inbox-root", type=Path, required=True)
    p.add_argument("--journal", type=Path, required=True)
    p.add_argument("--render-job-id", required=True)
    args = p.parse_args(argv)
    report = audit(db=args.db, inbox_root=args.inbox_root,
                   journal=args.journal, render_job_id=args.render_job_id)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PI_READONLY_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
