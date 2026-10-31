"""Dashboard store integration tests."""
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m68_educational_dashboard_store import record_cycle
from kidsstudio.m68_educational_dashboard_bridge import load_educational_dashboard


class EducationalDashboardStoreTests(unittest.TestCase):
    def test_upsert_and_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dashboard.json"
            handoff = {"short_id": "s", "source_episode_id": "episode-1",
                       "sha256": "a" * 64}
            review = {"short_id": "s", "source_episode_id": "episode-1",
                      "video_sha256": "a" * 64,
                      "checks": {"pedagogy": True, "source_consistency": True},
                      "youtube_upload_authorized": False,
                      "public_release_authorized": False}
            cycle = {"status": "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
                     "review": review, "attempts": []}
            record_cycle(target, series_id="colors", handoff=handoff, cycle=cycle)
            record_cycle(target, series_id="colors", handoff=handoff, cycle=cycle)
            self.assertEqual(load_educational_dashboard(target)["total_episodes"], 1)
            self.assertEqual(len(json.loads(target.read_text())), 1)

    def test_invalid_review_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dashboard.json"
            with self.assertRaises(ValueError):
                record_cycle(target, series_id="colors",
                             handoff={"short_id": "s", "source_episode_id": "e",
                                      "sha256": "a" * 64},
                             cycle={"status": "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
                                    "review": {}, "attempts": []})
            self.assertFalse(target.exists())
