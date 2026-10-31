"""Portrait compositor security and fail-closed tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m68_portrait_compositor import render_portrait, ShortRenderError


class PortraitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "portrait.mp4"
        self.manifest = {"episode_id": "e", "assets": [{
            "start": 0, "end": 10, "art": "art.png", "voice": "voice.wav"}]}
        self.short = {"short_id": "e-short-01", "source_episode_id": "e",
                      "source_beats": [1], "source_asset_keys": ["art.png", "voice.wav"],
                      "start_seconds": 0, "end_seconds": 10,
                      "youtube_visibility": "PRIVATE_ONLY",
                      "public_release_authorized": False}

    def tearDown(self):
        self.temp.cleanup()

    def test_no_qa_blocks_render(self):
        with patch("kidsstudio.m68_portrait_compositor.audit_assets",
                   return_value={"render_authorized": False}):
            with self.assertRaises(ShortRenderError):
                render_portrait(self.short, self.manifest, self.root, self.output)

    def test_private_approved_source_uses_uncropped_foreground(self):
        (self.root / "art.png").write_bytes(b"art")
        (self.root / "voice.wav").write_bytes(b"voice")
        commands = []
        def fake_runner(command, **kwargs):
            commands.append(command)
            self.output.write_bytes(b"fake-mp4")
        with patch("kidsstudio.m68_portrait_compositor.audit_assets",
                   return_value={"render_authorized": True}), patch(
                   "kidsstudio.m68_portrait_compositor.shutil.which",
                   return_value="/usr/bin/ffmpeg"):
            result = render_portrait(self.short, self.manifest, self.root,
                                     self.output, runner=fake_runner)
        self.assertIn("scale=1000:1450:force_original_aspect_ratio=decrease",
                      " ".join(commands[0]))
        self.assertFalse(result["youtube_upload_authorized"])
