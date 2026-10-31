"""Durable one-shot Short attempt journal tests."""
import tempfile
import unittest
from pathlib import Path
import json
from kidsstudio.m68_short_content_review import CHECKS
from unittest.mock import Mock, patch

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
                VALUES ('colors-short-01','colors',? ,?,'RESERVED_NO_UPLOAD')""",
                ("a" * 64, self.queue.clock()))
        with self.queue._connection(write=True) as db:
            db.execute("CREATE TABLE studio_series(series_id TEXT PRIMARY KEY,state TEXT)")
            db.execute("INSERT INTO studio_series VALUES('colors','ACTIVE')")
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,channel_id TEXT,state TEXT)""")
            db.execute("""INSERT INTO studio_youtube_private_policies
                VALUES('colors','UC1234567890123456789012','ENABLED')""")
            db.execute("""CREATE TABLE studio_derived_shorts(
                short_id TEXT PRIMARY KEY,source_episode_id TEXT,
                media_sha256 TEXT,state TEXT)""")
            db.execute("""INSERT INTO studio_derived_shorts VALUES(
                'colors-short-01','colors-ep-01',?,'PI_STAGED_NOT_APPROVED')""",
                ("a" * 64,))
            db.execute("""CREATE TABLE studio_short_reviews(
                short_id TEXT PRIMARY KEY,source_episode_id TEXT,
                media_sha256 TEXT,decision TEXT,checks_json TEXT)""")
            db.execute("""INSERT INTO studio_short_reviews VALUES(
                'colors-short-01','colors-ep-01',?,'PASS',?)""",
                ("a" * 64, json.dumps(dict.fromkeys(CHECKS, True))))
        from kidsstudio.m68_short_source_binding import initialize as init_source, bind
        init_source(self.queue)
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE studio_episodes(
                series_id TEXT,ordinal INTEGER,state TEXT,render_job_id TEXT,
                PRIMARY KEY(series_id,ordinal))""")
            db.execute("""INSERT INTO studio_episodes
                VALUES('colors',1,'EPISODE_APPROVED',?)""", ("a" * 32,))
            db.execute("""INSERT INTO jobs(job_id,request_key,kind,payload,state,
                max_attempts,available_at,created_at,updated_at)
                VALUES (?,?,?,?,?,1,?,?,?)""",
                ("a" * 32, "source-render", "episode_assemble", "{}", "COMPLETED",
                 0, 0, 0))
        # Unit fixture isolates source receipt; real M26 receipt is tested separately.
        approval = patch("kidsstudio.private_upload_policy.PrivateUploadPolicy._approved")
        approval.start()
        self.addCleanup(approval.stop)
        bind(self.queue, short_id="colors-short-01", series_id="colors",
             source_episode_id="colors-ep-01", source_ordinal=1,
             source_render_job_id="a" * 32, source_master_sha256="c" * 64)
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
        self.journal.begin(**self.args)
        self.journal.record_upload_result(**self.args, video_id="AbCdEfGhI12")
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

    def test_unpinned_video_cannot_be_verified(self):
        self.journal.begin(**self.args)
        transport = Mock()
        with self.assertRaises(ShortAttemptError):
            self.journal.verify_private(
                **self.args, video_id="AbCdEfGhI12",
                channel_id="UC1234567890123456789012",
                token="x" * 40, transport=transport)
        transport.verify.assert_not_called()

    def test_upload_response_video_id_is_immutable(self):
        self.journal.begin(**self.args)
        self.journal.record_upload_result(**self.args, video_id="AbCdEfGhI12")
        with self.assertRaises(ShortAttemptError):
            self.journal.record_upload_result(**self.args, video_id="AbCdEfGhI13")

    def test_revoked_review_blocks_attempt_before_network(self):
        with self.queue._connection(write=True) as db:
            db.execute("UPDATE studio_short_reviews SET decision='REJECT'")
        with self.assertRaises(ShortAttemptError):
            self.journal.begin(**self.args)
        self.assertIsNone(self.journal.status(short_id="colors-short-01"))

    def test_revoked_source_approval_blocks_upload_attempt(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET state='PLANNED'
                WHERE series_id='colors' AND ordinal=1""")
        with self.assertRaises(ShortAttemptError):
            self.journal.begin(**self.args)
        self.assertIsNone(self.journal.status(short_id="colors-short-01"))

    def test_changed_source_render_job_blocks_upload_attempt(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_episodes SET render_job_id=?
                WHERE series_id='colors' AND ordinal=1""", ("b" * 32,))
        with self.assertRaises(ShortAttemptError):
            self.journal.begin(**self.args)

    def test_expired_reservation_cannot_start_upload(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_short_quota_reservations
                SET created_at=? WHERE short_id='colors-short-01'""",
                (self.queue.clock() - 86401,))
        with self.assertRaises(ShortAttemptError):
            self.journal.begin(**self.args)
        self.assertIsNone(self.journal.status(short_id="colors-short-01"))
