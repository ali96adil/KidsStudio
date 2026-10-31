"""Read-only M68 short content review report; never grants upload rights."""
from __future__ import annotations

import json

from .m68_short_content_review import CHECKS


def inspect(queue, short_id):
    if not isinstance(short_id, str) or not short_id.strip():
        raise ValueError("short_id required")
    with queue._connection() as db:
        row = db.execute(
            """SELECT r.*, s.state AS short_state, s.media_sha256 AS staged_sha
               FROM studio_short_reviews r
               JOIN studio_derived_shorts s ON s.short_id=r.short_id
               WHERE r.short_id=?""", (short_id,)).fetchone()
    if not row:
        return {"short_id": short_id, "status": "NO_REVIEW", "upload_authorized": False}
    try:
        checks = json.loads(row["checks_json"])
        evidence = json.loads(row["ai_evidence_json"]) if row["ai_evidence_json"] else None
    except (ValueError, TypeError):
        return {"short_id": short_id, "status": "REVIEW_EVIDENCE_INVALID",
                "upload_authorized": False, "public_release_authorized": False}
    consistent = (row["short_state"] == "PI_STAGED_NOT_APPROVED"
                  and row["staged_sha"] == row["media_sha256"]
                  and isinstance(checks, dict) and set(checks) == set(CHECKS)
                  and all(type(checks[k]) is bool for k in CHECKS)
                  and (row["decision"] == "PASS") == all(checks.values())
                  and (evidence is None or
                       (isinstance(evidence, dict) and set(evidence) == set(CHECKS)
                        and all(isinstance(evidence[k], str)
                                and 12 <= len(evidence[k].strip()) <= 2000
                                for k in CHECKS))))
    return {
        "short_id": row["short_id"],
        "source_episode_id": row["source_episode_id"],
        "media_sha256": row["media_sha256"],
        "decision": row["decision"] if consistent else "INVALID",
        "reviewer": row["reviewer"],
        "checks": checks,
        "ai_evidence": evidence,
        "created_at": row["created_at"],
        "status": "REVIEW_EVIDENCE_CONSISTENT" if consistent else "REVIEW_EVIDENCE_INVALID",
        "upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    import argparse
    from .studio_queue import StudioQueue
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--short-id", required=True)
    args = parser.parse_args(argv)
    queue = StudioQueue(args.db)
    try:
        report = inspect(queue, args.short_id)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc),
                          "upload_authorized": False}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "REVIEW_EVIDENCE_CONSISTENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
