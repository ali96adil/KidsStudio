from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from kidsstudio.planner import make_rig_plan
from kidsstudio.rigqa import MINIMUM_PARTS, check_rig


class RigQATests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        self.parts = []
        for z, ident in enumerate(sorted(MINIMUM_PARTS)):
            png = self.root / "assets" / f"{ident}.png"
            img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((25, 25, 104, 105), fill=(238, 190, 150, 255))
            img.save(png)
            self.parts.append(
                {"id": ident, "file": f"assets/{ident}.png",
                 "pivot": [64, 64], "z": z}
            )
        self.manifest = self.root / "rig.json"
        self.save()

    def save(self) -> None:
        self.manifest.write_text(json.dumps({
            "schema_version": 1, "character_id": "test_bunny",
            "canvas": {"width": 128, "height": 128},
            "parts": self.parts,
        }))

    def test_valid_rig_is_only_technical_pass(self):
        report = check_rig(self.manifest)
        self.assertEqual(report["status"], "TECHNICAL_PASS_PENDING_VISUAL_REVIEW")
        self.assertTrue(report["passed"])
        self.assertTrue(report["visual_review_required"])
        self.assertEqual(report["parts_checked"], 6)

    def test_missing_required_layer_fails(self):
        self.parts = [p for p in self.parts if p["id"] != "head"]
        self.save()
        self.assertFalse(check_rig(self.manifest)["passed"])

    def test_non_rgba_image_fails(self):
        Image.new("RGB", (128, 128), (255, 255, 255)).save(
            self.root / "assets" / "head.png"
        )
        self.assertFalse(check_rig(self.manifest)["passed"])

    def test_path_traversal_rejected(self):
        self.parts[0]["file"] = "../secrets.png"
        self.save()
        report = check_rig(self.manifest)
        self.assertFalse(report["passed"])
        self.assertTrue(any("unsafe" in x for x in report["errors"]))

    def test_invalid_pivot_rejected(self):
        self.parts[0]["pivot"] = [999, 64]
        self.save()
        self.assertFalse(check_rig(self.manifest)["passed"])

    def test_duplicate_part_rejected(self):
        self.parts.append(self.parts[0].copy())
        self.save()
        self.assertFalse(check_rig(self.manifest)["passed"])

    def test_blueprint_generates_jobs_not_images(self):
        blueprint = Path(__file__).resolve().parents[1] / "examples" / "bunny_blueprint.json"
        plan = make_rig_plan(blueprint)
        self.assertEqual(plan["status"], "PLAN_ONLY_NO_ART_GENERATED")
        self.assertEqual(len(plan["jobs"]), 10)
        self.assertEqual(
            {p["id"] for p in plan["rig_manifest_template"]["parts"]},
            {j["part_id"] for j in plan["jobs"]},
        )


if __name__ == "__main__":
    unittest.main()
