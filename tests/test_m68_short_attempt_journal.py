"""Durable one-shot Short attempt journal tests."""
import tempfile
import unittest
from pathlib import Path

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
