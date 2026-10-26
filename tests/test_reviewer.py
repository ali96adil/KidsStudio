from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.motion import create_motion_evidence
from kidsstudio.reviewer import (
    LocalVisionClient, VisionReviewError, review_rig,
)


class FakeVision:
    def __init__(self, verdict="PASS", confidence=0.95, issues=None):
        self.verdict = verdict
        self.confidence = confidence
        self.issues = [] if issues is None else issues
        self.calls = 0

    def review(self, model, images_b64):
        self.calls += 1
        assert len(images_b64) >= 1
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reason": "All panels have clean joints" if self.verdict == "PASS"
                      else "Visible shoulder seam in wave_right",
            "issues": self.issues
        }


class VisionReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        parts = []
        for z, name in enumerate((
            "body", "head", "arm_left", "arm_right", "leg_left", "leg_right"
        )):
            image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse((12, 12, 52, 52), fill=(240, 200, 175, 255))
            image.save(self.root / "assets" / (name + ".png"))
            parts.append({
                "id": name, "file": "assets/" + name + ".png",
                "pivot": [32, 32], "z": z,
            })
        self.manifest = self.root / "rig.json"
        self.manifest.write_text(json.dumps({
            "schema_version": 1, "character_id": "test",
            "canvas": {"width": 64, "height": 64}, "parts": parts
        }), encoding="utf-8")
        create_motion_evidence(
            self.manifest, self.root / "review", side=96, gif=False
        )
        self.evidence = self.root / "review" / "motion_evidence.json"

    def test_clean_review_may_approve_rig_only(self):
        ai = FakeVision()
        report = review_rig(
            self.manifest, self.evidence, self.root / "decision.json",
            model="local-vision:8b", client=ai
        )
        self.assertEqual(report["status"], "APPROVED_BY_LOCAL_AI_QA")
        self.assertEqual(ai.calls, 1)
        self.assertTrue(report["owner_release_approval_required"])

    def test_low_confidence_pass_requires_revision(self):
        report = review_rig(
            self.manifest, self.evidence, self.root / "decision2.json",
            model="local-vision:8b", client=FakeVision(confidence=0.42)
        )
        self.assertEqual(report["status"], "REVISE_REQUIRED")

    def test_reported_defect_blocks_pass(self):
        ai = FakeVision(issues=[{
            "motion": "wave_right", "severity": "high",
            "description": "Old arm visible behind moving arm",
        }])
        report = review_rig(
            self.manifest, self.evidence, self.root / "decision3.json",
            model="local-vision:8b", client=ai
        )
        self.assertEqual(report["status"], "REVISE_REQUIRED")

    def test_stale_evidence_rejected_before_vision(self):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((10, 10, 50, 50), fill=(0, 150, 140, 255))
        image.save(self.root / "assets" / "arm_right.png")
        ai = FakeVision()
        with self.assertRaises(VisionReviewError):
            review_rig(self.manifest, self.evidence, self.root / "decision4.json",
                       model="local-vision:8b", client=ai)
        self.assertEqual(ai.calls, 0)

    def test_remote_reviewer_forbidden(self):
        with self.assertRaises(VisionReviewError):
            LocalVisionClient("https://some-cloud.example:11434")


if __name__ == "__main__":
    unittest.main()
