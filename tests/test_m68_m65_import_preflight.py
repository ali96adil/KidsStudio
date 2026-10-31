"""M68 Shorts must never bypass the existing M65 approval database."""
import unittest

from kidsstudio.m68_m65_import_preflight import assess_short_import


class ShortImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            "episode_id": "colors-short-01", "short_id": "colors-short-01",
            "source_episode_id": "colors",
            "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING",
            "master": {"sha256": "a" * 64},
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
        self.transfer = {
            "status": "SHORT_PI_STAGED_REQUIRES_M65_INBOX",
            "short_id": "colors-short-01", "source_episode_id": "colors",
            "sha256": "a" * 64, "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }

    def test_missing_m65_receipts_blocks(self):
        result = assess_short_import(self.handoff, self.transfer)
        self.assertEqual(result["status"], "M68_SHORT_M65_IMPORT_BLOCKED")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_wrong_short_blocks(self):
        result = assess_short_import(
            self.handoff, dict(self.transfer, short_id="another-short"))
        self.assertFalse(result["checks"]["matching_short"])
        self.assertFalse(result["pi_upload_authorized"])

    def test_private_only_required(self):
        result = assess_short_import(
            self.handoff, dict(self.transfer, public_release_authorized=True))
        self.assertFalse(result["checks"]["private_only"])
        self.assertEqual(result["status"], "M68_SHORT_M65_IMPORT_BLOCKED")
