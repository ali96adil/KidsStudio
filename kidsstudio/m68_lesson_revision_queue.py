"""Convert pinned failed lesson-model findings into a bounded revision task.

The task is an instruction to a future script agent, not an automatic rewrite,
approval, upload, or permission to change the source without a new review.
"""
from __future__ import annotations

import json
import re

SHA = re.compile(r"^[0-9a-f]{64}$")
AXES = {"pedagogy", "source_consistency"}
DECISIONS = {"PASS", "UNSURE", "NEEDS_FIX"}


def plan_revision(handoff, receipt):
    if not isinstance(handoff, dict) or not isinstance(receipt, dict):
        raise ValueError("handoff and review receipt required")
    if (receipt.get("short_id") != handoff.get("short_id")
            or receipt.get("source_episode_id") != handoff.get("source_episode_id")
            or receipt.get("video_sha256") != handoff.get("sha256")
            or not isinstance(receipt.get("script_sha256"), str)
            or not SHA.fullmatch(receipt["script_sha256"])
            or receipt.get("status") !=
            "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED"
            or receipt.get("youtube_upload_authorized") is not False
            or receipt.get("public_release_authorized") is not False):
        raise ValueError("untrusted or mismatched educational review")
    findings = receipt.get("review_findings")
    if not isinstance(findings, list) or len(findings) != 4:
        raise ValueError("two-model findings required")
    seen = set()
    fixes = []
    for row in findings:
        if not isinstance(row, dict) or set(row) != {
                "reviewer_model", "axis", "decision", "evidence"}:
            raise ValueError("invalid finding")
        model, axis, decision, evidence = (
            row["reviewer_model"], row["axis"],
            row["decision"], row["evidence"])
        if (not isinstance(model, str) or not 3 <= len(model) <= 120
                or axis not in AXES or decision not in DECISIONS
                or not isinstance(evidence, str)
                or not 25 <= len(evidence.strip()) <= 800):
            raise ValueError("invalid model finding")
        seen.add((model, axis))
        if decision != "PASS":
            fixes.append({"axis": axis, "decision": decision,
                          "reviewer_model": model, "evidence": evidence})
    if len(seen) != 4 or len({model for model, _ in seen}) != 2:
        raise ValueError("distinct model and axis findings required")
    checks = receipt.get("checks")
    if (not isinstance(checks, dict) or set(checks) != AXES
            or any(type(value) is not bool for value in checks.values())
            or any(checks[axis] != all(
                row["decision"] == "PASS" for row in findings
                if row["axis"] == axis) for axis in AXES)):
        raise ValueError("model findings do not match recorded checks")
    return {
        "status": "LESSON_REVISION_REQUIRED" if fixes else "LESSON_MODEL_PASS_NO_REVISION",
        "short_id": handoff["short_id"],
        "source_episode_id": handoff["source_episode_id"],
        "video_sha256": handoff["sha256"],
        "script_sha256": receipt["script_sha256"],
        "assigned_role": "script_revision_agent" if fixes else None,
        "issues": fixes,
        "requires_new_script_hash_and_full_review": bool(fixes),
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
