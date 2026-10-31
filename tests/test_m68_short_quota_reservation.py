"""Atomic M68 reservation tests against a real SQLite coordinator."""
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry
from kidsstudio.m68_short_review_store import ShortReviewStore
from kidsstudio.m68_short_content_review import CHECKS
from kidsstudio.m68_short_quota_reservation import ShortQuotaReservations, ShortQuotaError


class ReservationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.queue = StudioQueue(Path(tmp.name) / "queue.sqlite", clock=lambda: 1000000)
        self.queue.initialize()
        with self.queue._connection(write=True) as db:
            db.execute("CREATE TABLE studio_series(series_id TEXT PRIMARY KEY,state TEXT)")
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,state TEXT,max_uploads_24h INTEGER)""")
            db.execute("INSERT INTO studio_series VALUES('colors','ACTIVE')")
            db.execute("INSERT INTO studio_youtube_private_policies VALUES('colors','ENABLED',1)")
        self.registry = ShortRegistry(self.queue)
        self.registry.initialize()
        self.store = ShortReviewStore(self.queue)
        self.store.initialize()
        self.quota = ShortQuotaReservations(self.queue)
        self.quota.initialize()

    def add_short(self, name, digest):
        self.registry.register(short_id=name, source_episode_id="colors-ep-01",
                               media_sha256=digest)
        self.registry.mark_staged(short_id=name, media_sha256=digest,
                                  transfer_receipt={
                                      "status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
                                      "short_id": name,
                                      "source_episode_id": "colors-ep-01",
                                      "sha256": digest,
                                      "youtube_upload_authorized": False,
                                      "public_release_authorized": False})
        self.store.record({
            "status": "SHORT_CONTENT_QA_RECORDED",
            "decision": "PASS", "short_id": name,
            "source_episode_id": "colors-ep-01",
            "video_sha256": digest, "reviewer": "independent-reviewer",
            "checks": dict.fromkeys(CHECKS, True),
            "youtube_upload_authorized": False,
            "public_release_authorized": False})

    def reserve(self, name, digest):
        return self.quota.reserve(short_id=name, series_id="colors",
                                  media_sha256=digest)

    def test_reservation_is_idempotent_and_no_upload(self):
        self.add_short("colors-short-01", "a" * 64)
        first = self.reserve("colors-short-01", "a" * 64)
        self.assertEqual(first, self.reserve("colors-short-01", "a" * 64))
        self.assertFalse(first["youtube_upload_authorized"])

    def test_second_short_cannot_exceed_shared_quota(self):
        self.add_short("colors-short-01", "a" * 64)
        self.add_short("colors-short-02", "b" * 64)
        self.reserve("colors-short-01", "a" * 64)
        with self.assertRaises(ShortQuotaError):
            self.reserve("colors-short-02", "b" * 64)

    def test_original_upload_job_consumes_budget(self):
        self.add_short("colors-short-01", "a" * 64)
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO jobs(job_id,request_key,kind,payload,state,
                max_attempts,available_at,created_at,updated_at)
                VALUES (?,?,?,?,?,1,?,?,?)""",
                ("c"*32, "ordinary", "youtube_private_upload",
                 json.dumps({"series_id": "colors"}), "COMPLETED",
                 1000000, 1000000, 1000000))
        with self.assertRaises(ShortQuotaError):
            self.reserve("colors-short-01", "a" * 64)

    def test_unreviewed_short_rejected(self):
        self.registry.register(short_id="colors-short-01",
                               source_episode_id="colors-ep-01",
                               media_sha256="a" * 64)
        with self.assertRaises(ShortQuotaError):
            self.reserve("colors-short-01", "a" * 64)

    def test_unused_reservation_release_reopens_slot(self):
        self.add_short("colors-short-01", "a" * 64)
        self.add_short("colors-short-02", "b" * 64)
        self.reserve("colors-short-01", "a" * 64)
        released = self.quota.release_unused(short_id="colors-short-01",
                                             series_id="colors",
                                             media_sha256="a" * 64)
        self.assertFalse(released["youtube_upload_authorized"])
        self.assertEqual(self.reserve("colors-short-02", "b" * 64)["status"],
                         "SHORT_QUOTA_RESERVED_NO_UPLOAD")

    def test_release_rejects_wrong_media_and_missing_reservation(self):
        self.add_short("colors-short-01", "a" * 64)
        self.reserve("colors-short-01", "a" * 64)
        with self.assertRaises(ShortQuotaError):
            self.quota.release_unused(short_id="colors-short-01",
                                      series_id="colors", media_sha256="b" * 64)
        self.quota.release_unused(short_id="colors-short-01",
                                  series_id="colors", media_sha256="a" * 64)
        with self.assertRaises(ShortQuotaError):
            self.quota.release_unused(short_id="colors-short-01",
                                      series_id="colors", media_sha256="a" * 64)
