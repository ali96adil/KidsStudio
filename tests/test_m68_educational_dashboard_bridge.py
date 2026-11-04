"""Tests for read-only educational dashboard ingestion."""
import unittest

from kidsstudio.m68_educational_dashboard_bridge import build_educational_dashboard


class EducationalDashboardBridgeTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "s", "source_episode_id": "e",
                        "sha256": "a" * 64}
        self.cycle = {
            "status": "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
            "attempts": [],
            "review": {"short_id": "s", "source_episode_id": "e",
                       "video_sha256": "a" * 64,
                       "checks": {"pedagogy": True, "source_consistency": True},
                       "youtube_upload_authorized": False,
                       "public_release_authorized": False}}

    def test_series_dashboard(self):
        result = build_educational_dashboard([
            {"series_id": "colors", "handoff": self.handoff, "cycle": self.cycle}])
        self.assertEqual(result["total_episodes"], 1)
        self.assertEqual(result["series"][0]["educational_script_pass"], 1)
        self.assertFalse(result["youtube_upload_authorized"])

    def test_duplicate_rejected(self):
        item = {"series_id": "colors", "handoff": self.handoff, "cycle": self.cycle}
        with self.assertRaises(ValueError):
            build_educational_dashboard([item, item])

    def test_forged_release_rejected(self):
        self.cycle["review"]["youtube_upload_authorized"] = True
        with self.assertRaises(ValueError):
            build_educational_dashboard([
                {"series_id": "colors", "handoff": self.handoff, "cycle": self.cycle}])
