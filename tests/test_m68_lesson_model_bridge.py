"""Tests for educational AI evidence binding and conservative semantics."""
import unittest

from kidsstudio.m68_lesson_model_bridge import audit_lesson_model_receipt


class LessonModelBridgeTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "short-1", "source_episode_id": "ep-1",
                        "sha256": "a" * 64}
        self.lesson = {"script_sha256": "b" * 64}
        self.receipt = {
            "status": "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED",
            "short_id": "short-1", "source_episode_id": "ep-1",
            "video_sha256": "a" * 64, "script_sha256": "b" * 64,
            "model_response_sha256": ["c" * 64, "d" * 64],
            "checks": {"pedagogy": True, "source_consistency": True},
            "model_claims_independently_attested": False,
            "video_script_fidelity_verified": False,
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }

    def test_two_reported_passes_never_authorize_upload(self):
        result = audit_lesson_model_receipt(
            self.handoff, self.lesson, self.receipt)
        self.assertTrue(result["model_reported_pedagogy_pass"])
        self.assertFalse(result["video_script_fidelity_verified"])
        self.assertFalse(result["youtube_upload_authorized"])

    def test_cross_episode_receipt_rejected(self):
        self.receipt["source_episode_id"] = "other"
        with self.assertRaises(ValueError):
            audit_lesson_model_receipt(self.handoff, self.lesson, self.receipt)

    def test_duplicate_model_responses_rejected(self):
        self.receipt["model_response_sha256"] = ["c" * 64, "c" * 64]
        with self.assertRaises(ValueError):
            audit_lesson_model_receipt(self.handoff, self.lesson, self.receipt)

    def test_forged_upload_permission_rejected(self):
        self.receipt["youtube_upload_authorized"] = True
        with self.assertRaises(ValueError):
            audit_lesson_model_receipt(self.handoff, self.lesson, self.receipt)
