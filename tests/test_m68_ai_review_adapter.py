"""Fail-closed independent AI review adapter contract tests."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_ai_review_adapter import run_ai_review, ShortAIReviewError
from kidsstudio.m68_short_content_review import CHECKS


class AIReviewAdapterTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {"short_id": "short-01", "source_episode_id": "episode-01",
                        "sha256": "a" * 64}
        self.receipt = {"status": "SHORT_CONTENT_QA_RECORDED",
                        "decision": "PASS", "checks": dict.fromkeys(CHECKS, True)}

    def infer(self, *, axis, root, handoff):
        return {"axis": axis, "passed": True,
                "evidence": "Verified against actual video and lesson script.",
                "short_id": handoff["short_id"],
                "source_episode_id": handoff["source_episode_id"],
                "video_sha256": handoff["sha256"]}

    def test_six_independent_inferences_required(self):
        seen = []
        def infer(**kwargs):
            seen.append(kwargs["axis"])
            return self.infer(**kwargs)
        with patch("kidsstudio.m68_ai_review_adapter.review", return_value=self.receipt):
            result = run_ai_review(".", self.handoff, infer=infer)
        self.assertEqual(seen, list(CHECKS))
        self.assertTrue(result["ai_review_completed"])
        self.assertEqual(set(result["ai_evidence"]), set(CHECKS))

    def test_mismatched_media_evidence_rejected(self):
        def infer(**kwargs):
            result = self.infer(**kwargs)
            result["video_sha256"] = "b" * 64
            return result
        with patch("kidsstudio.m68_ai_review_adapter.review") as record:
            with self.assertRaises(ShortAIReviewError):
                run_ai_review(".", self.handoff, infer=infer)
            record.assert_not_called()

    def test_missing_inference_rejected(self):
        with self.assertRaises(ShortAIReviewError):
            run_ai_review(".", self.handoff, infer=None)
