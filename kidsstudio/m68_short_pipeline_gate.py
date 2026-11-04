"""M68 end-to-end private staging gate for independently registered Shorts.

Combines existing checks without modifying M65 policies or starting uploads.
"""
from __future__ import annotations

from .m68_m65_import_preflight import assess_short_import
from .m68_pi_readiness_audit import audit as audit_pi
from .m68_short_upload_audit import audit_short_upload


def assess_pipeline(queue, inbox_root, journal_path, *, handoff,
                    transfer_receipt, registry_record, render_job_id,
                    master, plan, readiness):
    preflight = assess_short_import(
        handoff, transfer_receipt, render_job_id=render_job_id,
        master=master, plan=plan, readiness=readiness)
    if preflight["status"] != "M68_SHORT_READY_FOR_M65_POLICY_VERIFICATION":
        return {"status": "SHORT_PIPELINE_BLOCKED_AT_RECEIPTS",
                "checks": preflight["checks"],
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    short_id = handoff["short_id"]
    sha = handoff["master"]["sha256"]
    pi = audit_pi(queue, inbox_root, short_id=short_id,
                  render_job_id=render_job_id, media_sha256=sha,
                  registry_record=registry_record)
    if pi["status"] != "SHORT_M65_MEDIA_VERIFIED_POLICY_CHECK_REQUIRED":
        return {"status": "SHORT_PIPELINE_BLOCKED_AT_PI",
                "pi_status": pi["status"],
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    journal = audit_short_upload(
        journal_path, short_id=short_id, render_job_id=render_job_id,
        media_sha256=sha, registry_record=registry_record)
    if journal["status"] != "NO_UPLOAD_ATTEMPT_M65_APPROVAL_REQUIRED":
        return {"status": "SHORT_PIPELINE_EXISTING_UPLOAD_RECONCILIATION",
                "journal_status": journal["status"],
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    return {"status": "SHORT_PIPELINE_PRECHECK_PASSED_M65_POLICY_REQUIRED",
            "short_id": short_id, "render_job_id": render_job_id,
            "media_sha256": sha,
            "next_action": "EXISTING_M65_OWNER_POLICY_AND_PRIVATE_UPLOAD_FLOW",
            "youtube_upload_authorized": False,
            "public_release_authorized": False}
