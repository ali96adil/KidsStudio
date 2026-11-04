"""M66 transferred MP4 read-only SHA256 acceptance."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m66_master_check import verify_master, main


class MasterCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "master.mp4"
        self.path.write_bytes(b"safe-test-media" * 100)
        self.sha = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_exact_master_passes(self):
        result = verify_master(self.path, self.sha)
        self.assertTrue(result["pass"])
        self.assertFalse(result["upload_performed"])

    def test_changed_media_fails(self):
        self.path.write_bytes(b"modified-test-media" * 100)
        result = verify_master(self.path, self.sha)
        self.assertFalse(result["pass"])

    def test_missing_file_rejected(self):
        with self.assertRaises(OSError):
            verify_master(self.path.with_name("missing.mp4"), self.sha)

    def test_symlink_rejected(self):
        link = self.path.with_name("link.mp4")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            verify_master(link, self.sha)

    def test_invalid_digest_rejected(self):
        with self.assertRaises(ValueError):
            verify_master(self.path, "0" * 63)

    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            verify_master(Path("master.mp4"), self.sha)

    def test_cli_mismatch_exits_nonzero(self):
        self.assertEqual(main(["--mp4", str(self.path), "--expected-sha256", "0" * 64]), 2)


if __name__ == "__main__":
    unittest.main()
