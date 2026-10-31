"""M67 release evidence regression tests."""
import tempfile
import unittest

from kidsstudio.m67_release_evidence import report


class ReleaseEvidenceTests(unittest.TestCase):
    def test_ci_success_without_production_is_incomplete(self):
        with tempfile.TemporaryDirectory() as root:
            result = report(root, commit_sha="a" * 40,
                            ci="success", godot="success")
            self.assertEqual(result["status"], "M67_SOFTWARE_EVIDENCE_INCOMPLETE")
            self.assertFalse(result["youtube_private_upload_verified"])
            self.assertFalse(result["public_release_authorized"])

    def test_invalid_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            result = report(root, commit_sha="not-a-commit",
                            ci="success", godot="success")
            self.assertFalse(result["checks"]["commit_sha_valid"])
