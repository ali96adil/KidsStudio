"""Tests for independent immutable Pi short review evidence."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry
from kidsstudio.m68_short_review_store import ShortReviewStore, ShortReviewStoreError
from kidsstudio.m68_short_content_review import CHECKS


class ShortReviewStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        queue = StudioQueue(Path(tmp.name) / "queue.sqlite")
        queue.initialize()
        registry = ShortRegistry(queue)
        registry.initialize()
        registry.register(short_id="colors-short-01",
                          source_episode_id="colors",
                          media_sha256="a" * 64)
        registry.mark_staged(short_id="colors-short-01",
                             media_sha256="a" * 64,
                             transfer_receipt={
                                 "status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
                                 "short_id": "colors-short-01",
                                 "source_episode_id": "colors",
                                 "sha256": "a" * 64,
                                 "youtube_upload_authorized": False,
                                 "public_release_authorized": False})
        self.store = ShortReviewStore(queue)
        self.store.initialize()
        self.receipt = {
            "status": "SHORT_CONTENT_QA_RECORDED",
            "decision": "PASS",
            "short_id": "colors-short-01",
            "source_episode_id": "colors",
            "video_sha256": "a" * 64,
            "reviewer": "content-reviewer",
            "checks": dict.fromkeys(CHECKS, True),
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }

    def test_pass_persisted_but_not_upload_approved(self):
        result = self.store.record(self.receipt)
        self.assertEqual(result["decision"], "PASS")
        self.assertFalse(result["youtube_upload_authorized"])
        self.assertEqual(result, self.store.record(self.receipt))

    def test_reject_changed_video(self):
        self.receipt["video_sha256"] = "b" * 64
        with self.assertRaises(ShortReviewStoreError):
            self.store.record(self.receipt)

    def test_cannot_overwrite_existing_review(self):
        self.store.record(self.receipt)
        self.receipt["reviewer"] = "another-reviewer"
        with self.assertRaises(ShortReviewStoreError):
            self.store.record(self.receipt)

    def test_pass_cannot_hide_failed_axis(self):
        self.receipt["checks"]["visual"] = False
        with self.assertRaises(ShortReviewStoreError):
            self.store.record(self.receipt)

    def test_ai_receipt_requires_complete_hash_bound_evidence(self):
        self.receipt["ai_review_completed"] = True
        self.receipt["ai_evidence_video_sha256"] = "a" * 64
        self.receipt["ai_evidence"] = dict.fromkeys(
            CHECKS, "Verified in the reviewed media.")
        result = self.store.record(self.receipt)
        self.assertEqual(result["decision"], "PASS")

    def test_ai_receipt_with_wrong_evidence_hash_is_rejected(self):
        self.receipt["ai_review_completed"] = True
        self.receipt["ai_evidence_video_sha256"] = "b" * 64
        self.receipt["ai_evidence"] = dict.fromkeys(
            CHECKS, "Verified in the reviewed media.")
        with self.assertRaises(ShortReviewStoreError):
            self.store.record(self.receipt)
