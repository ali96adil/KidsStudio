"""Consolidated M68 evidence remains blocked until all independent axes exist."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_consolidated_review import audit
from kidsstudio.m68_short_content_review import CHECKS


class ConsolidatedReviewTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING",
            "short_id": "short-001", "episode_id": "short-001",
            "source_episode_id": "episode-001", "sha256": "a" * 64,
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }

    @patch("kidsstudio.m68_consolidated_review.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_missing_evidence_never_approves(self, _verify):
        result = audit("/tmp", self.handoff)
        self.assertEqual(result["status"], "M68_CONSOLIDATED_REVIEW_BLOCKED")
        self.assertEqual(set(result["checks"]), set(CHECKS))
        self.assertFalse(any(result["checks"].values()))
        self.assertFalse(result["youtube_upload_authorized"])

    @patch("kidsstudio.m68_consolidated_review.audit_rights",
           return_value={"reasons": [], "legal_rights_independently_verified": False})
    @patch("kidsstudio.m68_consolidated_review.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_visual_pass_and_documented_rights_still_block(self, _verify, _rights):
        checks = {axis: axis in ("visual", "age_appropriate") for axis in CHECKS}
        receipt = {
            "short_id": "short-001", "video_sha256": "a" * 64,
            "decision": "REJECT",
            "review_scope": "LOCAL_VISUAL_SAFETY_ONLY_FOUR_AXES_UNVERIFIED",
            "checks": checks,
        }
        result = audit("/tmp", self.handoff, vision_receipt=receipt,
                       rights_manifest="/tmp/rights.json")
        self.assertTrue(result["checks"]["visual"])
        self.assertFalse(result["checks"]["copyright"])
        self.assertIn("source_rights_documented_not_legally_verified",
                      result["blockers"])
        self.assertFalse(result["youtube_upload_authorized"])

    @patch("kidsstudio.m68_consolidated_review.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_untrusted_visual_receipt_rejected(self, _verify):
        with self.assertRaises(ValueError):
            audit("/tmp", self.handoff, vision_receipt={
                "short_id": "short-001", "video_sha256": "a" * 64,
                "decision": "PASS", "checks": {axis: True for axis in CHECKS},
                "review_scope": "LOCAL_VISUAL_SAFETY_ONLY_FOUR_AXES_UNVERIFIED"})
