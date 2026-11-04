"""M66 offline Pi reboot journal comparison acceptance."""
import copy
import unittest

from kidsstudio.m66_reboot_compare import compare


class RebootCompareTests(unittest.TestCase):
    def setUp(self):
        self.before = {
            "status": "M66_READ_ONLY_JOURNAL_REPORT",
            "network_used": False,
            "database_modified": False,
            "public_release_authorized": False,
            "total": 2,
            "states": {"STARTED": 1, "UPLOADED_UNVERIFIED": 0, "PRIVATE_VERIFIED": 1},
            "requires_manual_reconciliation": ["a" * 32],
        }

    def test_unchanged_restart_passes(self):
        self.assertTrue(compare(self.before, copy.deepcopy(self.before))["pass"])

    def test_missing_job_fails(self):
        after = copy.deepcopy(self.before)
        after["total"] = 1
        after["states"]["STARTED"] = 0
        after["requires_manual_reconciliation"] = []
        self.assertFalse(compare(self.before, after)["pass"])

    def test_changed_unresolved_identity_fails(self):
        after = copy.deepcopy(self.before)
        after["requires_manual_reconciliation"] = ["b" * 32]
        self.assertFalse(compare(self.before, after)["pass"])

    def test_changed_state_fails(self):
        after = copy.deepcopy(self.before)
        after["states"]["STARTED"] = 0
        after["states"]["PRIVATE_VERIFIED"] = 2
        after["requires_manual_reconciliation"] = []
        self.assertFalse(compare(self.before, after)["pass"])

    def test_malformed_count_rejected(self):
        after = copy.deepcopy(self.before)
        after["states"]["STARTED"] = True
        with self.assertRaises(ValueError):
            compare(self.before, after)

    def test_duplicate_jobs_rejected(self):
        after = copy.deepcopy(self.before)
        after["requires_manual_reconciliation"] = ["a" * 32, "a" * 32]
        with self.assertRaises(ValueError):
            compare(self.before, after)

    def test_network_claim_rejected(self):
        after = copy.deepcopy(self.before)
        after["network_used"] = True
        with self.assertRaises(ValueError):
            compare(self.before, after)


if __name__ == "__main__":
    unittest.main()
