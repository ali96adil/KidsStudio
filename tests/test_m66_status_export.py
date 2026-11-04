"""M66.5 operator status export excludes raw evidence and release actions."""
import unittest

from kidsstudio.m66_status_export import snapshot


class M66StatusExportTests(unittest.TestCase):
    def test_missing_evidence_is_not_qualified(self):
        report = snapshot({})
        self.assertEqual(report["qualification_status"], "NOT_QUALIFIED")
        self.assertFalse(report["public_release_allowed_by_this_report"])
        self.assertFalse(report["youtube_upload_allowed_by_this_report"])

    def test_raw_evidence_is_not_exported(self):
        report = snapshot({"refresh_token": "SECRET", "mac_sha256": "a" * 64})
        self.assertNotIn("SECRET", str(report))
        self.assertNotIn("refresh_token", str(report))


if __name__ == "__main__":
    unittest.main()
