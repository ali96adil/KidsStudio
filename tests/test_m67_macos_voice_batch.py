"""M67 macOS voice worker tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_macos_voice_batch import render_voices, VoiceBatchError
from kidsstudio.m67_media_jobs import make_jobs

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class VoiceBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = make_jobs(json.loads(SOURCE.read_text(encoding="utf-8")))

    def test_six_tracks_no_approval(self):
        calls = []
        def fake_run(args, **kwargs):
            calls.append(args)
            if "-o" in args:
                Path(args[args.index("-o") + 1]).write_bytes(b"aiff")
            else:
                Path(args[-1]).write_bytes(b"wav")
        with tempfile.TemporaryDirectory() as temp:
            with patch("kidsstudio.m67_macos_voice_batch.shutil.which",
                       return_value="/usr/bin/mock"):
                result = render_voices(self.packet, Path(temp), voice="Laila",
                                       runner=fake_run)
            self.assertEqual(len(result["voices"]), 6)
            self.assertEqual(len(calls), 12)
            self.assertEqual(result["voice_qa"], "PENDING")
            self.assertFalse(result["youtube_upload_authorized"])

    def test_requires_explicit_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(VoiceBatchError):
                render_voices(self.packet, Path(temp), voice="")


if __name__ == "__main__":
    unittest.main()
