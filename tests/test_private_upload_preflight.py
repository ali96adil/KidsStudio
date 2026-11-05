import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.private_upload_preflight import inspect_private_upload


class PrivateUploadPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = b"synthetic, not real video"
        (self.root / "episode.mp4").write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def inspect(self, **kwargs):
        args = dict(inbox_root=self.root, relative_path="episode.mp4",
                    expected_sha256=self.sha)
        args.update(kwargs)
        return inspect_private_upload(**args)

    def test_no_owner_review_holds_private(self):
        report = self.inspect()
        self.assertEqual(report["status"], "HOLD_PRIVATE")
        self.assertFalse(report["youtube_request_performed"])

    def test_owner_flag_is_not_upload_approval(self):
        report = self.inspect(owner_reviewed=True)
        self.assertEqual(report["status"], "READY_FOR_MANUAL_PRIVATE_UPLOAD")
        self.assertFalse(report["upload_approved"])
        self.assertFalse(report["publication_approved"])
        self.assertFalse(report["video_decoding_verified"])

    def test_wrong_sha_holds_private(self):
        report = self.inspect(expected_sha256="0" * 64, owner_reviewed=True)
        self.assertEqual(report["status"], "HOLD_PRIVATE")

    def test_public_visibility_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(visibility="public", owner_reviewed=True)

    def test_wrong_extension_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(relative_path="episode.mov")

    def test_empty_file_holds_private(self):
        (self.root / "episode.mp4").write_bytes(b"")
        report = self.inspect(expected_sha256=hashlib.sha256(b"").hexdigest(),
                              owner_reviewed=True)
        self.assertEqual(report["status"], "HOLD_PRIVATE")


if __name__ == "__main__":
    unittest.main()
