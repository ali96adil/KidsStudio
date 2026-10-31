"""M68 read-only review report tests."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry
from kidsstudio.m68_short_review_store import ShortReviewStore
from kidsstudio.m68_short_content_review import CHECKS
from kidsstudio.m68_short_review_report import inspect


class ReviewReportTests(unittest.TestCase):
    def test_missing_review_never_authorizes_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = StudioQueue(Path(tmp) / "queue.db")
            queue.initialize()
            ShortRegistry(queue).initialize()
            ShortReviewStore(queue).initialize()
            report = inspect(queue, "missing")
            self.assertEqual(report["status"], "NO_REVIEW")
            self.assertFalse(report["upload_authorized"])

    def test_review_report_exposes_evidence_without_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = StudioQueue(Path(tmp) / "queue.db")
            queue.initialize()
            registry = ShortRegistry(queue)
            registry.initialize()
            registry.register(short_id="s1", source_episode_id="e1",
                              media_sha256="a" * 64)
            registry.mark_staged(short_id="s1", media_sha256="a" * 64,
                                 transfer_receipt={
                                     "status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
                                     "short_id": "s1", "source_episode_id": "e1",
                                     "sha256": "a" * 64,
                                     "youtube_upload_authorized": False,
                                     "public_release_authorized": False})
            store = ShortReviewStore(queue)
            store.initialize()
            store.record({
                "status": "SHORT_CONTENT_QA_RECORDED",
                "decision": "PASS", "short_id": "s1",
                "source_episode_id": "e1", "video_sha256": "a" * 64,
                "reviewer": "kidsstudio-ai-test",
                "checks": dict.fromkeys(CHECKS, True),
                "ai_review_completed": True,
                "ai_evidence_video_sha256": "a" * 64,
                "ai_evidence": dict.fromkeys(CHECKS, "Video and script verified."),
                "youtube_upload_authorized": False,
                "public_release_authorized": False})
            report = inspect(queue, "s1")
            self.assertEqual(report["status"], "REVIEW_EVIDENCE_CONSISTENT")
            self.assertEqual(set(report["ai_evidence"]), set(CHECKS))
            self.assertFalse(report["upload_authorized"])
            self.assertFalse(report["public_release_authorized"])
