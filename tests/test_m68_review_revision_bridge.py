"""Integration tests for AI findings to rewrite proposal bridge."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m68_review_revision_bridge import review_and_revise


class FakeRewriter:
    def rewrite(self, *, script, lesson, issues):
        return {"revised_script": script + "\nCan you name a color?",
                "change_summary": "Added a learning check for young viewers."}


class ReviewRevisionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "s", "source_episode_id": "e",
                        "sha256": "a" * 64}
        self.receipt = {
            "status": "LESSON_MODEL_EVIDENCE_RECORDED_NOT_INDEPENDENTLY_ATTESTED",
            "short_id": "s", "source_episode_id": "e",
            "video_sha256": "a" * 64,
            "checks": {"pedagogy": False, "source_consistency": True},
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
            "review_findings": [
                {"reviewer_model": model, "axis": axis,
                 "decision": "UNSURE" if model == "model-b" and axis == "pedagogy" else "PASS",
                 "evidence": "The script does not clearly assess the learning objective."}
                for model in ("model-a", "model-b")
                for axis in ("pedagogy", "source_consistency")
            ]}

    def test_rejected_review_produces_separate_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.txt"
            lesson = root / "lesson.json"
            proposal = root / "proposal.txt"
            script.write_text("Learn colors.", encoding="utf-8")
            lesson.write_text('{"learning_objective":"colors"}')
            original = script.read_bytes()
            self.receipt["script_sha256"] = hashlib.sha256(original).hexdigest()
            result = review_and_revise(
                self.handoff, review_receipt=self.receipt,
                script_path=script, lesson_path=lesson,
                proposed_script_path=proposal, rewriter=FakeRewriter())
            self.assertEqual(result["status"], "REVISION_CREATED_REVIEW_PENDING")
            self.assertTrue(proposal.is_file())
            self.assertEqual(script.read_bytes(), original)
            self.assertFalse(result["public_release_authorized"])

    def test_pass_skips_rewriter(self):
        self.receipt["script_sha256"] = "b" * 64
        for finding in self.receipt["review_findings"]:
            finding["decision"] = "PASS"
        self.receipt["checks"]["pedagogy"] = True
        result = review_and_revise(
            self.handoff, review_receipt=self.receipt,
            script_path="/nonexistent", lesson_path="/nonexistent",
            proposed_script_path="/nonexistent", rewriter=FakeRewriter())
        self.assertEqual(result["status"], "LESSON_REVIEW_PASS_NO_REVISION")
