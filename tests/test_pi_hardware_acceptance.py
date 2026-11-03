import unittest

from kidsstudio.pi_hardware_acceptance import REQUIRED_STEPS, evaluate_evidence


class HardwareAcceptanceTests(unittest.TestCase):
    def evidence(self, value="not_tested"):
        return {"version": 1, "steps": {step: value for step in REQUIRED_STEPS}}

    def test_not_tested_is_not_ready(self):
        result = evaluate_evidence(self.evidence())
        self.assertFalse(result["ready_for_live_operation"])
        self.assertEqual(result["not_tested"], 7)
        self.assertFalse(result["youtube_public_release_authorized"])
        self.assertFalse(result["network_checked"])

    def test_all_pass_required(self):
        result = evaluate_evidence(self.evidence("pass"))
        self.assertTrue(result["ready_for_live_operation"])
        self.assertFalse(result["youtube_public_release_authorized"])
        evidence = self.evidence("pass")
        evidence["steps"]["iphone_owner_review"] = "fail"
        self.assertFalse(evaluate_evidence(evidence)["ready_for_live_operation"])

    def test_missing_or_extra_step_rejected(self):
        evidence = self.evidence()
        del evidence["steps"]["pi_private_upload"]
        with self.assertRaises(ValueError):
            evaluate_evidence(evidence)
        evidence = self.evidence()
        evidence["steps"]["auto_public_release"] = "pass"
        with self.assertRaises(ValueError):
            evaluate_evidence(evidence)

    def test_invalid_status_rejected(self):
        evidence = self.evidence()
        evidence["steps"]["mac_video_export"] = "probably"
        with self.assertRaises(ValueError):
            evaluate_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
