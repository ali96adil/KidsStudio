"""Create a new lesson-plan revision bound to a newly rewritten script.

Preserves educational objectives; never modifies the original lesson plan.
A revised script requires fresh model reviews before production.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .m68_lesson_evidence import audit_lesson


def prepare_revised_lesson(handoff, *, original_script_path, original_lesson_path,
                           revised_script_path, revised_lesson_path,
                           proposal):
    if (not isinstance(proposal, dict)
            or proposal.get("status") != "REVISION_PROPOSAL_WRITTEN_REVIEW_REQUIRED"
            or proposal.get("youtube_upload_authorized") is not False
            or proposal.get("public_release_authorized") is not False):
        raise ValueError("valid unapproved script revision proposal required")
    original = audit_lesson(
        handoff, script_path=original_script_path, lesson_path=original_lesson_path)
    if original["reasons"]:
        raise ValueError("original lesson evidence invalid")
    source = Path(original_lesson_path)
    script = Path(revised_script_path)
    destination = Path(revised_lesson_path)
    for path in (script, destination):
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("absolute non-symlink paths required")
    if (not script.is_file() or not 1 <= script.stat().st_size <= 16000
            or script.resolve() == Path(original_script_path).resolve()
            or destination.resolve() == source.resolve()):
        raise ValueError("invalid revised script or destination")
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    if (digest != proposal.get("script_sha256")
            or proposal.get("output_path") != str(script)):
        raise ValueError("revised script does not match proposal")
    lesson_bytes = source.read_bytes()
    lesson = json.loads(lesson_bytes)
    revised = dict(lesson)
    revised["script_sha256"] = digest
    revised_bytes = (json.dumps(revised, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if source.read_bytes() != lesson_bytes:
        raise ValueError("original lesson changed during revision")
    with destination.open("xb") as handle:
        handle.write(revised_bytes)
    evidence = audit_lesson(handoff, script_path=script, lesson_path=destination)
    if evidence["reasons"]:
        raise ValueError("revised lesson evidence invalid")
    return {"status": "REVISED_LESSON_READY_FOR_FRESH_AI_REVIEW",
            "revised_lesson_path": str(destination),
            "revised_script_sha256": digest,
            "source_lesson_preserved": True,
            "requires_new_model_review": True,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}
