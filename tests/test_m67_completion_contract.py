"""Completion gate regression checks."""
import tempfile
import unittest

from kidsstudio.m67_completion_gate import evaluate


class CompletionTests(unittest.TestCase):
    def test_no_hardware_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            result = evaluate(root)
            self.assertEqual(result["status"], "M67_NOT_ACCEPTED")
            self.assertFalse(result["hardware_independently_verified"])
            self.assertFalse(result["public_release_authorized"])

    def test_claims_not_automatically_proof(self):
        with tempfile.TemporaryDirectory() as root:
            result = evaluate(root, {
                "mac_render_verified": True,
                "pi_transfer_verified": True,
                "m65_pi_inbox_accepted": True,
                "private_youtube_video_verified": True,
                "owner_private_review_completed": True,
            })
            self.assertFalse(result["hardware_independently_verified"])
