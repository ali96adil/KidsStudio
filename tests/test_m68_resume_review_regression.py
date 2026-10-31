"""Regression tests for canonical M68 resume entrypoint review enforcement."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_short_resume import resume_short, ShortResumeError
from kidsstudio.m68_short_content_review import CHECKS


class ResumeReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING",
            "short_id": "colors-short-01",
            "episode_id": "colors-short-01",
            "source_episode_id": "colors",
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
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

    def run_resume(self):
        return resume_short("/media", self.manifest, self.receipt,
                            host="pi.local", user="studio",
                            remote_dir="/srv/kids")

    @patch("kidsstudio.m68_short_resume.transfer_resumable")
    def test_legacy_pass_without_checks_cannot_transfer(self, transfer):
        del self.receipt["checks"]
        with self.assertRaises(ShortResumeError):
            self.run_resume()
        transfer.assert_not_called()

    @patch("kidsstudio.m68_short_resume.transfer_resumable")
    def test_rejected_axis_cannot_transfer(self, transfer):
        self.receipt["checks"]["copyright"] = False
        with self.assertRaises(ShortResumeError):
            self.run_resume()
        transfer.assert_not_called()

    @patch("kidsstudio.m68_short_resume.transfer_resumable")
    def test_public_release_cannot_transfer(self, transfer):
        self.receipt["public_release_authorized"] = True
        with self.assertRaises(ShortResumeError):
            self.run_resume()
        transfer.assert_not_called()

    @patch("kidsstudio.m68_short_resume.transfer_resumable")
    @patch("kidsstudio.m68_short_resume.verify_inventory",
           return_value={"sha256": "a" * 64})
    def test_complete_review_can_stage_only(self, _verify, transfer):
        transfer.return_value = {"sha256": "a" * 64,
                                 "remote_master": "/srv/kids/short.mp4",
                                 "status": "VERIFIED"}
        result = self.run_resume()
        self.assertEqual(result["status"], "SHORT_PI_STAGED_REQUIRES_M65_INBOX")
        self.assertFalse(result["youtube_upload_authorized"])
        transfer.assert_called_once()
