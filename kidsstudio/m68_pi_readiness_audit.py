"""M68 Pi-side read-only derived-short readiness audit.

A verified short must be independently approved by the existing M65
ordinary-inbox policy. This audit does not create an approval or upload job.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .studio_queue import StudioQueue
from .pi_ordinary_inbox import PiOrdinaryInbox


class ShortPiReadinessError(ValueError):
    pass


def audit(queue, inbox_root, *, short_id, render_job_id, media_sha256,
          registry_record):
    if (not isinstance(registry_record, dict)
            or registry_record.get("short_id") != short_id
            or registry_record.get("media_sha256") != media_sha256
            or registry_record.get("status") != "PI_STAGED_NOT_APPROVED"):
        raise ShortPiReadinessError("staged short registry mismatch")
    inbox = PiOrdinaryInbox(queue, inbox_root)
    try:
        accepted = inbox.verify(render_job_id, full_sha=True)
    except (ValueError, OSError, KeyError) as exc:
        return {
            "status": "SHORT_NOT_ACCEPTED_BY_M65",
            "short_id": short_id,
            "reason": type(exc).__name__,
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
    if accepted["master_sha256"] != media_sha256:
        raise ShortPiReadinessError("M65 accepted a different video")
    return {
        "status": "SHORT_M65_MEDIA_VERIFIED_POLICY_CHECK_REQUIRED",
        "short_id": short_id,
        "render_job_id": render_job_id,
        "media_sha256": media_sha256,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--inbox-root", type=Path, required=True)
    p.add_argument("--short-id", required=True)
    p.add_argument("--render-job-id", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--registry-record", type=Path, required=True)
    args = p.parse_args(argv)
    report = audit(
        StudioQueue(args.db), args.inbox_root,
        short_id=args.short_id, render_job_id=args.render_job_id,
        media_sha256=args.sha256,
        registry_record=json.loads(args.registry_record.read_text(encoding="utf-8")))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "SHORT_M65_MEDIA_VERIFIED_POLICY_CHECK_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
