"""M67 local production preflight checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_local_preflight import preflight
from kidsstudio.m67_production_handoff import build_manifest

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class M67LocalPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_missing_assets_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("kidsstudio.m67_local_preflight.shutil.which",
                       return_value="/usr/bin/tool"):
                result = preflight(self.storyboard, build_manifest(self.storyboard),
                                   Path(tmp))
            self.assertEqual(result["status"], "BLOCKED")
            self.assertFalse(result["youtube_upload_authorized"])

    def test_missing_tools_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("kidsstudio.m67_local_preflight.shutil.which",
                       return_value=None):
                result = preflight(self.storyboard, build_manifest(self.storyboard),
                                   Path(tmp))
            self.assertEqual(result["checks"]["godot"], "MISSING")
            self.assertEqual(result["checks"]["ffmpeg"], "MISSING")
            self.assertEqual(result["checks"]["ffprobe"], "MISSING")


if __name__ == "__main__":
    unittest.main()
