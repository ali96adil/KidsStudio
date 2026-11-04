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

    def test_stable_unresolved_started_upload_blocks_completion(self):
        before = journal()
        before["total"] = 1
        before["states"]["STARTED"] = 1
        before["requires_manual_reconciliation"] = ["a" * 32]
        result = summarize(acceptance(), before, copy.deepcopy(before))
        self.assertFalse(result["pass"])
        self.assertTrue(result["checks"]["journal_reboot_stable"])
        self.assertFalse(result["checks"]["journal_unresolved_uploads_clear"])
        self.assertEqual(result["journal_requires_manual_reconciliation"],
                         ["a" * 32])

    def test_reserved_receipt_must_match_master_size(self):
        a = acceptance()
        a["master"]["size_bytes"] = 1200
        a["reserved"] = {
            "status": "M66_RESERVED_PI_MASTER_MATCH", "pass": True,
            "network_used": False, "upload_performed": False,
            "render_job_id": "a" * 32, "size_bytes": 1300,
            "master_sha256": "b" * 64,
        }
        with self.assertRaises(ValueError):
            summarize(a, journal(), journal())

    def test_matching_reserved_receipt_accepted_offline_only(self):
        a = acceptance()
        a["master"]["size_bytes"] = 1200
        a["reserved"] = {
            "status": "M66_RESERVED_PI_MASTER_MATCH", "pass": True,
            "network_used": False, "upload_performed": False,
            "render_job_id": "a" * 32, "size_bytes": 1200,
            "master_sha256": "b" * 64,
        }
        result = summarize(a, journal(), journal())
        self.assertTrue(result["checks"]["reserved_journal_checked"])
        self.assertFalse(result["field_qualified"])

    def test_matching_size_wrong_reserved_digest_rejected(self):
        a = acceptance()
        a["master"]["size_bytes"] = 1200
        a["reserved"] = {
            "status": "M66_RESERVED_PI_MASTER_MATCH", "pass": True,
            "network_used": False, "upload_performed": False,
            "render_job_id": "a" * 32, "size_bytes": 1200,
            "master_sha256": "c" * 64,
        }
        with self.assertRaises(ValueError):
            summarize(a, journal(), journal())

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
