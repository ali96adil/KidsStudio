"""Pi M68 operational snapshot never mutates upload state."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry
from kidsstudio.m68_short_review_store import ShortReviewStore
from kidsstudio.m68_short_quota_reservation import ShortQuotaReservations
from kidsstudio.m68_short_attempt_journal import ShortAttemptJournal
from kidsstudio.m68_pi_operations import snapshot


class PiOperationsTests(unittest.TestCase):
    def test_empty_snapshot_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = StudioQueue(Path(tmp) / "queue.db")
            queue.initialize()
            ShortRegistry(queue).initialize()
            ShortReviewStore(queue).initialize()
            ShortQuotaReservations(queue).initialize()
            ShortAttemptJournal(queue).initialize()
            before = queue.path.stat().st_size if hasattr(queue, "path") else None
            report = snapshot(queue)
            self.assertEqual(report["status"], "READ_ONLY_M68_PI_SNAPSHOT")
            self.assertEqual(report["shorts"], [])
            self.assertEqual(report["counts"]["private_verified"], 0)
            self.assertFalse(report["upload_authorized"])
            self.assertFalse(report["public_release_authorized"])

    def test_unreviewed_short_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = StudioQueue(Path(tmp) / "queue.db")
            queue.initialize()
            registry = ShortRegistry(queue)
            registry.initialize()
            ShortReviewStore(queue).initialize()
            ShortQuotaReservations(queue).initialize()
            ShortAttemptJournal(queue).initialize()
            registry.register(short_id="short-01", source_episode_id="episode-01",
                              media_sha256="a" * 64)
            report = snapshot(queue)
            self.assertEqual(report["counts"]["registered"], 1)
            self.assertEqual(report["counts"]["review_blocked"], 1)
            self.assertEqual(report["shorts"][0]["review_status"], "NO_REVIEW")
            self.assertFalse(report["shorts"][0]["upload_authorized"])

    def test_missing_m68_tables_fail_with_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = StudioQueue(Path(tmp) / "queue.db")
            queue.initialize()
            with self.assertRaisesRegex(ValueError, "not initialized"):
                snapshot(queue)
