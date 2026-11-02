"""Read-only diagnostics for private resumable upload sessions.

No credentials, session URLs, or video paths are emitted in reports.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .pi_upload_queue import PiUploadQueue
from .youtube_upload_session import load_session


def audit_sessions(queue: PiUploadQueue, session_dir: str | Path) -> dict:
    root = Path(session_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid session directory")
    counts = {"valid": 0, "corrupt": 0, "orphaned": 0,
              "queued": 0, "failed": 0, "completed": 0}
    problems = []
    with sqlite3.connect(queue.path, timeout=10) as db:
        rows = db.execute("SELECT session_path,state FROM pi_upload_jobs").fetchall()
    jobs = {str(Path(path).absolute()): state for path, state in rows}
    seen = set()
    for path in sorted(root.glob("*.json")):
        # Report only a safe count, not untrusted filenames or secret URLs.
        if path.is_symlink():
            counts["corrupt"] += 1
            problems.append("invalid_session")
            continue
        try:
            load_session(path)
        except (OSError, ValueError, KeyError, TypeError):
            counts["corrupt"] += 1
            problems.append("invalid_session")
            continue
        counts["valid"] += 1
        seen.add(str(path.absolute()))
        state = jobs.get(str(path.absolute()))
        if state is None:
            counts["orphaned"] += 1
        elif state == "failed":
            counts["failed"] += 1
        elif state == "completed":
            counts["completed"] += 1
        else:
            counts["queued"] += 1
    missing = sum(1 for path in jobs if path not in seen and not Path(path).is_file())
    counts["missing"] = missing
    if missing:
        problems.append("missing_queued_session")
    return {"healthy": counts["corrupt"] == 0 and counts["orphaned"] == 0 and missing == 0,
            "counts": counts, "problems": problems,
            "network_checked": False, "youtube_upload_tested": False}
