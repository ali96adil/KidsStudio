import unittest

from kidsstudio.pi_hardware_acceptance import REQUIRED_STEPS, evaluate_evidence


class HardwareAcceptanceRemainingTests(unittest.TestCase):
    def test_initial_report_lists_all_steps(self):
        evidence = {"version": 1,
                    "steps": {name: "not_tested" for name in REQUIRED_STEPS}}
        report = evaluate_evidence(evidence)
        self.assertEqual(report["remaining_steps"], list(REQUIRED_STEPS))
        self.assertEqual(report["next_step"], REQUIRED_STEPS[0])

    def test_partial_and_complete_reports(self):
        evidence = {"version": 1,
                    "steps": {name: "pass" for name in REQUIRED_STEPS}}
        evidence["steps"]["iphone_owner_review"] = "fail"
        evidence["steps"]["owner_notes_recorded"] = "not_tested"
        report = evaluate_evidence(evidence)
        self.assertEqual(report["remaining_steps"],
                         ["iphone_owner_review", "owner_notes_recorded"])
        self.assertEqual(report["next_step"], "iphone_owner_review")
        self.assertFalse(report["ready_for_live_operation"])
        evidence["steps"]["iphone_owner_review"] = "pass"
        evidence["steps"]["owner_notes_recorded"] = "pass"
        report = evaluate_evidence(evidence)
        self.assertEqual(report["remaining_steps"], [])
        self.assertIsNone(report["next_step"])


if __name__ == "__main__":
    unittest.main()
