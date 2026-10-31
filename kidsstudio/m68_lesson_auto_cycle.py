"""Bounded local educational review/rewrite loop for M68.

This is script-only AI review, not rendered-video approval or publication.
Each revision is preserved as separate files; all reviews use exact script hash.
"""
from __future__ import annotations

from pathlib import Path

from .m68_local_lesson_review import review_lesson
from .m68_lesson_revision_queue import plan_revision
from .m68_lesson_revision_lifecycle import start_revision
from .m68_local_script_rewriter import propose_revision
from .m68_revised_lesson_plan import prepare_revised_lesson


def run_cycle(handoff, *, script_path, lesson_path, output_dir,
              first, second, rewriter, max_attempts=3):
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
        raise ValueError("revision attempts must be between 1 and 3")
    directory = Path(output_dir)
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("existing absolute output directory required")
    script = Path(script_path)
    lesson = Path(lesson_path)
    previous = None
    attempts = []
    for round_number in range(max_attempts + 1):
        receipt = review_lesson(handoff, script_path=script, lesson_path=lesson,
                                first=first, second=second)
        task = plan_revision(handoff, receipt)
        if task["status"] == "LESSON_MODEL_PASS_NO_REVISION":
            return {"status": "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
                    "final_script_path": str(script),
                    "final_lesson_path": str(lesson),
                    "review": receipt, "attempts": attempts,
                    "youtube_upload_authorized": False,
                    "public_release_authorized": False}
        if round_number >= max_attempts:
            return {"status": "LESSON_REVISION_LIMIT_REACHED",
                    "review": receipt, "attempts": attempts,
                    "requires_manual_triage": True,
                    "youtube_upload_authorized": False,
                    "public_release_authorized": False}
        state = start_revision(task, previous=previous)
        new_script = directory / ("script_revision_%02d.txt" % (round_number + 1))
        new_lesson = directory / ("lesson_revision_%02d.json" % (round_number + 1))
        proposal = propose_revision(
            state, script_path=script, lesson_path=lesson,
            output_path=new_script, rewriter=rewriter)
        plan = prepare_revised_lesson(
            handoff, original_script_path=script, original_lesson_path=lesson,
            revised_script_path=new_script, revised_lesson_path=new_lesson,
            proposal=proposal)
        previous = proposal["lifecycle"]
        attempts.append({"attempt": round_number + 1,
                         "script_path": str(new_script),
                         "lesson_path": str(new_lesson),
                         "script_sha256": plan["revised_script_sha256"]})
        script, lesson = new_script, new_lesson
    raise AssertionError("unreachable review cycle state")
