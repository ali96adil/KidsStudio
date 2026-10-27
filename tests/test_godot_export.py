from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from kidsstudio.godot_export import (
    GodotExportError, export_godot, load_scene_spec
)
from kidsstudio.motion import create_motion_evidence


class GodotExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        self.parts = []
        for z, ident in enumerate((
            "body", "head", "arm_left", "arm_right", "leg_left", "leg_right",
            "ear_left", "ear_right", "eyes", "mouth",
        )):
            image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            ImageDraw.Draw(image).ellipse(
                (25, 25, 100, 105), fill=(230, 185, 165, 255)
            )
            image.save(self.root / "assets" / (ident + ".png"))
            self.parts.append({
                "id": ident, "file": "assets/" + ident + ".png",
                "pivot": [65, 63], "z": z
            })
        self.manifest = self.root / "rig.json"
        self.manifest.write_text(json.dumps({
            "schema_version": 1, "character_id": "bunny_v02",
            "canvas": {"width": 128, "height": 128},
            "parts": self.parts
        }), encoding="utf-8")
        self.scene = self.root / "scene.json"
        self.timeline = {
            "schema_version": 1, "fps": 30, "duration_seconds": 6,
            "beats": [
                {"start": 0, "end": 2, "motion": "neutral"},
                {"start": 2, "end": 4, "motion": "wave_right"},
                {"start": 4, "end": 6, "motion": "jump"}
            ]
        }
        self.write_scene()

    def write_scene(self):
        self.scene.write_text(json.dumps(self.timeline), encoding="utf-8")

    def test_generates_standalone_project_and_correct_part_mapping(self):
        dest = self.root / "godot_export"
        report = export_godot(self.manifest, self.scene, dest)
        self.assertEqual(report["status"], "PREVIEW_ONLY_UNAPPROVED")
        self.assertEqual(report["fps"], 30)
        self.assertTrue((dest / "project.godot").is_file())
        self.assertTrue((dest / "main.tscn").is_file())
        script = (dest / "scripts" / "rig_player.gd").read_text()
        self.assertIn("wave_right", script)
        self.assertIn("ImageTexture.create_from_image", script)
        self.assertIn("layer_image.load(", script)
        self.assertIn('(_parts["head"] as Node2D)', script)
        copy = json.loads((dest / "rig.json").read_text())
        for part in copy["parts"]:
            self.assertTrue((dest / part["file"]).is_file())
        self.assertEqual(len(report["exported_parts"]), 10)

    def test_contiguous_scene_enforced(self):
        self.timeline["beats"][1]["start"] = 2.5
        self.write_scene()
        with self.assertRaises(GodotExportError):
            load_scene_spec(self.scene)

    def test_unknown_action_rejected(self):
        self.timeline["beats"][1]["motion"] = "run_shell"
        self.write_scene()
        with self.assertRaises(GodotExportError):
            load_scene_spec(self.scene)

    def test_does_not_overwrite_project(self):
        dest = self.root / "out"
        export_godot(self.manifest, self.scene, dest)
        with self.assertRaises(FileExistsError):
            export_godot(self.manifest, self.scene, dest)

    def test_reviewer_required_fail_closed(self):
        with self.assertRaises(GodotExportError):
            export_godot(
                self.manifest, self.scene, self.root / "unapproved",
                require_reviewed=True
            )
        self.assertFalse((self.root / "unapproved").exists())

    def test_cannot_use_unsafe_part_id(self):
        self.parts[1]["id"] = "head/../../unsafe"
        self.manifest.write_text(json.dumps({
            "schema_version": 1, "character_id": "bunny",
            "canvas": {"width": 128, "height": 128},
            "parts": self.parts
        }))
        with self.assertRaises(GodotExportError):
            export_godot(self.manifest, self.scene, self.root / "unsafe")

    def test_proper_review_allows_internal_asset_export(self):
        review_out = self.root / "review"
        create_motion_evidence(self.manifest, review_out, side=96, gif=False)
        evidence = review_out / "motion_evidence.json"
        reviewed = self.root / "approved.json"
        reviewed.write_text(json.dumps({
            "status": "APPROVED_BY_LOCAL_AI_QA",
            "verdict": "PASS",
            "owner_release_approval_required": True,
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        result = export_godot(
            self.manifest, self.scene, self.root / "internal_approved",
            require_reviewed=True,
            review_report=reviewed, evidence_path=evidence,
        )
        self.assertEqual(result["status"],
                         "INTERNAL_RIG_QA_PASSED_NOT_PUBLICATION_APPROVED")

    def test_revised_art_invalidates_previous_approval(self):
        review_out = self.root / "review"
        create_motion_evidence(self.manifest, review_out, side=96, gif=False)
        evidence = review_out / "motion_evidence.json"
        review = self.root / "approved.json"
        review.write_text(json.dumps({
            "status": "APPROVED_BY_LOCAL_AI_QA",
            "verdict": "PASS",
            "owner_release_approval_required": True,
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }))
        Image.new("RGBA", (128, 128), (0, 0, 0, 0)).save(
            self.root / "assets" / "arm_right.png"
        )
        with self.assertRaises(GodotExportError):
            export_godot(
                self.manifest, self.scene, self.root / "out",
                require_reviewed=True, review_report=review,
                evidence_path=evidence,
            )


if __name__ == "__main__":
    unittest.main()
