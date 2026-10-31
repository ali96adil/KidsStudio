"""Tests for automatic lesson revision work-item planning."""
import unittest

from kidsstudio.m68_lesson_revision_queue import plan_revision


class RevisionQueueTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "s", "source_episode_id": "ep",
                        "sha256": "a" * 64}
        self.receipt = {
            "status": "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED",
            "short_id": "s", "source_episode_id": "ep",
            "video_sha256": "a" * 64, "script_sha256": "b" * 64,
            "checks": {"pedagogy": False, "source_consistency": True},
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
            "review_findings": [
                {"reviewer_model": model, "axis": axis,
                 "decision": "UNSURE" if model == "model-b" and axis == "pedagogy" else "PASS",
                 "evidence": "This script does not clearly assess the child's learning objective."}
                for model in ("model-a", "model-b")
                for axis in ("pedagogy", "source_consistency")
            ],
        }

    def test_disagreement_creates_revision_not_upload(self):
        result = plan_revision(self.handoff, self.receipt)
        self.assertEqual(result["status"], "LESSON_REVISION_REQUIRED")
        self.assertEqual(result["assigned_role"], "script_revision_agent")
        self.assertEqual(len(result["issues"]), 1)
        self.assertFalse(result["youtube_upload_authorized"])

    def test_mismatched_checks_rejected(self):
        self.receipt["checks"]["pedagogy"] = True
        with self.assertRaises(ValueError):
            plan_revision(self.handoff, self.receipt)

    def test_duplicate_model_findings_rejected(self):
        self.receipt["review_findings"][2]["reviewer_model"] = "model-a"
        with self.assertRaises(ValueError):
            plan_revision(self.handoff, self.receipt)

    def test_all_pass_needs_no_revision(self):
        for row in self.receipt["review_findings"]:
            row["decision"] = "PASS"
        self.receipt["checks"]["pedagogy"] = True
        result = plan_revision(self.handoff, self.receipt)
        self.assertEqual(result["status"], "LESSON_MODEL_PASS_NO_REVISION")
        self.assertEqual(result["issues"], [])
