"""Durable one-shot Short attempt journal tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_quota_reservation import ShortQuotaReservations, ShortQuotaError
from kidsstudio.m68_short_attempt_journal import ShortAttemptJournal, ShortAttemptError


class ShortAttemptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.queue = StudioQueue(Path(temp.name) / "queue.sqlite")
        self.queue.initialize()
        self.quota = ShortQuotaReservations(self.queue)
        self.quota.initialize()
        self.journal = ShortAttemptJournal(self.queue)
        self.journal.initialize()
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_short_quota_reservations
                VALUES ('colors-short-01','colors',? ,0,'RESERVED_NO_UPLOAD')""",
                ("a" * 64,))
        self.args = dict(short_id="colors-short-01",
                         series_id="colors", media_sha256="a" * 64)

    def test_attempt_starts_uncertain_without_upload(self):
        report = self.journal.begin(**self.args)
        self.assertEqual(report["status"], "STARTED_UNCERTAIN")
        self.assertFalse(report["youtube_upload_authorized"])

    def test_attempt_cannot_be_restarted(self):
        self.journal.begin(**self.args)
        with self.assertRaises(ShortAttemptError):
            self.journal.begin(**self.args)

    def test_started_attempt_blocks_quota_release(self):
        self.journal.begin(**self.args)
        with self.assertRaises(ShortQuotaError):
            self.quota.release_unused(**self.args)

    def test_manual_reconciliation_keeps_attempt_locked(self):
        self.journal.begin(**self.args)
        report = self.journal.mark_manual(short_id="colors-short-01")
        self.assertEqual(report["status"], "MANUAL_RECONCILIATION")
        with self.assertRaises(ShortAttemptError):
            self.journal.begin(**self.args)

    def test_authenticated_private_verification(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,channel_id TEXT,state TEXT)""")
            db.execute("""INSERT INTO studio_youtube_private_policies
                VALUES('colors','UC1234567890123456789012','ENABLED')""")
        self.journal.begin(**self.args)
        transport = Mock()
        transport.verify.return_value = {
            "video_id": "AbCdEfGhI12",
            "channel_id": "UC1234567890123456789012",
            "privacy_status": "private",
            "processing_status": "succeeded",
            "verified_using_authenticated_youtube_api": True,
        }
        report = self.journal.verify_private(
            **self.args, video_id="AbCdEfGhI12",
            channel_id="UC1234567890123456789012",
            token="x" * 40, transport=transport)
        self.assertEqual(report["status"], "PRIVATE_VERIFIED")
        self.assertEqual(report["video_id"], "AbCdEfGhI12")
        self.assertFalse(report["public_release_authorized"])

    def test_wrong_privacy_never_verifies(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,channel_id TEXT,state TEXT)""")
            db.execute("""INSERT INTO studio_youtube_private_policies
                VALUES('colors','UC1234567890123456789012','ENABLED')""")
        self.journal.begin(**self.args)
        transport = Mock()
        transport.verify.return_value = {
            "video_id": "AbCdEfGhI12",
            "channel_id": "UC1234567890123456789012",
            "privacy_status": "public",
            "processing_status": "succeeded",
            "verified_using_authenticated_youtube_api": True,
        }
        with self.assertRaises(ShortAttemptError):
            self.journal.verify_private(
                **self.args, video_id="AbCdEfGhI12",
                channel_id="UC1234567890123456789012",
                token="x" * 40, transport=transport)
        self.assertEqual(self.journal.status(short_id="colors-short-01")["status"],
                         "STARTED_UNCERTAIN")
