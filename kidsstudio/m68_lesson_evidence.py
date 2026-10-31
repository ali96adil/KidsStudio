"""Read-only educational script provenance diagnostic for M68.

A script and lesson plan can be checked for integrity and declared educational
intent. This is NOT a factual accuracy assessment or pedagogical AI review.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{64}$")


def audit_lesson(handoff, *, script_path, lesson_path):
    if not isinstance(handoff, dict):
        raise ValueError("handoff required")
    if (not isinstance(handoff.get("sha256"), str)
            or not SHA.fullmatch(handoff["sha256"])):
        raise ValueError("valid pinned video identity required")
    script = Path(script_path)
    lesson = Path(lesson_path)
    for path in (script, lesson):
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("absolute regular source files required")
        if not 1 <= path.stat().st_size <= 16000:
            raise ValueError("source file outside size limit")
    script_bytes = script.read_bytes()
    try:
        script_text = script_bytes.decode("utf-8")
        doc = json.loads(lesson.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid UTF-8 lesson evidence") from exc
    if not isinstance(doc, dict):
        raise ValueError("lesson plan must be an object")
    sha = hashlib.sha256(script_bytes).hexdigest()
    reasons = []
    if not script_text.strip():
        reasons.append("script_empty")
    if doc.get("schema_version") != 1:
        reasons.append("lesson_schema_invalid")
    if doc.get("short_id") != handoff.get("short_id"):
        reasons.append("short_id_mismatch")
    if doc.get("source_episode_id") != handoff.get("source_episode_id"):
        reasons.append("source_episode_id_mismatch")
    if doc.get("video_sha256") != handoff.get("sha256"):
        reasons.append("video_sha256_mismatch")
    if (not isinstance(doc.get("script_sha256"), str)
            or not SHA.fullmatch(doc["script_sha256"])
            or doc["script_sha256"] != sha):
        reasons.append("script_sha256_mismatch")
    if doc.get("language") not in ("ar", "en"):
        reasons.append("language_missing")
    for field in ("learning_objective", "age_range", "teaching_method",
                  "assessment_question", "fact_check_reference"):
        value = doc.get(field)
        if not isinstance(value, str) or not 8 <= len(value.strip()) <= 1000:
            reasons.append(field + "_missing")
    return {
        "status": "LESSON_PLAN_DOCUMENTED_NOT_PEDAGOGICALLY_VERIFIED"
                  if not reasons else "BLOCKED_LESSON_PLAN",
        "short_id": handoff.get("short_id"),
        "script_sha256": sha,
        "reasons": reasons,
        "pedagogy_independently_verified": False,
        "source_consistency_independently_verified": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
