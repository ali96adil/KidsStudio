"""M68 never treats a raw transferred short as an approved M65 upload."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_pi_import_preflight import assess_short_import, ShortImportPreflightError


class ShortImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.receipt = {"status": "SHORT_ON_PI_PENDING_PRIVATE_UPLOAD",
                        "short_id": "colors-ar-001-short-01",
                        "source_episode_id": "colors-ar-001",
                        "sha256": "a" * 64,
                        "youtube_upload_authorized": False,
                        "public_release_authorized": False}

    def test_missing_m65_receipts_blocks(self):
        with patch("kidsstudio.m68_pi_import_preflight.preflight",
                   return_value={"status": "M67_PI_RECEIPTS_BLOCKED"}):
            with self.assertRaises(ShortImportPreflightError):
                assess_short_import(self.receipt, master="short.mp4", plan="plan.json",
                                    readiness="ready.json", render_job_id="short-job-01")

    def test_valid_receipts_still_do_not_authorize_upload(self):
        with patch("kidsstudio.m68_pi_import_preflight.preflight",
                   return_value={"status": "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL"}):
            result = assess_short_import(self.receipt, master="short.mp4", plan="plan.json",
                                         readiness="ready.json", render_job_id="short-job-01")
        self.assertEqual(result["status"], "M68_SHORT_READY_FOR_EXISTING_M65_IMPORT")
        self.assertFalse(result["pi_upload_authorized"])
        self.assertFalse(result["public_release_authorized"])

    def test_parent_identity_cannot_be_reused(self):
        with self.assertRaises(ShortImportPreflightError):
            assess_short_import(self.receipt, master="short.mp4", plan="plan.json",
                                readiness="ready.json", render_job_id="colors-ar-001")
