"""Local dependencies probe must not launch executables or connect to Pi."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_local_dependencies import probe


class LocalDependencyTests(unittest.TestCase):
    @patch("kidsstudio.m68_local_dependencies.shutil.which",
           side_effect=lambda name: "/usr/bin/" + name)
    def test_all_present_is_not_runtime_qualification(self, which):
        result = probe(require_ollama=True)
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["model_inference_executed"])
        self.assertFalse(result["pi_connection_tested"])
        self.assertFalse(result["youtube_upload_authorized"])
        self.assertEqual(which.call_count, 7)

    @patch("kidsstudio.m68_local_dependencies.shutil.which",
           side_effect=lambda name: None if name in ("ollama", "ffmpeg") else "/usr/bin/" + name)
    def test_required_missing_tools_block(self, _which):
        result = probe(require_ollama=True)
        self.assertEqual(result["status"], "LOCAL_DEPENDENCIES_MISSING")
        self.assertIn("ffmpeg", result["missing"])
        self.assertIn("ollama", result["missing"])

    @patch("kidsstudio.m68_local_dependencies.shutil.which",
           side_effect=lambda name: None if name == "ollama" else "/usr/bin/" + name)
    def test_optional_ollama_not_required_by_default(self, _which):
        self.assertEqual(probe()["missing"], [])
