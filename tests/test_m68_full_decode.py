"""M68 full decode rejects broken video streams and preserves private-only policy."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from kidsstudio.m68_full_decode import verify_decoded, ShortVerifyError


class FullDecodeTests(unittest.TestCase):
    def test_decoder_failure_blocks(self):
        short = {"short_id": "s-01", "source_episode_id": "episode-01"}
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"fake")
            with patch("kidsstudio.m68_full_decode.verify_short",
                       return_value={"status": "SHORT_MEDIA_TECHNICALLY_VERIFIED_PENDING_CONTENT_QA"}), patch(
                       "kidsstudio.m68_full_decode.shutil.which", return_value="/usr/bin/ffmpeg"):
                def fail(*args, **kwargs):
                    raise subprocess.CalledProcessError(1, "ffmpeg")
                with self.assertRaises(ShortVerifyError):
                    verify_decoded(short, video, runner=fail)

    def test_success_still_requires_content_qa(self):
        short = {"short_id": "s-01", "source_episode_id": "episode-01"}
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"fake")
            with patch("kidsstudio.m68_full_decode.verify_short",
                       return_value={"status": "SHORT_MEDIA_TECHNICALLY_VERIFIED_PENDING_CONTENT_QA"}), patch(
                       "kidsstudio.m68_full_decode.shutil.which", return_value="/usr/bin/ffmpeg"):
                result = verify_decoded(short, video, runner=lambda *args, **kwargs: None)
            self.assertEqual(result["full_decode"], "PASS")
            self.assertFalse(result["youtube_upload_authorized"])
            self.assertFalse(result["public_release_authorized"])
