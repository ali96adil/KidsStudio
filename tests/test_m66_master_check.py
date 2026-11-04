"""M66 transferred MP4 read-only SHA256 acceptance."""
import hashlib
import os
from unittest.mock import patch
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

    def test_same_length_corruption_detected(self):
        original = self.path.read_bytes()
        self.path.write_bytes(b"X" + original[1:])
        self.assertEqual(self.path.stat().st_size, len(original))
        self.assertFalse(verify_master(self.path, self.sha)["pass"])

    def test_nofollow_flag_used_to_open_media(self):
        actual_open = os.open
        flags_seen = []

        def checked_open(path, flags, *args, **kwargs):
            flags_seen.append(flags)
            return actual_open(path, flags, *args, **kwargs)

        with patch("kidsstudio.m66_master_check.os.open", side_effect=checked_open):
            self.assertTrue(verify_master(self.path, self.sha)["pass"])
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(flags_seen[0] & os.O_NOFOLLOW)

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
