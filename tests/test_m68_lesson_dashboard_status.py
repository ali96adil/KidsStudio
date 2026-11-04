"""Tests for dashboard status and release separation."""
import unittest

from kidsstudio.m68_lesson_dashboard_status import project_episode_status


class LessonDashboardStatusTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "s", "source_episode_id": "e",
                        "sha256": "a" * 64}
        self.review = {"short_id": "s", "source_episode_id": "e",
                       "video_sha256": "a" * 64,
                       "checks": {"pedagogy": True, "source_consistency": True},
                       "youtube_upload_authorized": False,
                       "public_release_authorized": False}

    def test_model_pass_is_not_upload_approval(self):
        row = project_episode_status(
            self.handoff, {"status": "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
                           "review": self.review, "attempts": [{}]})
        self.assertEqual(row["stage"], "EDUCATIONAL_SCRIPT_MODEL_PASS")
        self.assertEqual(row["remaining_revision_attempts"], 2)
        self.assertFalse(row["media_quality_verified"])
        self.assertFalse(row["public_release_authorized"])

    def test_rejects_forged_pass(self):
        self.review["checks"]["pedagogy"] = False
        with self.assertRaises(ValueError):
            project_episode_status(
                self.handoff, {"status": "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
                               "review": self.review, "attempts": []})

    def test_triage_after_three_attempts(self):
        row = project_episode_status(
            self.handoff, {"status": "LESSON_REVISION_LIMIT_REACHED",
                           "review": self.review, "attempts": [{}, {}, {}]})
        self.assertEqual(row["stage"], "EDUCATIONAL_REVIEW_NEEDS_TRIAGE")
        self.assertEqual(row["remaining_revision_attempts"], 0)

    def test_technical_failure(self):
        row = project_episode_status(
            self.handoff, {"status": "LESSON_AUTO_CYCLE_FAILED"})
        self.assertEqual(row["stage"], "EDUCATIONAL_REVIEW_TECHNICAL_FAILURE")
