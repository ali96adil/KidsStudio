import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.private_upload_gate import check_private_upload_candidate


class PrivateUploadGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.data = b"synthetic private video"
        (self.root / "episode.mp4").write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def check(self, **kwargs):
        args = dict(private_root=self.root, relative_path="episode.mp4",
                    expected_sha256=self.sha)
        args.update(kwargs)
        return check_private_upload_candidate(**args)

    def test_default_blocks_without_owner_permission(self):
        result = self.check()
        self.assertEqual(result["status"], "PRIVATE_UPLOAD_BLOCKED")
        self.assertTrue(result["integrity_verified"])
        self.assertFalse(result["upload_submitted"])

    def test_explicit_private_permission_is_not_submission(self):
        result = self.check(owner_private_upload_authorized=True)
        self.assertEqual(result["status"], "PRIVATE_UPLOAD_ELIGIBLE_NOT_SUBMITTED")
        self.assertEqual(result["required_youtube_visibility"], "private")
        self.assertFalse(result["upload_submitted"])
        self.assertFalse(result["public_release_approved"])

    def test_mismatch_blocks_even_with_permission(self):
        result = self.check(owner_private_upload_authorized=True,
                            expected_sha256="0" * 64)
        self.assertEqual(result["status"], "PRIVATE_UPLOAD_BLOCKED")

    def test_nonprivate_directory_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.check(owner_private_upload_authorized=True)

    def test_nonboolean_permission_rejected(self):
        with self.assertRaises(ValueError):
            self.check(owner_private_upload_authorized="true")


if __name__ == "__main__":
    unittest.main()
