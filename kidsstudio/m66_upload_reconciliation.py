"""M66.4: classify durable Pi upload attempts without performing any network call.

STARTED is ambiguous after a crash: never initiate a second upload.
A persisted video ID may only be inspected using the existing GET-only verifier.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from .youtube_private_upload import VIDEO


def classify(row: dict | None) -> dict:
    if row is None:
        return {"status": "NO_ATTEMPT", "action": "NO_UPLOAD_DECISION"}
    state = row.get("state")
    video_id = row.get("video_id")
    if state == "STARTED":
        return {"status": "NEEDS_RECONCILIATION",
                "action": "STOP_NO_SECOND_INSERT"}
    if state in ("UPLOADED_UNVERIFIED", "PRIVATE_VERIFIED"):
        if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
            return {"status": "INVALID_JOURNAL", "action": "STOP"}
        if state == "UPLOADED_UNVERIFIED":
            return {"status": "EXISTING_VIDEO_GET_ONLY",
                    "action": "VERIFY_WITH_GET", "video_id": video_id}
        return {"status": "PRIVATE_ALREADY_VERIFIED",
                "action": "NO_UPLOAD", "video_id": video_id}
    return {"status": "UNKNOWN_STATE", "action": "STOP"}


def inspect_journal(path: Path, job_id: str) -> dict:
    if path.is_symlink() or not path.is_file() or path.suffix != ".sqlite":
        return {"status": "MISSING_JOURNAL", "action": "STOP"}
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        return {"status": "INVALID_JOB", "action": "STOP"}
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT state,video_id FROM attempts WHERE render_job_id=?",
                (job_id,),
            ).fetchone()
        return classify(dict(row) if row is not None else None)
    except (OSError, sqlite3.Error):
        return {"status": "UNREADABLE_JOURNAL", "action": "STOP"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", type=Path, required=True)
    p.add_argument("--job-id", required=True)
    args = p.parse_args(argv)
    result = inspect_journal(args.journal, args.job_id)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in (
        "EXISTING_VIDEO_GET_ONLY", "PRIVATE_ALREADY_VERIFIED"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
