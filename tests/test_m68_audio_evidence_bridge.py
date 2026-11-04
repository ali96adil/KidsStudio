"""M68 audio evidence bridge never treats a claimed PASS as authorization."""
import unittest

from kidsstudio.m68_audio_evidence_bridge import audit_audio_receipt


class AudioEvidenceBridgeTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "short-1", "source_episode_id": "ep-1",
                        "sha256": "a" * 64}
        self.receipt = {
            "short_id": "short-1", "source_episode_id": "ep-1",
            "video_sha256": "a" * 64,
            "review_scope": "ACTUAL_MP4_AUDIO_OBSERVED",
            "audio_review_completed": True, "independent_reviewers": 2,
            "audio_decision": "PASS", "audio_sha256": "b" * 64,
            "reviewer_model_hashes": ["c" * 64, "d" * 64],
            "evidence": "Two actual audio model observations are supplied.",
        }

    def test_pinned_claim_is_diagnostic_only(self):
        result = audit_audio_receipt(self.handoff, self.receipt)
        self.assertTrue(result["audio_check"])
        self.assertFalse(result["youtube_upload_authorized"])

    def test_wrong_video_hash_rejected(self):
        receipt = dict(self.receipt, video_sha256="f" * 64)
        with self.assertRaises(ValueError):
            audit_audio_receipt(self.handoff, receipt)

    def test_same_model_twice_rejected(self):
        receipt = dict(self.receipt, reviewer_model_hashes=["c" * 64] * 2)
        with self.assertRaises(ValueError):
            audit_audio_receipt(self.handoff, receipt)
