"""M66 offline acceptance uses real MP4 bytes and production SQLite journal."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m66_offline_acceptance import offline_acceptance
from kidsstudio.youtube_private_upload import UploadJournal


class OfflineAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.mp4 = root / "episode_qa_master.mp4"
        self.mp4.write_bytes(b"video-content" * 100)
        self.sha = hashlib.sha256(self.mp4.read_bytes()).hexdigest()
        self.journal_path = root / "upload.sqlite"
        self.job = "a" * 32

    def test_approved_media_without_reservation(self):
        result = offline_acceptance(self.mp4, self.sha)
        self.assertTrue(result["pass"])
        self.assertFalse(result["field_youtube_upload_verified"])
        self.assertFalse(result["upload_performed"])

    def test_reserved_matching_media(self):
        UploadJournal(self.journal_path).reserve(self.job, self.sha, "b" * 64)
        result = offline_acceptance(
            self.mp4, self.sha, journal=self.journal_path, job=self.job)
        self.assertTrue(result["pass"])
        self.assertEqual(result["reserved"]["journal_state"], "STARTED")

    def test_mismatched_master_blocked(self):
        result = offline_acceptance(self.mp4, "0" * 64)
        self.assertFalse(result["pass"])

    def test_reserved_different_sha_blocked(self):
        UploadJournal(self.journal_path).reserve(self.job, "c" * 64, "b" * 64)
        result = offline_acceptance(
            self.mp4, self.sha, journal=self.journal_path, job=self.job)
        self.assertFalse(result["pass"])

    def test_incomplete_journal_arguments_blocked(self):
        with self.assertRaises(ValueError):
            offline_acceptance(self.mp4, self.sha, journal=self.journal_path)


if __name__ == "__main__":
    unittest.main()
