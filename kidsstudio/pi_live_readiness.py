"""Local, read-only live-test readiness report for the Pi private uploader.

Never makes network requests, uploads media, or exposes OAuth secrets.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import stat
from pathlib import Path

from .pi_pipeline_preflight import inspect_pi_pipeline
from .pi_upload_queue import PiUploadQueue
from .pi_upload_session_audit import audit_sessions
from .pi_session_intent_audit import audit_session_intents


def inspect_live_readiness(*, state_dir: str | Path,
                           credentials: str | Path,
                           titles_file: str | Path) -> dict:
    root = Path(state_dir)
    config = inspect_pi_pipeline(
        state_dir=root, credentials=credentials, titles_file=titles_file,
    )
    checks = dict(config["checks"])
    checks["upload_queue_readable"] = False
    checks["sessions_healthy"] = False
    checks["no_failed_upload_jobs"] = False
    checks["no_ambiguous_session_intents"] = False
    checks["private_session_directories"] = False
    checks["private_session_files"] = False
    try:
        queue = PiUploadQueue(root / "queue.sqlite")
        # Read-only connection: preflight must not create a missing database.
        with sqlite3.connect(f"file:{(root / 'queue.sqlite').resolve()}?mode=ro",
                             uri=True, timeout=10) as db:
            rows = db.execute(
                "SELECT state,COUNT(*) FROM pi_upload_jobs GROUP BY state"
            ).fetchall()
        checks["upload_queue_readable"] = True
        checks["no_failed_upload_jobs"] = not any(
            state == "failed" and count for state, count in rows
        )
        session_health = audit_sessions(queue, root / "sessions")
        checks["sessions_healthy"] = bool(session_health["healthy"])
        sessions = root / "sessions"
        intent_dir = sessions / ".session-intents"
        checks["private_session_directories"] = (
            not sessions.is_symlink() and sessions.is_dir() and
            stat.S_IMODE(sessions.stat().st_mode) & 0o077 == 0 and
            (not intent_dir.exists() or (
                not intent_dir.is_symlink() and intent_dir.is_dir() and
                stat.S_IMODE(intent_dir.stat().st_mode) & 0o077 == 0
            ))
        )
        # Read metadata only; never open or print private resumable URLs.
        private_files = True
        for directory, suffix in ((sessions, ".json"), (intent_dir, ".intent")):
            if directory.exists() and directory.is_dir() and not directory.is_symlink():
                for item in directory.iterdir():
                    if item.suffix == suffix:
                        if (item.is_symlink() or not item.is_file() or
                                stat.S_IMODE(item.stat().st_mode) & 0o077):
                            private_files = False
        checks["private_session_files"] = private_files
        intent_health = audit_session_intents(sessions, queue.path)
        checks["no_ambiguous_session_intents"] = (
            intent_health["pending_reconciliation"] == 0 and
            intent_health["invalid_intents"] == 0
        )
    except (OSError, ValueError, sqlite3.Error):
        pass
    return {
        "ready_for_hardware_test": all(checks.values()),
        "checks": checks,
        "network_checked": False,
        "mac_to_pi_transfer_tested": False,
        "youtube_upload_tested": False,
        "owner_review_tested": False,
        "public_release_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Pi live test readiness")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--titles-file", required=True)
    args = parser.parse_args()
    report = inspect_live_readiness(
        state_dir=args.state_dir, credentials=args.credentials,
        titles_file=args.titles_file,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_hardware_test"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
