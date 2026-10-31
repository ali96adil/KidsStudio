"""M68 multi-short qualification fail-closed tests."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_short_qualification import qualify, ShortQualificationError


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "s.mp4"
        self.video.write_bytes(b"video")
        self.short = {"short_id": "e-short-01", "source_episode_id": "e",
                      "youtube_visibility": "PRIVATE_ONLY"}
        self.plan = {"episode_id": "e", "shorts": [self.short]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_video_blocks(self):
        with self.assertRaises(ShortQualificationError):
            qualify(self.root, self.plan, {})

    def test_duplicate_short_id_blocks(self):
        self.plan["shorts"].append(dict(self.short))
        with self.assertRaises(ShortQualificationError):
            qualify(self.root, self.plan, {"e-short-01": self.video})

    def test_qualified_video_still_pending_qa(self):
        seen = []
        def decoder(short, video):
            seen.append(video)
            return {"status": "SHORT_FULLY_DECODED_PENDING_CONTENT_QA"}
        result = qualify(self.root, self.plan, {"e-short-01": self.video},
                         decoder=decoder,
                         handoff_builder=lambda root, short, video, receipt: {
                             "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING"})
        self.assertEqual(seen, [self.video])
        self.assertEqual(result["shorts"][0]["content_qa"], "PENDING")
        self.assertFalse(result["pi_transfer_authorized"])
        self.assertFalse(result["public_release_authorized"])
