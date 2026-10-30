"""M66.3 qualification report tests; fake evidence cannot imply device readiness."""
import unittest

from kidsstudio.m66_qualification_report import assess


def valid_evidence():
    return {
        "mac_sha256": "a" * 64,
        "pi_sha256": "a" * 64,
        "transfer_resumed": True,
        "mac_off_pi_continued": True,
        "pi_reboot_recovered": True,
        "youtube_privacy_status": "private",
        "owner_review_status": "pending",
        "duplicate_inserts": 0,
        "public_transitions": 0,
        "real_hardware_observed": True,
        "youtube_video_id": "synthetic-only-test-id",
    }


class M66QualificationReportTests(unittest.TestCase):
    def test_complete_claimed_evidence(self):
        self.assertEqual(assess(valid_evidence())["status"], "QUALIFIED")

    def test_missing_fields_fail_closed(self):
        result = assess({})
        self.assertEqual(result["status"], "NOT_QUALIFIED")
        self.assertIn("mac_sha256", result["missing"])

    def test_no_real_hardware_fail_closed(self):
        data = valid_evidence()
        data["real_hardware_observed"] = False
        self.assertEqual(assess(data)["status"], "NOT_QUALIFIED")

    def test_public_video_fail_closed(self):
        data = valid_evidence()
        data["youtube_privacy_status"] = "public"
        self.assertEqual(assess(data)["status"], "NOT_QUALIFIED")

    def test_duplicate_upload_fail_closed(self):
        data = valid_evidence()
        data["duplicate_inserts"] = 1
        self.assertEqual(assess(data)["status"], "NOT_QUALIFIED")

    def test_mismatched_sha_fail_closed(self):
        data = valid_evidence()
        data["pi_sha256"] = "b" * 64
        self.assertEqual(assess(data)["status"], "NOT_QUALIFIED")


if __name__ == "__main__":
    unittest.main()
