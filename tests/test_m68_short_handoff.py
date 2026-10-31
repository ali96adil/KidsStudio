"""M68 individual short handoff cannot bypass decode or hash checks."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_short_handoff import build_short_handoff, ShortHandoffError


SHORT = {"short_id": "colors-ar-001-short-01", "source_episode_id": "colors-ar-001",
         "youtube_visibility": "PRIVATE_ONLY"}


class ShortHandoffTests(unittest.TestCase):
    def test_unverified_decode_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"test")
            with self.assertRaises(ShortHandoffError):
                build_short_handoff(tmp, SHORT, video,
                                    {"status": "SHORT_MEDIA_TECHNICALLY_VERIFIED_PENDING_CONTENT_QA"})

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"test")
            receipt = {"status": "SHORT_FULLY_DECODED_PENDING_CONTENT_QA",
                       "short_id": SHORT["short_id"],
                       "source_episode_id": SHORT["source_episode_id"],
                       "full_decode": "PASS", "video_sha256": "0" * 64, "bytes": 4}
            with self.assertRaises(ShortHandoffError):
                build_short_handoff(tmp, SHORT, video, receipt)
