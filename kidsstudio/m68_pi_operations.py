"""Read-only Pi M68 operational dashboard snapshot.

No queue initialization, token access, uploads, or policy mutations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_queue import StudioQueue
from .m68_short_review_report import inspect


def snapshot(queue):
    with queue._connection() as db:
        shorts = db.execute(
            """SELECT short_id,source_episode_id,media_sha256,state
               FROM studio_derived_shorts ORDER BY short_id""").fetchall()
        attempts = {row["short_id"]: dict(row) for row in db.execute(
            """SELECT short_id,state,video_id,updated_at
               FROM studio_short_upload_attempts""")}
        reservations = {row["short_id"]: dict(row) for row in db.execute(
            """SELECT short_id,state,created_at
               FROM studio_short_quota_reservations""")}
    items = []
    counts = {"registered": 0, "staged": 0, "review_pass": 0,
              "review_blocked": 0, "attempt_uncertain": 0,
              "manual_reconciliation": 0, "private_verified": 0}
    for short in shorts:
        sid = short["short_id"]
        report = inspect(queue, sid)
        attempt = attempts.get(sid)
        state = short["state"]
        counts["staged" if state == "PI_STAGED_NOT_APPROVED" else "registered"] += 1
        if report["status"] == "REVIEW_EVIDENCE_CONSISTENT" and report["decision"] == "PASS":
            counts["review_pass"] += 1
        else:
            counts["review_blocked"] += 1
        if attempt:
            category = {"STARTED_UNCERTAIN": "attempt_uncertain",
                        "MANUAL_RECONCILIATION": "manual_reconciliation",
                        "PRIVATE_VERIFIED": "private_verified"}.get(attempt["state"])
            if category:
                counts[category] += 1
        items.append({
            "short_id": sid, "source_episode_id": short["source_episode_id"],
            "state": state, "review_status": report["status"],
            "review_decision": report.get("decision"),
            "reservation_state": reservations.get(sid, {}).get("state"),
            "attempt_state": attempt["state"] if attempt else None,
            "youtube_video_id": attempt["video_id"] if attempt else None,
            "upload_authorized": False, "public_release_authorized": False,
        })
    return {"status": "READ_ONLY_M68_PI_SNAPSHOT",
            "counts": counts, "shorts": items,
            "upload_authorized": False, "public_release_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(json.dumps({"status": "BLOCKED", "reason": "database missing"}))
        return 2
    try:
        report = snapshot(StudioQueue(args.db))
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
