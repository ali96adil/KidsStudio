"""M67 status board unit tests."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_episode_status import summarize


class EpisodeStatusTests(unittest.TestCase):
    def test_missing_steps_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            result = summarize(temp)
            self.assertTrue(all(s["status"] == "NOT_RECORDED"
                                for s in result["steps"]))
            self.assertFalse(result["pi_upload_authorized"])

    def test_reports_existing_step(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "comfy_batch_report.json").write_text(
                json.dumps({"status": "IMAGES_GENERATED_PENDING_QA"}))
            result = summarize(temp)
            images = next(x for x in result["steps"] if x["stage"] == "images")
            self.assertEqual(images["status"], "IMAGES_GENERATED_PENDING_QA")
