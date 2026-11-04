"""M68 one-command local lesson review orchestration tests."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_lesson_review_run import run


class LessonReviewRunTests(unittest.TestCase):
    def setUp(self):
        self.args = {
            "script_path": "/tmp/script", "lesson_path": "/tmp/lesson",
            "first_endpoint": "http://127.0.0.1:11434/api/chat",
            "first_model": "model-one",
            "second_endpoint": "http://127.0.0.1:11435/api/chat",
            "second_model": "model-two",
        }
        self.handoff = {"short_id": "s", "source_episode_id": "e",
                        "sha256": "a" * 64}

    def test_missing_model_never_runs_inference(self):
        with patch("kidsstudio.m68_lesson_review_run.review_lesson") as inference:
            result = run(self.handoff, **self.args, inspector=lambda _: {
                "reachable": True, "models": ["model-one"]})
        self.assertEqual(result["status"], "LESSON_REVIEW_BLOCKED_MODELS_NOT_READY")
        inference.assert_not_called()
        self.assertFalse(result["youtube_upload_authorized"])

    def test_ready_models_invoke_real_review_adapter(self):
        receipt = {"status": "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED",
                   "checks": {"pedagogy": True, "source_consistency": True},
                   "youtube_upload_authorized": False,
                   "public_release_authorized": False}
        with patch("kidsstudio.m68_lesson_review_run.review_lesson",
                   return_value=receipt) as inference:
            result = run(self.handoff, **self.args, inspector=lambda _: {
                "reachable": True, "models": ["model-one", "model-two"]})
        inference.assert_called_once()
        self.assertEqual(result["review"], receipt)
        self.assertEqual(result["status"], "LESSON_REVIEW_MODEL_PASS_RECORDED")
        self.assertFalse(result["public_release_authorized"])

    def test_model_rejection_is_needs_fix_not_success(self):
        receipt = {"checks": {"pedagogy": False, "source_consistency": True},
                   "youtube_upload_authorized": False,
                   "public_release_authorized": False}
        with patch("kidsstudio.m68_lesson_review_run.review_lesson",
                   return_value=receipt):
            result = run(self.handoff, **self.args, inspector=lambda _: {
                "reachable": True, "models": ["model-one", "model-two"]})
        self.assertEqual(result["status"], "LESSON_REVIEW_NEEDS_FIX")
        self.assertFalse(result["youtube_upload_authorized"])
