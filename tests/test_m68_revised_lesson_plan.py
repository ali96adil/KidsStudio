"""Tests for preparing a revised educational plan from an AI script proposal."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m68_revised_lesson_plan import prepare_revised_lesson


class RevisedLessonPlanTests(unittest.TestCase):
    def test_preserves_original_objective_and_requires_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "original.txt"
            revised_script = root / "revised.txt"
            original_plan = root / "lesson.json"
            revised_plan = root / "revised_lesson.json"
            script.write_text("Learn the color red.", encoding="utf-8")
            revised_script.write_text("Learn the color red. Can you find red?",
                                      encoding="utf-8")
            handoff = {"short_id": "short-1", "source_episode_id": "episode-1",
                       "sha256": "a" * 64}
            plan = {
                "schema_version": 1, "short_id": "short-1",
                "source_episode_id": "episode-1", "video_sha256": "a" * 64,
                "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "language": "en",
                "learning_objective": "Recognize the color red in daily objects.",
                "age_range": "Children aged three to five years.",
                "teaching_method": "Show familiar objects and ask for red ones.",
                "assessment_question": "Can you point to an object that is red?",
                "fact_check_reference": "Approved original color curriculum notes.",
            }
            original_plan.write_text(json.dumps(plan), encoding="utf-8")
            proposal = {
                "status": "REVISION_PROPOSAL_WRITTEN_REVIEW_REQUIRED",
                "output_path": str(revised_script),
                "script_sha256": hashlib.sha256(revised_script.read_bytes()).hexdigest(),
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
            result = prepare_revised_lesson(
                handoff, original_script_path=script,
                original_lesson_path=original_plan,
                revised_script_path=revised_script,
                revised_lesson_path=revised_plan, proposal=proposal)
            self.assertEqual(result["status"], "REVISED_LESSON_READY_FOR_FRESH_AI_REVIEW")
            self.assertEqual(json.loads(revised_plan.read_text())["learning_objective"],
                             plan["learning_objective"])
            self.assertEqual(json.loads(original_plan.read_text()), plan)
            self.assertFalse(result["youtube_upload_authorized"])
            with self.assertRaises(FileExistsError):
                prepare_revised_lesson(
                    handoff, original_script_path=script,
                    original_lesson_path=original_plan,
                    revised_script_path=revised_script,
                    revised_lesson_path=revised_plan, proposal=proposal)
