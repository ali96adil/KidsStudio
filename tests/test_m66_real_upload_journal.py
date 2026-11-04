"""M66 regression tests for M25/M65's REAL SQLite UploadJournal.

No Google credentials, no network, no actual upload. A fresh SQLite file is
used in each test. This is the journal used by the Pi uploader, unlike the
separate M66 JSON reference model.
"""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.youtube_private_upload import UploadJournal, YouTubePrivateError


class RealUploadJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "journal.sqlite"
        self.journal = UploadJournal(self.path)
        self.job = "a" * 32
        self.sha = "b" * 64
        self.plan = "c" * 64
        self.video = "AbCdef12345"

    def test_started_survives_process_restart(self):
        self.journal.reserve(self.job, self.sha, self.plan)
        reopened = UploadJournal(self.path)
        self.assertEqual(reopened.status(self.job)["state"], "STARTED")
        with self.assertRaises(YouTubePrivateError):
            reopened.reserve(self.job, self.sha, self.plan)

    def test_same_master_different_job_blocked(self):
        self.journal.reserve(self.job, self.sha, self.plan)
        with self.assertRaises(YouTubePrivateError):
            self.journal.reserve("d" * 32, self.sha, self.plan)

    def test_verified_cannot_be_reserved_again(self):
        self.journal.reserve(self.job, self.sha, self.plan)
        self.journal.record_uploaded(self.job, self.video)
        self.journal.record_verified(self.job, self.video)
        reopened = UploadJournal(self.path)
        self.assertEqual(reopened.status(self.job)["state"], "PRIVATE_VERIFIED")
        with self.assertRaises(YouTubePrivateError):
            reopened.reserve(self.job, self.sha, self.plan)

    def test_verified_requires_matching_video(self):
        self.journal.reserve(self.job, self.sha, self.plan)
        self.journal.record_uploaded(self.job, self.video)
        with self.assertRaises(YouTubePrivateError):
            self.journal.record_verified(self.job, "Z" * 11)
        self.assertEqual(self.journal.status(self.job)["state"], "UPLOADED_UNVERIFIED")

    def test_cannot_verify_started_without_uploaded_receipt(self):
        self.journal.reserve(self.job, self.sha, self.plan)
        with self.assertRaises(YouTubePrivateError):
            self.journal.record_verified(self.job, self.video)
        self.assertEqual(self.journal.status(self.job)["state"], "STARTED")

    def test_invalid_video_id_rejected(self):
        self.journal.reserve(self.job, self.sha, self.plan)
        with self.assertRaises(YouTubePrivateError):
            self.journal.record_uploaded(self.job, "bad")
        self.assertEqual(self.journal.status(self.job)["state"], "STARTED")


if __name__ == "__main__":
    unittest.main()
