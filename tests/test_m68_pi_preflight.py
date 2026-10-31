"""M68 read-only preflight regression tests."""
from test_m68_short_pi_upload import PiShortUploadTests
from kidsstudio.m68_pi_preflight import assess


class PiPreflightTests(PiShortUploadTests):
    def test_preflight_ready_without_network(self):
        result = assess(self.queue, short_id="colors-short-01",
                        series_id="colors", media_path=self.media)
        self.assertEqual(result["status"], "READY_FOR_EXPLICIT_PRIVATE_UPLOAD")
        self.assertFalse(result["youtube_upload_authorized"])
        self.assertFalse(result["public_release_authorized"])

    def test_preflight_detects_revoked_source(self):
        with self.queue._connection(write=True) as db:
            db.execute("UPDATE studio_episodes SET state='PLANNED'")
        result = assess(self.queue, short_id="colors-short-01",
                        series_id="colors", media_path=self.media)
        self.assertIn("SOURCE_MASTER_NOT_APPROVED", result["reasons"])

    def test_preflight_detects_existing_attempt(self):
        self.journal.begin(short_id="colors-short-01", series_id="colors",
                           media_sha256=self.sha)
        result = assess(self.queue, short_id="colors-short-01",
                        series_id="colors", media_path=self.media)
        self.assertIn("UPLOAD_ATTEMPT_ALREADY_EXISTS", result["reasons"])

    def test_preflight_detects_changed_media(self):
        self.media.write_bytes(b"z" * 1200)
        result = assess(self.queue, short_id="colors-short-01",
                        series_id="colors", media_path=self.media)
        self.assertIn("STAGED_MEDIA_SHA_MISMATCH", result["reasons"])

    def test_preflight_rejects_malformed_channel_id(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_youtube_private_policies
                SET channel_id='UCbad' WHERE series_id='colors'""")
        result = assess(self.queue, short_id="colors-short-01",
                        series_id="colors", media_path=self.media)
        self.assertIn("OWNER_CHANNEL_INVALID", result["reasons"])

    def test_preflight_rejects_expired_reservation(self):
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_short_quota_reservations
                SET created_at=? WHERE short_id='colors-short-01'""",
                (self.queue.clock() - 86401,))
        result = assess(self.queue, short_id="colors-short-01",
                        series_id="colors", media_path=self.media)
        self.assertIn("QUOTA_RESERVATION_EXPIRED", result["reasons"])
