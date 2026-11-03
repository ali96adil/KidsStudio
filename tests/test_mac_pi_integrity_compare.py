import unittest

from kidsstudio.mac_pi_integrity_compare import compare_reports


class MacPiIntegrityCompareTests(unittest.TestCase):
    def setUp(self):
        self.mac = {
            "status": "READY_FOR_TRANSFER_NOT_TRANSFERRED",
            "episode_id": "colors_001",
            "size": 123,
            "sha256": "a" * 64,
            "network_checked": False,
            "youtube_uploaded": False,
            "public_release_authorized": False,
        }
        self.pi = dict(self.mac, status="PI_MEDIA_VERIFIED_NOT_QUEUED")

    def test_matching_reports(self):
        result = compare_reports(self.mac, self.pi)
        self.assertTrue(result["matching"])
        self.assertEqual(result["status"], "MAC_PI_INTEGRITY_MATCH")
        self.assertFalse(result["public_release_authorized"])

    def test_different_digest_rejected_as_mismatch(self):
        self.pi["sha256"] = "b" * 64
        result = compare_reports(self.mac, self.pi)
        self.assertFalse(result["matching"])
        self.assertEqual(result["status"], "MAC_PI_INTEGRITY_MISMATCH")

    def test_different_episode_or_size_mismatch(self):
        self.pi["size"] = 124
        self.assertFalse(compare_reports(self.mac, self.pi)["matching"])
        self.pi["size"] = 123
        self.pi["episode_id"] = "other"
        self.assertFalse(compare_reports(self.mac, self.pi)["matching"])

    def test_forged_online_or_public_claim_rejected(self):
        self.pi["youtube_uploaded"] = True
        with self.assertRaises(ValueError):
            compare_reports(self.mac, self.pi)
        self.pi["youtube_uploaded"] = False
        self.mac["public_release_authorized"] = True
        with self.assertRaises(ValueError):
            compare_reports(self.mac, self.pi)

    def test_invalid_digest_rejected(self):
        self.pi["sha256"] = "x" * 64
        with self.assertRaises(ValueError):
            compare_reports(self.mac, self.pi)


if __name__ == "__main__":
    unittest.main()
