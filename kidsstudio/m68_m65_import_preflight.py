"""M68 Shorts: inspect compatibility with the existing Pi inbox.

This module never creates an upload job or grants upload permission.
"""
from __future__ import annotations

from .m67_pi_receipts_preflight import preflight


def assess_short_import(handoff, transfer_receipt, *, render_job_id=None,
                        master=None, plan=None, readiness=None):
    checks = {
        "independent_short": (
            handoff.get("episode_id") == handoff.get("short_id")
            and bool(handoff.get("short_id"))
            and handoff.get("status") == "SHORT_HASH_PINNED_CONTENT_QA_PENDING"),
        "staged_on_pi": (
            transfer_receipt.get("status") == "SHORT_PI_STAGED_REQUIRES_M65_INBOX"),
        "matching_short": (
            transfer_receipt.get("short_id") == handoff.get("short_id")
            and transfer_receipt.get("source_episode_id") == handoff.get("source_episode_id")),
        "matching_sha": (
            transfer_receipt.get("sha256") == handoff.get("master", {}).get("sha256")),
        "private_only": (
            handoff.get("public_release_authorized") is False
            and handoff.get("youtube_upload_authorized") is False
            and transfer_receipt.get("public_release_authorized") is False
            and transfer_receipt.get("youtube_upload_authorized") is False),
    }
    receipt_check = None
    if all(checks.values()) and all(x is not None for x in (
            render_job_id, master, plan, readiness)):
        receipt_check = preflight(
            master=master, plan=plan, readiness=readiness,
            render_job_id=render_job_id,
            expected_sha256=handoff["master"]["sha256"])
    checks["m65_receipts_consistent"] = bool(
        receipt_check and receipt_check["status"] ==
        "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL")
    ready = all(checks.values())
    return {
        "status": ("M68_SHORT_READY_FOR_M65_POLICY_VERIFICATION"
                   if ready else "M68_SHORT_M65_IMPORT_BLOCKED"),
        "checks": checks,
        "next_action": ("VERIFY_EXISTING_M65_POLICY_AND_INBOX"
                        if ready else "REQUIRE_APPROVED_INDEPENDENT_RENDER_JOB"),
        "pi_upload_authorized": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
