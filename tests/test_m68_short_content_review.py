"""Tests for M68 explicit content review decisions."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_short_content_review import CHECKS, review


class ShortContentReviewTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING",
            "short_id": "colors-short-01",
            "episode_id": "colors-short-01",
            "source_episode_id": "colors",
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
        self.checks = dict.fromkeys(CHECKS, True)

    @patch("kidsstudio.m68_short_content_review.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_all_checks_pass(self, verify):
        result = review("/media", self.handoff, self.checks, "visual-reviewer")
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["video_sha256"], "a" * 64)
        self.assertFalse(result["youtube_upload_authorized"])
        verify.assert_called_once()

    @patch("kidsstudio.m68_short_content_review.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_failed_check_rejects(self, _verify):
        checks = dict(self.checks, pedagogy=False)
        result = review("/media", self.handoff, checks, "pedagogy-reviewer")
        self.assertEqual(result["decision"], "REJECT")

    def test_missing_check_rejected(self):
        checks = dict(self.checks)
        del checks["copyright"]
        with self.assertRaises(ValueError):
            review("/media", self.handoff, checks, "reviewer")

    def test_unsafe_handoff_rejected(self):
        handoff = dict(self.handoff, public_release_authorized=True)
        with self.assertRaises(ValueError):
            review("/media", handoff, self.checks, "reviewer")
