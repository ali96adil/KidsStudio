"""M66 real SQLite reservation and Pi master integrity acceptance."""
import sqlite3
import tempfile
from pathlib import Path
import hashlib
from unittest.mock import patch
import unittest

from kidsstudio.m66_reserved_master_check import verify_reserved_master
from kidsstudio.youtube_private_upload import UploadJournal


class ReservedMasterCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.master = root / "episode_qa_master.mp4"
        self.master.write_bytes(b"pi-media" * 200)
        self.sha = hashlib.sha256(self.master.read_bytes()).hexdigest()
        self.journal_path = root / "journal.sqlite"
        self.journal = UploadJournal(self.journal_path)
        self.job = "a" * 32

    def test_reserved_media_matches(self):
        self.journal.reserve(self.job, self.sha, "b" * 64)
        report = verify_reserved_master(self.journal_path, self.job, self.master)
        self.assertTrue(report["pass"])
        self.assertFalse(report["upload_performed"])

    def test_corrupted_media_fails(self):
        self.journal.reserve(self.job, self.sha, "b" * 64)
        self.master.write_bytes(b"changed" * 200)
        self.assertFalse(verify_reserved_master(self.journal_path, self.job, self.master)["pass"])

    def test_unknown_job_fails_closed(self):
        with self.assertRaises(ValueError):
            verify_reserved_master(self.journal_path, self.job, self.master)

    def test_invalid_job_fails_closed(self):
        with self.assertRaises(ValueError):
            verify_reserved_master(self.journal_path, "invalid", self.master)

    def test_changed_reserved_sha_fails(self):
        self.journal.reserve(self.job, "c" * 64, "b" * 64)
        self.assertFalse(verify_reserved_master(self.journal_path, self.job, self.master)["pass"])

    def test_journal_change_while_hashing_rejected(self):
        self.journal.reserve(self.job, self.sha, "b" * 64)
        from kidsstudio.m66_master_check import verify_master as actual_verify

        def change_journal(mp4, expected):
            result = actual_verify(mp4, expected)
            self.journal.record_uploaded(self.job, "AbCdef12345")
            return result

        with patch("kidsstudio.m66_reserved_master_check.verify_master",
                   side_effect=change_journal):
            with self.assertRaises(ValueError):
                verify_reserved_master(self.journal_path, self.job, self.master)

    def test_report_does_not_modify_journal(self):
        self.journal.reserve(self.job, self.sha, "b" * 64)
        before = self.journal.status(self.job)
        verify_reserved_master(self.journal_path, self.job, self.master)
        self.assertEqual(before, self.journal.status(self.job))


if __name__ == "__main__":
    unittest.main()
