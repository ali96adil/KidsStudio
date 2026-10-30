"""Offline M67 handoff contract lab tests."""
import unittest
from kidsstudio.m67_offline_handoff_lab import run_lab


class HandoffLabTests(unittest.TestCase):
    def test_contract_passes_without_network(self):
        result = run_lab()
        self.assertEqual(result["status"], "OFFLINE_HANDOFF_CONTRACT_PASS")
        self.assertFalse(result["network_used"])
        self.assertFalse(result["youtube_uploaded"])
        self.assertEqual(result["cases"]["tampered_receipts"],
                         "M67_PI_RECEIPTS_BLOCKED")
