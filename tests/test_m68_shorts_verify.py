"""M68 FFprobe media verification tests."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m68_shorts_verify import verify_short, ShortVerifyError


SHORT = {"short_id": "colors-ar-001-short-01", "source_episode_id": "colors-ar-001",
         "start_seconds": 10, "end_seconds": 22}


class ShortVerifyTests(unittest.TestCase):
    def test_wrong_resolution_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"test")
            fake = subprocess.CompletedProcess([], 0, stdout=(
                '{"format":{"duration":"12"},"streams":['
                '{"codec_type":"video","width":1920,"height":1080},'
                '{"codec_type":"audio"}]}'))
            with patch("kidsstudio.m68_shorts_verify.shutil.which", return_value="/usr/bin/ffprobe"):
                with self.assertRaises(ShortVerifyError):
                    verify_short(SHORT, video, runner=lambda *args, **kwargs: fake)

    def test_valid_streams_report_hash_but_not_upload_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"test")
            fake = subprocess.CompletedProcess([], 0, stdout=(
                '{"format":{"duration":"12"},"streams":['
                '{"codec_type":"video","width":1080,"height":1920},'
                '{"codec_type":"audio"}]}'))
            with patch("kidsstudio.m68_shorts_verify.shutil.which", return_value="/usr/bin/ffprobe"):
                result = verify_short(SHORT, video, runner=lambda *args, **kwargs: fake)
            self.assertEqual(result["status"], "SHORT_MEDIA_TECHNICALLY_VERIFIED_PENDING_CONTENT_QA")
            self.assertFalse(result["youtube_upload_authorized"])
