"""Strict anatomical geometry regression tests, using synthetic RGBA rigs."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.planner import make_rig_plan
from kidsstudio.rigqa import check_rig

PARTS = ("body", "head", "arm_left", "arm_right", "leg_left", "leg_right")
RECTS = (
    (8, 8, 58, 58),
    (70, 8, 120, 58),
    (8, 70, 58, 120),
    (70, 70, 120, 120),
    (40, 40, 90, 90),
    (40, 8, 90, 60),
)
POLICY = {
    "strict_parts": True,
    "max_outside_fraction": 0.10,
    "min_inside_fill_fraction": 0.03,
    "alpha_threshold": 32,
    "reject_identical_layers": True,
}


class AnatomicalRigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        self.parts = []
        for i, (name, rect) in enumerate(zip(PARTS, RECTS)):
            region = list(rect)
            img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse(
                (rect[0] + 6, rect[1] + 6, rect[2] - 6, rect[3] - 6),
                fill=(235, 170 + i, 165, 255),
            )
            img.save(self.root / "assets" / (name + ".png"))
            self.parts.append({
                "id": name,
                "file": "assets/" + name + ".png",
                "pivot": [(rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2],
                "z": i,
                "expected_region": region,
            })
        self.rig = self.root / "rig.json"
        self.save()

    def save(self):
        self.rig.write_text(json.dumps({
            "schema_version": 1,
            "character_id": "synthetic_bunny",
            "canvas": {"width": 128, "height": 128},
            "qa_policy": POLICY,
            "parts": self.parts,
        }), encoding="utf-8")

    def test_correctly_registered_distinct_parts_pass(self):
        report = check_rig(self.rig)
        self.assertTrue(report["passed"], report["errors"])
        self.assertTrue(report["anatomical_checks_enabled"])
        self.assertEqual(len(report["part_geometry"]), 6)
        for stats in report["part_geometry"].values():
            self.assertEqual(stats["outside_pixels"], 0)
            self.assertGreater(stats["inside_fill_fraction"], 0.03)

    def test_full_body_masquerading_as_single_arm_fails(self):
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((3, 3, 124, 124), fill=(250, 180, 165, 255))
        img.save(self.root / "assets" / "arm_right.png")
        report = check_rig(self.rig)
        self.assertFalse(report["passed"])
        self.assertTrue(any("outside anatomical region" in e for e in report["errors"]))
        self.assertGreater(report["part_geometry"]["arm_right"]["outside_fraction"], 0.20)

    def test_unrelated_faraway_arm_rejected(self):
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((1, 1, 37, 37), fill=(200, 220, 80, 255))
        img.save(self.root / "assets" / "arm_right.png")
        report = check_rig(self.rig)
        self.assertFalse(report["passed"])
        self.assertTrue(any("arm_right" in e for e in report["errors"]))

    def test_duplicate_layer_bytes_under_different_filenames_rejected(self):
        copy = (self.root / "assets" / "arm_left.png").read_bytes()
        (self.root / "assets" / "arm_right.png").write_bytes(copy)
        report = check_rig(self.rig)
        self.assertFalse(report["passed"])
        self.assertTrue(any("identical RGBA artwork" in e for e in report["errors"]))

    def test_tiny_pixel_dot_does_not_count_as_a_limb(self):
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        ImageDraw.Draw(img).point((90, 90), fill=(240, 180, 160, 255))
        img.save(self.root / "assets" / "arm_right.png")
        report = check_rig(self.rig)
        self.assertFalse(report["passed"])
        self.assertTrue(any("too little artwork" in e for e in report["errors"]))

    def test_missing_or_invalid_region_is_rejected_in_strict_mode(self):
        self.parts[0].pop("expected_region")
        self.save()
        self.assertFalse(check_rig(self.rig)["passed"])
        self.parts[0]["expected_region"] = [-1, 1, 200, 300]
        self.save()
        self.assertFalse(check_rig(self.rig)["passed"])

    def test_geometry_policy_rejects_out_of_range_thresholds(self):
        original = dict(POLICY)
        try:
            POLICY["max_outside_fraction"] = 1.0
            self.save()
            self.assertFalse(check_rig(self.rig)["passed"])
        finally:
            POLICY.clear()
            POLICY.update(original)

    def test_missing_transparency_is_not_accepted(self):
        Image.new("RGBA", (128, 128), (200, 200, 200, 255)).save(
            self.root / "assets" / "head.png"
        )
        self.assertFalse(check_rig(self.rig)["passed"])

    def test_planner_propagates_regions_and_strict_policy(self):
        blueprint = {
            "schema_version": 1,
            "character_id": "synthetic_bunny",
            "identity_prompt": "Original pastel bunny",
            "canvas": {"width": 128, "height": 128},
            "qa_policy": POLICY,
            "parts": [
                {
                    "id": p["id"], "instruction": "one isolated rig part",
                    "pivot": p["pivot"], "z": p["z"],
                    "expected_region": p["expected_region"],
                }
                for p in self.parts
            ],
        }
        blueprint_file = self.root / "blueprint.json"
        blueprint_file.write_text(json.dumps(blueprint))
        plan = make_rig_plan(blueprint_file)
        manifest = plan["rig_manifest_template"]
        self.assertTrue(manifest["qa_policy"]["strict_parts"])
        self.assertEqual(len(manifest["parts"]), 6)
        for part, job in zip(manifest["parts"], plan["jobs"]):
            self.assertIn("expected_region", part)
            self.assertIn("pixel region", job["prompt"])


if __name__ == "__main__":
    unittest.main()
