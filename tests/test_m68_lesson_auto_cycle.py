"""End-to-end simulated educational review/rewrite loop tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m68_lesson_auto_cycle import run_cycle


class FakeReviewer:
    def __init__(self, model):
        self.model = model
        self.endpoint = "http://127.0.0.1:" + ("11434" if model == "first" else "11435") + "/api/chat"

    def run(self, *, script, lesson):
        decision = "PASS" if "assessment" in script else "NEEDS_FIX"
        answer = {"checks": {
            "pedagogy": {"decision": decision,
                         "evidence": "The script includes an assessment question." if decision == "PASS"
                         else "The script has no assessment question for the learner."},
            "source_consistency": {"decision": "PASS",
                                   "evidence": "The script matches the stated educational goal."}},
            "summary": "The script requires an explicit assessment question."}
        return answer, hashlib.sha256((self.model + script).encode()).hexdigest()


class FakeRewriter:
    def rewrite(self, *, script, lesson, issues):
        return {"revised_script": script + "\nassessment: Which one is red?",
                "change_summary": "Added a simple assessment question for the child."}


class AutoCycleTests(unittest.TestCase):
    def test_one_revision_then_two_model_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "script.txt"
            lesson = root / "lesson.json"
            script.write_text("This is red.", encoding="utf-8")
            handoff = {"short_id": "short-1", "source_episode_id": "ep-1",
                       "sha256": "a" * 64}
            lesson.write_text(json.dumps({
                "schema_version": 1, "short_id": "short-1",
                "source_episode_id": "ep-1", "video_sha256": "a" * 64,
                "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "language": "en",
                "learning_objective": "Identify the color red in daily life.",
                "age_range": "Children aged three to five years.",
                "teaching_method": "Show everyday objects and ask about red.",
                "assessment_question": "Which object in the scene is red?",
                "fact_check_reference": "Original reviewed educational color notes.",
            }), encoding="utf-8")
            result = run_cycle(
                handoff, script_path=script, lesson_path=lesson,
                output_dir=root, first=FakeReviewer("first"),
                second=FakeReviewer("second"), rewriter=FakeRewriter())
            self.assertEqual(result["status"], "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL")
            self.assertEqual(len(result["attempts"]), 1)
            self.assertEqual(script.read_text(), "This is red.")
            self.assertFalse(result["public_release_authorized"])

    def test_max_attempts_rejects_invalid(self):
        with self.assertRaises(ValueError):
            run_cycle({}, script_path="x", lesson_path="y", output_dir="/tmp",
                      first=None, second=None, rewriter=None, max_attempts=4)
