import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_media_inbox import build_manifest
from kidsstudio.pi_received_media_precheck import verify_received


class PiReceivedMediaPrecheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "original.mp4"
        self.video.write_bytes(b"test render data")
        self.manifest = build_manifest(self.video, "colors_001")
        self.prefix = "colors_001-" + self.manifest["sha256"][:16]
        self.received = self.root / (self.prefix + ".mp4")
        self.video.rename(self.received)
        self.manifest["filename"] = self.received.name
        self.metadata = self.root / (self.prefix + ".json")
        self.metadata.write_text(json.dumps(self.manifest))

    def test_verified_received_media(self):
        result = verify_received(self.root, self.metadata.name)
        self.assertEqual(result["status"], "PI_MEDIA_VERIFIED_NOT_QUEUED")
        self.assertFalse(result["youtube_uploaded"])

    def test_modified_video_rejected(self):
        self.received.write_bytes(b"tampered bytes!")
        with self.assertRaises(ValueError):
            verify_received(self.root, self.metadata.name)

    def test_symlink_video_rejected(self):
        original = self.root / "real.mp4"
        self.received.rename(original)
        self.received.symlink_to(original)
        with self.assertRaises(ValueError):
            verify_received(self.root, self.metadata.name)

    def test_manifest_extra_fields_rejected(self):
        self.manifest["session_url"] = "must not be here"
        self.metadata.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):
            verify_received(self.root, self.metadata.name)

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            verify_received(self.root, "../outside.json")


if __name__ == "__main__":
    unittest.main()
