"""M66 evidence bundle must never misrepresent offline tests as field proof."""
import copy
import unittest

from kidsstudio.m66_evidence_summary import summarize


def journal():
    return {
        "status": "M66_READ_ONLY_JOURNAL_REPORT",
        "network_used": False, "database_modified": False,
        "public_release_authorized": False, "total": 0,
        "states": {"STARTED": 0, "UPLOADED_UNVERIFIED": 0,
                   "PRIVATE_VERIFIED": 0},
        "snapshot_sha256": "a" * 64,
        "requires_manual_reconciliation": [],
    }


def acceptance():
    return {
        "status": "M66_OFFLINE_PI_MASTER_ACCEPTED", "pass": True,
        "network_used": False, "upload_performed": False,
        "public_release_authorized": False,
        "field_youtube_upload_verified": False,
        "master": {
            "status": "M66_PI_MASTER_SHA256_MATCH", "pass": True,
            "expected_sha256": "b" * 64, "actual_sha256": "b" * 64,
        },
        "reserved": None,
    }


class EvidenceSummaryTests(unittest.TestCase):
    def test_stable_offline_receipts_never_field_qualified(self):
        result = summarize(acceptance(), journal(), journal())
        self.assertTrue(result["pass"])
        self.assertFalse(result["field_qualified"])
        self.assertFalse(result["checks"]["youtube_private_verified"])
        self.assertFalse(result["checks"]["physical_pi_verified"])

    def test_changed_reboot_blocks(self):
        after = journal()
        after["snapshot_sha256"] = "c" * 64
        result = summarize(acceptance(), journal(), after)
        self.assertFalse(result["pass"])

    def test_rejects_claimed_network_use(self):
        a = acceptance()
        a["network_used"] = True
        with self.assertRaises(ValueError):
            summarize(a, journal(), journal())

    def test_rejects_false_field_success(self):
        a = acceptance()
        a["field_youtube_upload_verified"] = True
        with self.assertRaises(ValueError):
            summarize(a, journal(), journal())

    def test_rejects_wrong_master(self):
        a = acceptance()
        a["master"]["actual_sha256"] = "c" * 64
        with self.assertRaises(ValueError):
            summarize(a, journal(), journal())


if __name__ == "__main__":
    unittest.main()
