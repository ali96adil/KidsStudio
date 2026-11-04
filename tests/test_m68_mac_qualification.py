"""Tests for single-command Mac readiness assessment."""
import unittest

from kidsstudio.m68_mac_qualification import qualify_mac


class MacQualificationTests(unittest.TestCase):
    def test_ready_does_not_claim_execution(self):
        result = qualify_mac(
            first_endpoint="http://127.0.0.1:11434/api/chat",
            first_model="model-a",
            second_endpoint="http://127.0.0.1:11435/api/chat",
            second_model="model-b",
            dependency_probe=lambda **kwargs: {"missing": [], "status": "PRESENT"},
            model_qualifier=lambda **kwargs: {"ready_for_inference_attempt": True})
        self.assertTrue(result["ready_for_manual_inference_trial"])
        self.assertFalse(result["inference_executed"])
        self.assertFalse(result["pi_transfer_executed"])
        self.assertFalse(result["public_release_authorized"])

    def test_missing_dependency_blocks(self):
        result = qualify_mac(
            first_endpoint="a", first_model="b",
            second_endpoint="c", second_model="d",
            dependency_probe=lambda **kwargs: {"missing": ["ffmpeg"]},
            model_qualifier=lambda **kwargs: {"ready_for_inference_attempt": True})
        self.assertEqual(result["status"], "MAC_PREPARATION_BLOCKED")
