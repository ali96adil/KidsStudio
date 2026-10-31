"""Tests for complete M68 content QA gating before Pi transfer."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_reviewed_transfer import (
    ShortQATransferError, validate_review, transfer_reviewed_short)
from kidsstudio.m68_short_content_review import CHECKS


class ReviewedTransferTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "colors-short-01",
                        "source_episode_id": "colors"}
        self.receipt = {
            "status": "SHORT_CONTENT_QA_RECORDED", "decision": "PASS",
            "short_id": "colors-short-01", "source_episode_id": "colors",
            "video_sha256": "a" * 64, "reviewer": "visual-reviewer",
            "checks": dict.fromkeys(CHECKS, True),
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }

    @patch("kidsstudio.m68_reviewed_transfer.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_complete_review_passes(self, _verify):
        self.assertEqual(validate_review("/media", self.handoff, self.receipt),
                         "a" * 64)

    def test_missing_review_axis_blocks(self):
        del self.receipt["checks"]["copyright"]
        with self.assertRaises(ShortQATransferError):
            validate_review("/media", self.handoff, self.receipt)

    def test_false_review_axis_blocks(self):
        self.receipt["checks"]["pedagogy"] = False
        with self.assertRaises(ShortQATransferError):
            validate_review("/media", self.handoff, self.receipt)

    def test_public_authorization_blocks(self):
        self.receipt["public_release_authorized"] = True
        with self.assertRaises(ShortQATransferError):
            validate_review("/media", self.handoff, self.receipt)

    @patch("kidsstudio.m68_reviewed_transfer.resume_short")
    @patch("kidsstudio.m68_reviewed_transfer.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_transfer_uses_validated_receipt(self, _verify, transfer):
        transfer.return_value = {"sha256": "a" * 64,
                                 "status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX"}
        result = transfer_reviewed_short(
            "/media", self.handoff, self.receipt,
            host="pi.local", user="studio", remote_dir="/srv/kids")
        self.assertEqual(result["sha256"], "a" * 64)
        transfer.assert_called_once()

    @patch("kidsstudio.m68_reviewed_transfer.verify_inventory",
           return_value={"sha256": "b" * 64})
    def test_changed_media_blocks(self, _verify):
        with self.assertRaises(ShortQATransferError):
            validate_review("/media", self.handoff, self.receipt)
