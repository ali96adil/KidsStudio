"""M67 full decode qualification tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_decode_qualification import decode_check
from kidsstudio.m67_media_jobs import make_jobs

SOURCE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class DecodeQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = make_jobs(json.loads(SOURCE.read_text(encoding="utf-8")))

    def test_missing_media_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("kidsstudio.m67_decode_qualification.shutil.which",
                       return_value="/usr/bin/mock"):
                report = decode_check(self.packet, temp)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["youtube_upload_authorized"])

    def test_decoded_media_remains_unapproved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for job in self.packet["jobs"]:
                for kind in ("visual", "voice"):
                    file = root / job[kind]["output"]
                    file.parent.mkdir(exist_ok=True)
                    file.write_bytes(b"mock media")
            class Completed:
                def __init__(self, stdout=""):
                    self.stdout = stdout
            def fake_run(args, **kwargs):
                if "-show_streams" in args:
                    is_png = str(args[-1]).endswith(".png")
                    if is_png:
                        stream = {"codec_type": "video", "width": 1280,
                                  "height": 720}
                    else:
                        stream = {"codec_type": "audio", "sample_rate": "48000",
                                  "channels": 1, "codec_name": "pcm_s16le"}
                    return Completed(json.dumps({"streams": [stream]}))
                return Completed()
            with patch("kidsstudio.m67_decode_qualification.shutil.which",
                       return_value="/usr/bin/mock"):
                report = decode_check(self.packet, root, runner=fake_run)
            self.assertEqual(report["status"], "MEDIA_DECODED_PENDING_QA")
            self.assertEqual(report["voice_qa"], "PENDING")
            self.assertEqual(report["visual_qa"], "PENDING")


if __name__ == "__main__":
    unittest.main()
