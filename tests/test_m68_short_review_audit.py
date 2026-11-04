"""Tests for M68 Pi short QA eligibility audit."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_registry import ShortRegistry
from kidsstudio.m68_short_review_store import ShortReviewStore
from kidsstudio.m68_short_review_audit import assess_short_review
from kidsstudio.m68_short_content_review import CHECKS


class ShortReviewAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.queue = StudioQueue(Path(temp.name) / "queue.sqlite")
        self.queue.initialize()
        self.registry = ShortRegistry(self.queue)
        self.registry.initialize()
        self.store = ShortReviewStore(self.queue)
        self.store.initialize()
        self.registry.register(short_id="colors-short-01",
                               source_episode_id="colors",
                               media_sha256="a" * 64)
        self.args = dict(short_id="colors-short-01",
                         source_episode_id="colors", media_sha256="a" * 64)

    def assess(self):
        return assess_short_review(self.queue, **self.args)

    def stage(self):
        self.registry.mark_staged(short_id="colors-short-01",
                                  media_sha256="a" * 64,
                                  transfer_receipt={
                                      "status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
                                      "short_id": "colors-short-01",
                                      "source_episode_id": "colors",
                                      "sha256": "a" * 64,
                                      "youtube_upload_authorized": False,
                                      "public_release_authorized": False})

    def review(self):
        return self.store.record({
            "status": "SHORT_CONTENT_QA_RECORDED",
            "decision": "PASS",
            "short_id": "colors-short-01",
            "source_episode_id": "colors",
            "video_sha256": "a" * 64,
            "reviewer": "content-reviewer",
            "checks": dict.fromkeys(CHECKS, True),
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        })

    def test_missing_review_blocks(self):
        self.assertIn("CONTENT_REVIEW_MISSING", self.assess()["reasons"])

    def test_staged_without_review_blocks(self):
        self.stage()
        self.assertEqual(self.assess()["status"], "SHORT_REVIEW_BLOCKED")

    def test_valid_review_only_reaches_policy_stage(self):
        self.stage()
        self.review()
        result = self.assess()
        self.assertEqual(result["status"], "SHORT_REVIEW_READY_FOR_M65_POLICY")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_wrong_hash_blocks(self):
        self.stage()
        self.review()
        self.args["media_sha256"] = "b" * 64
        self.assertEqual(self.assess()["status"], "SHORT_REVIEW_BLOCKED")
