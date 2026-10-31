"""Conservative bridge from pinned actual audio evidence into M68 diagnostics.

Only explicit MP4-bound evidence from a qualified audio pipeline is accepted.
This never treats text-only AI as having listened to the soundtrack, and
never authorizes upload or publication.
"""
from __future__ import annotations

import re

SHA = re.compile(r"^[0-9a-f]{64}$")


def audit_audio_receipt(handoff, receipt):
    if not isinstance(handoff, dict) or not isinstance(receipt, dict):
        raise ValueError("handoff and audio receipt objects required")
    sha = handoff.get("sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("valid pinned short SHA required")
    if (receipt.get("short_id") != handoff.get("short_id")
            or receipt.get("source_episode_id") != handoff.get("source_episode_id")
            or receipt.get("video_sha256") != sha):
        raise ValueError("audio evidence is not bound to current short")
    if (receipt.get("review_scope") != "ACTUAL_MP4_AUDIO_OBSERVED"
            or receipt.get("audio_review_completed") is not True
            or receipt.get("independent_reviewers") != 2
            or receipt.get("audio_decision") not in ("PASS", "REJECT")
            or not isinstance(receipt.get("evidence"), str)
            or not 25 <= len(receipt["evidence"].strip()) <= 2000
            or not isinstance(receipt.get("audio_sha256"), str)
            or not SHA.fullmatch(receipt["audio_sha256"])
            or not isinstance(receipt.get("reviewer_model_hashes"), list)
            or len(receipt["reviewer_model_hashes"]) != 2
            or len(set(receipt["reviewer_model_hashes"])) != 2
            or any(not isinstance(x, str) or not SHA.fullmatch(x)
                   for x in receipt["reviewer_model_hashes"])):
        raise ValueError("audio review evidence incomplete or unqualified")
    return {
        "audio_check": receipt["audio_decision"] == "PASS",
        "status": "AUDIO_EVIDENCE_REPORTED_NOT_INDEPENDENTLY_ATTESTED",
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
