"""Tests: M68 short audit never starts or retries a YouTube upload."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_short_upload_audit import audit_short_upload, ShortUploadAuditError
from kidsstudio.youtube_private_upload import UploadJournal


class ShortUploadAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "uploads.sqlite"
        self.job = "a" * 32
        self.sha = "b" * 64
        self.registry = {"short_id": "colors-short-01",
                         "media_sha256": self.sha,
                         "status": "PI_STAGED_NOT_APPROVED"}

    def audit(self):
        return audit_short_upload(
            self.path, short_id="colors-short-01",
            render_job_id=self.job, media_sha256=self.sha,
            registry_record=self.registry)

    def test_no_attempt_does_not_authorize_upload(self):
        result = self.audit()
        self.assertEqual(result["status"], "NO_UPLOAD_ATTEMPT_M65_APPROVAL_REQUIRED")
        self.assertFalse(result["retry_authorized"])

    def test_started_attempt_must_not_retry(self):
        UploadJournal(self.path).reserve(self.job, self.sha, "c" * 64)
        result = self.audit()
        self.assertEqual(result["attempt_state"], "STARTED")
        self.assertFalse(result["retry_authorized"])

    def test_uploaded_attempt_must_not_retry(self):
        journal = UploadJournal(self.path)
        journal.reserve(self.job, self.sha, "c" * 64)
        journal.record_uploaded(self.job, "abcdefghijk")
        result = self.audit()
        self.assertEqual(result["attempt_state"], "UPLOADED_UNVERIFIED")
        self.assertFalse(result["retry_authorized"])

    def test_mismatched_short_rejected(self):
        self.registry["short_id"] = "other-short"
        with self.assertRaises(ShortUploadAuditError):
            self.audit()
