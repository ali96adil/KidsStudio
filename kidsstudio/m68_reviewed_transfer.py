"""M68 fail-closed verification of content QA before Mac-to-Pi transfer.

Existing transfer helpers accept a PASS decision; this gate additionally
requires the complete six-axis review receipt and immutable media digest.
"""
from __future__ import annotations

from .m68_short_content_review import CHECKS
from .m67_master_handoff import verify_inventory
from .m68_short_resume import resume_short


class ShortQATransferError(ValueError):
    pass


def validate_review(root, handoff, receipt):
    if (not isinstance(receipt, dict)
            or receipt.get("status") != "SHORT_CONTENT_QA_RECORDED"
            or receipt.get("decision") != "PASS"
            or receipt.get("short_id") != handoff.get("short_id")
            or receipt.get("source_episode_id") != handoff.get("source_episode_id")
            or receipt.get("youtube_upload_authorized") is not False
            or receipt.get("public_release_authorized") is not False):
        raise ShortQATransferError("approved private short review required")
    checks = receipt.get("checks")
    if (not isinstance(checks, dict) or set(checks) != set(CHECKS)
            or any(checks[key] is not True for key in CHECKS)
            or not isinstance(receipt.get("reviewer"), str)
            or not 3 <= len(receipt["reviewer"].strip()) <= 100):
        raise ShortQATransferError("six complete content checks and reviewer required")
    digest = verify_inventory(root, handoff)["sha256"]
    if receipt.get("video_sha256") != digest:
        raise ShortQATransferError("review does not match current MP4")
    return digest


def transfer_reviewed_short(root, handoff, receipt, *, host, user,
                            remote_dir, runner=None):
    digest = validate_review(root, handoff, receipt)
    result = resume_short(root, handoff, receipt, host=host, user=user,
                          remote_dir=remote_dir, runner=runner)
    if result["sha256"] != digest:
        raise ShortQATransferError("Pi transfer digest mismatch")
    return result
