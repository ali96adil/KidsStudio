"""Tests for M68 read-only M65 Pi media audit."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.m68_pi_readiness_audit import audit, ShortPiReadinessError


class ShortPiReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.record = {"short_id": "colors-short-01",
                       "media_sha256": "a" * 64,
                       "status": "PI_STAGED_NOT_APPROVED"}
        self.args = {"short_id": "colors-short-01",
                     "render_job_id": "b" * 32,
                     "media_sha256": "a" * 64,
                     "registry_record": self.record}

    def test_unaccepted_short_remains_blocked(self):
        with patch("kidsstudio.m68_pi_readiness_audit.PiOrdinaryInbox") as inbox:
            inbox.return_value.verify.side_effect = ValueError("not approved")
            result = audit(None, Path(self.tmp.name), **self.args)
        self.assertEqual(result["status"], "SHORT_NOT_ACCEPTED_BY_M65")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_full_hash_verification_is_required(self):
        with patch("kidsstudio.m68_pi_readiness_audit.PiOrdinaryInbox") as inbox:
            inbox.return_value.verify.return_value = {"master_sha256": "a" * 64}
            result = audit(None, Path(self.tmp.name), **self.args)
            inbox.return_value.verify.assert_called_once_with("b" * 32, full_sha=True)
        self.assertEqual(result["status"], "SHORT_M65_MEDIA_VERIFIED_POLICY_CHECK_REQUIRED")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_mismatched_accepted_hash_fails(self):
        with patch("kidsstudio.m68_pi_readiness_audit.PiOrdinaryInbox") as inbox:
            inbox.return_value.verify.return_value = {"master_sha256": "c" * 64}
            with self.assertRaises(ShortPiReadinessError):
                audit(None, Path(self.tmp.name), **self.args)
