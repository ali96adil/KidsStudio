"""Validate reported local educational AI judgments without granting trust."""
from __future__ import annotations

import re

SHA = re.compile(r"^[0-9a-f]{64}$")


def audit_lesson_model_receipt(handoff, lesson, receipt):
    if not isinstance(receipt, dict) or not isinstance(lesson, dict):
        raise ValueError("lesson model receipt and source evidence required")
    if (receipt.get("status") != "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED"
            or receipt.get("short_id") != handoff.get("short_id")
            or receipt.get("source_episode_id") != handoff.get("source_episode_id")
            or receipt.get("video_sha256") != handoff.get("sha256")
            or receipt.get("script_sha256") != lesson.get("script_sha256")
            or receipt.get("model_claims_independently_attested") is not False
            or receipt.get("video_script_fidelity_verified") is not False
            or receipt.get("youtube_upload_authorized") is not False
            or receipt.get("public_release_authorized") is not False):
        raise ValueError("untrusted or mismatched lesson model receipt")
    hashes = receipt.get("model_response_sha256")
    if (not isinstance(hashes, list) or len(hashes) != 2
            or len(set(hashes)) != 2
            or any(not isinstance(value, str) or not SHA.fullmatch(value)
                   for value in hashes)):
        raise ValueError("two distinct model response hashes required")
    checks = receipt.get("checks")
    if (not isinstance(checks, dict)
            or set(checks) != {"pedagogy", "source_consistency"}
            or any(type(value) is not bool for value in checks.values())):
        raise ValueError("exact model lesson checks required")
    return {
        "status": "LESSON_MODEL_CLAIMS_RECORDED_NOT_ATTESTED",
        "model_reported_pedagogy_pass": checks["pedagogy"],
        "model_reported_script_lesson_match": checks["source_consistency"],
        "video_script_fidelity_verified": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
