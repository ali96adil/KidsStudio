"""M68 Pi private upload: no retries after ambiguous Google response."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_quota_reservation import ShortQuotaReservations
from kidsstudio.m68_short_attempt_journal import ShortAttemptJournal, ShortAttemptError
from kidsstudio.m68_short_pi_upload import upload_short_private
from kidsstudio.youtube_private_upload import file_sha256


class PiShortUploadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.media = root / "short.mp4"
        self.media.write_bytes(b"f" * 1200)
        self.sha = file_sha256(self.media)
        self.queue = StudioQueue(root / "queue.sqlite")
        self.queue.initialize()
        ShortQuotaReservations(self.queue).initialize()
        self.journal = ShortAttemptJournal(self.queue)
        self.journal.initialize()
        self.channel = "UC1234567890123456789012"
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,state TEXT,channel_id TEXT,
                allowed_made_for_kids INTEGER,allowed_synthetic_media INTEGER)""")
            db.execute("""INSERT INTO studio_youtube_private_policies
                VALUES('colors','ENABLED',?,1,1)""", (self.channel,))
            db.execute("""INSERT INTO studio_short_quota_reservations
                VALUES('colors-short-01','colors',?,0,'RESERVED_NO_UPLOAD')""",
                (self.sha,))
        self.kwargs = dict(short_id="colors-short-01", series_id="colors",
                           media_sha256=self.sha, media_path=self.media,
                           channel_id=self.channel, title="Learn colors",
                           description="Educational short", made_for_kids=True,
                           contains_synthetic_media=True, token="x" * 40)

    def test_verified_private_upload(self):
        transport = Mock()
        transport.start.return_value = "session"
        transport.put_chunk.return_value = (201, "AbCdEfGhI12")
        transport.verify.return_value = {
            "video_id": "AbCdEfGhI12", "channel_id": self.channel,
            "privacy_status": "private", "processing_status": "succeeded",
            "verified_using_authenticated_youtube_api": True,
        }
        result = upload_short_private(self.queue, **self.kwargs, transport=transport)
        self.assertEqual(result["status"], "PRIVATE_VERIFIED")
        self.assertEqual(result["video_id"], "AbCdEfGhI12")
        self.assertFalse(result["public_release_authorized"])
        self.assertEqual(transport.start.call_count, 1)

    def test_timeout_quarantines_and_blocks_retry(self):
        transport = Mock()
        transport.start.side_effect = TimeoutError("unknown remote result")
        with self.assertRaises(TimeoutError):
            upload_short_private(self.queue, **self.kwargs, transport=transport)
        self.assertEqual(self.journal.status(short_id="colors-short-01")["status"],
                         "MANUAL_RECONCILIATION")
        with self.assertRaises(ShortAttemptError):
            upload_short_private(self.queue, **self.kwargs, transport=transport)
        self.assertEqual(transport.start.call_count, 1)

    def test_modified_media_does_not_start_attempt(self):
        self.media.write_bytes(b"g" * 1200)
        with self.assertRaises(ShortAttemptError):
            upload_short_private(self.queue, **self.kwargs, transport=Mock())
        self.assertIsNone(self.journal.status(short_id="colors-short-01"))
