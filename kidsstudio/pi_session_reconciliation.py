"""Read-only, privacy-safe reconciliation of upload intents, sessions and queue.

This report cannot prove a remote YouTube session exists or was uploaded.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .pi_session_intent_audit import audit_session_intents
from .youtube_upload_session import load_session


def reconciliation_report(state_dir: str | Path) -> dict:
    state = Path(state_dir)
    sessions = state / "sessions"
    queue_path = state / "queue.sqlite"
    intents = audit_session_intents(sessions, queue_path)
    with sqlite3.connect(queue_path, timeout=10) as db:
        jobs = db.execute(
            "SELECT episode_id,channel_id,session_path,state FROM pi_upload_jobs"
        ).fetchall()
    entries = []
    for episode, channel, session_path, job_state in jobs:
        path = Path(session_path)
        exists = path.is_file() and not path.is_symlink()
        valid = False
        if exists:
            try:
                load_session(path)
                valid = True
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if valid and job_state == "completed":
            action = "review_private_youtube_upload"
        elif valid and job_state in ("pending", "running"):
            action = "resume_existing_session_only"
        elif valid and job_state == "failed":
            action = "operator_review_existing_session_before_retry"
        else:
            action = "manual_reconcile_youtube_before_retry"
        entries.append({
            "episode_id": episode,
            "queue_state": job_state,
            "session_saved": bool(exists),
            "session_valid": valid,
            "action": action,
            "automatic_new_upload_allowed": False,
        })
    for item in intents["items"]:
        entries.append({
            "episode_id": item["episode_id"],
            "queue_state": "not_queued",
            "session_saved": False,
            "session_valid": False,
            "action": "manual_reconcile_youtube_before_retry",
            "automatic_new_upload_allowed": False,
        })
    return {
        "read_only": True,
        "youtube_checked": False,
        "invalid_intents": intents["invalid_intents"],
        "pending_reconciliation": intents["pending_reconciliation"],
        "episodes": entries,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Offline Pi upload reconciliation")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.suffix.lower() != ".json" or output.exists() or output.is_symlink():
        parser.error("output must be a new JSON file")
    report = reconciliation_report(args.state_dir)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
