"""M68 prerequisites never claim an unexecuted production pilot."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_runtime_prerequisites import assess


class RuntimePrerequisiteTests(unittest.TestCase):
    @patch("kidsstudio.m68_runtime_prerequisites.shutil.which")
    def test_mac_missing_model_runtime_blocks_when_required(self, which):
        which.side_effect = lambda name: None if name == "ollama" else "/bin/" + name
        report = assess("mac", require_ollama=True)
        self.assertEqual(report["status"], "BLOCKED_MISSING_PREREQUISITES")
        self.assertIn("ollama", report["missing"])
        self.assertFalse(report["real_model_inference_verified"])
        self.assertFalse(report["public_release_authorized"])

    @patch("kidsstudio.m68_runtime_prerequisites.shutil.which")
    def test_mac_tools_do_not_mean_video_review_passed(self, which):
        which.return_value = "/bin/available"
        report = assess("mac", require_ollama=True)
        self.assertEqual(report["status"], "PREREQUISITES_PRESENT_NOT_END_TO_END_TESTED")
        self.assertFalse(report["real_model_inference_verified"])
        self.assertFalse(report["youtube_private_upload_verified"])

    @patch("kidsstudio.m68_runtime_prerequisites.shutil.which")
    def test_pi_missing_media_blocks(self, which):
        which.return_value = "/bin/available"
        report = assess("pi", db="/missing/database.db", media="/missing/video.mp4")
        self.assertIn("sqlite_database_present", report["missing"])
        self.assertIn("private_staged_media_present", report["missing"])
        self.assertFalse(report["youtube_upload_authorized"])
